"""Running a workflow: create the row, walk the graph, park, resume.

The run record is a `call_logs` row
----------------------------------
Every execution creates one, before any node runs — including executions that
never place a call. Two reasons, and the first is the one that mattered:

*Nothing creates a call log* was the gap that made the whole call path
untestable. The ElevenLabs webhook can only complete a row that already exists,
so a row that appears after the call is placed is a race with a real phone call
on the other side of it. Creating it first means a conversation can never exist
without somewhere to record its outcome.

The second is that a run needs somewhere to keep its execution log, and
`call_logs.execution_log` is a column that already exists, is already
tenant-scoped, is already soft-deleted with its row, and is already what the
Calls page and the SSE stream read. A `workflow_runs` table would be better
named; it would also be a migration, a set of RLS policies and a new frontend
surface, to hold what this column holds today.

The cost, stated: the Calls page lists runs that placed no call. `status` and
`trigger_node` distinguish them, and the honest fix is the rename, later.

Parking and resuming
--------------------
A call takes minutes. The walk does not wait for it: `call_patient` returns
`parked`, the walk finishes every *other* branch it can, and the run stops with a
call in flight. When the post-call webhook arrives it rebuilds this same context
from the stored row and continues from the parked node's children.

Nothing is held in process memory between those two halves. The previous system
kept twenty minutes of run state in an `asyncio.create_task` poller, so a deploy
silently destroyed it — the patient confirmed and no appointment was ever
created. Everything needed to resume is in the row: the log carries the parked
node, the visited set, the graph fingerprint and the triggering event.

What is still missing is a timer. A run whose webhook never arrives stays parked
for ever, visible only as `needs_review`. That is recorded in
AI_CALL_SAFETY_POLICY.md under "not yet enforced" and it is the next thing this
module needs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

from app.core.config import get_settings
from app.db.tenancy import TenantScope
from app.engine.context import RunContext
from app.engine.graph import (
    MAX_STEPS,
    Graph,
    GraphError,
    Node,
    fingerprint,
    parse_graph,
    select_trigger,
)
from app.engine.nodes import run_node
from app.engine.steps import (
    BLOCKED,
    FAILED,
    HALTING,
    OK,
    PARKED,
    SKIPPED,
    ExecutionLog,
)
from app.integrations.elevenlabs.webhook import CallResult

logger = logging.getLogger(__name__)

# Run-level entries in the execution log. Namespaced with a dot so they cannot
# collide with a node type, which is also what lets `ExecutionLog.contains`
# recognise a resumed run.
RUN_STARTED: Final[str] = "run.started"
RUN_RESUMED: Final[str] = "run.resumed"
RUN_FINISHED: Final[str] = "run.finished"

# The status the API reports, which is not always the status stored on the row.
# `parked` says a call is in flight; the row spells that `in_progress`, the value
# routes/calls.py already writes for a web call awaiting its webhook.
COMPLETED: Final[str] = "completed"
PARKED_RUN: Final[str] = "parked"
FAILED_RUN: Final[str] = "failed"
BLOCKED_RUN: Final[str] = "blocked"

_STORED_STATUS: Final[dict[str, str]] = {
    COMPLETED: "completed",
    PARKED_RUN: "in_progress",
    FAILED_RUN: "failed",
    BLOCKED_RUN: "blocked",
}


@dataclass(frozen=True)
class RunResult:
    call_log_id: str
    status: str
    execution_log: list[dict[str, Any]]

    @property
    def needs_review(self) -> bool:
        return self.status != COMPLETED


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def _walk(ctx: RunContext, roots: list[Node], visited: set[str]) -> str | None:
    """Execute from `roots` outwards. Returns the parked node id, if any.

    Depth-first, children in the order the builder stored their edges, so a
    replayed run produces the same log.

    A parked node does not stop the walk — it stops *its* branch. A graph that
    fans out to a call and to something else should still do the something else,
    and a `break` here would silently make the rest of the graph depend on
    whether a call node happened to be visited first.
    """
    parked_at: str | None = None
    stack = list(reversed(roots))
    executed = 0

    while stack:
        node = stack.pop()

        if node.id in visited:
            # A join, or an edge back into the run. Either way it does not run
            # twice: a graph where "call the patient" is reachable by two paths
            # must not call twice because both were drawn.
            ctx.log.record(
                node_id=node.id,
                node_type=node.node_type,
                label=node.label,
                status=SKIPPED,
                message="Already executed in this run; not repeated.",
            )
            continue
        visited.add(node.id)

        executed += 1
        if executed > MAX_STEPS:
            ctx.require_review("the run hit the step ceiling")
            ctx.log.record(
                node_type=RUN_FINISHED,
                label="Step limit reached",
                status=FAILED,
                message=(
                    f"Stopped after {MAX_STEPS} steps. The graph is either much "
                    f"larger than intended or it loops."
                ),
            )
            return parked_at

        outcome = run_node(ctx, node)
        ctx.log.record(
            node_id=node.id,
            node_type=node.node_type,
            label=node.label,
            status=outcome.status,
            message=outcome.message,
            branch=outcome.branch,
            entity=outcome.entity,
        )

        if outcome.status in HALTING:
            # A failed step halts its branch. The nodes after it do not run —
            # "send the summary" after a call that never connected is the shape
            # of bug this is here to prevent.
            continue

        if outcome.status == PARKED:
            parked_at = node.id
            continue

        stack.extend(reversed(ctx.graph.children(node, outcome.branch)))

    return parked_at


def _report_status(log: ExecutionLog, parked_at: str | None) -> str:
    if parked_at:
        return PARKED_RUN
    if log.has_status(FAILED):
        return FAILED_RUN
    if log.has_status(BLOCKED):
        return BLOCKED_RUN
    return COMPLETED


# ---------------------------------------------------------------------------
# Starting a run
# ---------------------------------------------------------------------------


def execute_workflow(
    scope: TenantScope,
    *,
    workflow: dict,
    patient: dict,
    trigger_node_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunResult:
    """Walk `workflow` for `patient`, and record what happened.

    Raises GraphError before anything is created if the graph cannot be executed
    as written. That ordering is deliberate: a malformed workflow should not
    leave a run record behind, because a row whose log says only "the graph was
    invalid" is noise in the review queue.
    """
    settings = get_settings()
    graph = parse_graph(workflow)
    trigger = select_trigger(graph, trigger_node_type)
    metadata = dict(metadata or {})

    # Before anything else happens. See the module docstring.
    call_log = scope.insert_owned(
        "call_logs",
        {
            "patient_id": patient.get("id"),
            "workflow_id": workflow.get("id"),
            "trigger_node": trigger.node_type,
            "status": "running",
            "execution_log": [],
        },
    )
    call_log_id = str(call_log["id"])

    log = ExecutionLog()
    log.record(
        node_type=RUN_STARTED,
        label="Run started",
        status=OK,
        message=(
            f"Workflow {workflow.get('name') or 'unnamed'!r} at graph "
            f"{graph.fingerprint}, triggered by {trigger.node_type}"
        ),
        # Carried so the resume path can rebuild this run without the request
        # that started it. `fingerprint` is what lets a resume notice the
        # workflow was edited while the phone was ringing.
        data={
            "fingerprint": graph.fingerprint,
            "trigger_node_type": trigger.node_type,
            "metadata": metadata,
        },
    )

    ctx = RunContext(
        scope=scope,
        workflow=workflow,
        patient=dict(patient),
        graph=graph,
        call_log_id=call_log_id,
        log=log,
        settings=settings,
        metadata=metadata,
    )

    try:
        parked_at = _walk(ctx, [trigger], visited=set())
    except Exception:
        # A bug in a handler, not a workflow drawn wrong. Record it on the row so
        # the run is not left saying "running" for ever, then re-raise: the
        # caller gets a 500 with an incident id, which is the right answer for
        # something we have to fix.
        log.record(
            node_type=RUN_FINISHED,
            label="Run failed",
            status=FAILED,
            message="The run stopped on an unexpected error.",
        )
        _persist(scope, call_log_id, log=log, status=FAILED_RUN, needs_review=True)
        raise

    status = _report_status(log, parked_at)
    log.record(
        node_type=RUN_FINISHED,
        label="Run finished" if status != PARKED_RUN else "Run parked",
        status=OK if status == COMPLETED else status,
        message=_finish_message(ctx, status, parked_at),
    )

    _persist(
        scope,
        call_log_id,
        log=log,
        status=status,
        needs_review=status != COMPLETED or bool(ctx.review_reasons),
    )

    scope.record_audit(
        action="workflow.execute",
        entity_type="workflow",
        entity_id=str(workflow.get("id") or ""),
        patient_id=str(patient.get("id") or "") or None,
        # PHI-free by policy: the trail records that a run happened and what it
        # decided, never the clinical values it decided on. Those live in
        # execution_log, on the tenant's own row.
        metadata={
            "call_log_id": call_log_id,
            "trigger_node_type": trigger.node_type,
            "graph_fingerprint": graph.fingerprint,
            "status": status,
            "call_placed": ctx.call_placed,
            "steps": len(log.steps),
        },
    )

    logger.info(
        "Workflow run %s: workflow=%s patient=%s status=%s call_placed=%s",
        call_log_id,
        workflow.get("id"),
        patient.get("id"),
        status,
        ctx.call_placed,
    )
    return RunResult(call_log_id=call_log_id, status=status, execution_log=log.as_list())


def _finish_message(ctx: RunContext, status: str, parked_at: str | None) -> str:
    if status == PARKED_RUN:
        message = f"Parked at node {parked_at}, waiting for the post-call webhook."
    elif status == COMPLETED:
        message = "Completed."
    else:
        message = f"Stopped: {status}."
    if ctx.review_reasons:
        message += " For review: " + "; ".join(ctx.review_reasons) + "."
    return message


def _persist(
    scope: TenantScope,
    call_log_id: str,
    *,
    log: ExecutionLog,
    status: str | None,
    needs_review: bool,
) -> None:
    """Write the log and the run's state back to its row.

    One update rather than one per step. A run that dies mid-walk therefore
    leaves its row saying "running" with an empty log, which is worse for
    debugging than incremental writes and much better for the database: a
    twenty-node graph would otherwise be twenty round trips, each rewriting the
    whole JSONB array.
    """
    updates: dict[str, Any] = {
        "execution_log": log.as_list(),
        "needs_review": needs_review,
    }
    if status is not None:
        updates["status"] = _STORED_STATUS[status]
    scope.update_owned("call_logs", call_log_id, updates)


# ---------------------------------------------------------------------------
# Resuming a parked run
# ---------------------------------------------------------------------------


class ResumeSkipped(Exception):
    """There was nothing to resume, and that is not an error.

    A web call has no workflow. A webhook delivered twice has already been
    resumed. Both are ordinary, and both must leave the webhook answering 204 —
    a provider retries on anything else.
    """


def resume_run(
    scope: TenantScope, call_log: dict, result: CallResult, workflow: dict
) -> RunResult:
    """Continue a parked run from the node that parked it.

    `scope` is built from the doctor_id on the stored call log rather than from
    anything the webhook sent — see `app.db.system.tenant_scope_for_row`. Every
    write below therefore goes through the same tenant checks an authenticated
    request would.
    """
    call_log_id = str(call_log.get("id"))
    log = ExecutionLog.from_stored(call_log.get("execution_log"))

    if log.contains(RUN_RESUMED):
        raise ResumeSkipped("this run has already been resumed")

    parked = _last_parked_step(log)
    if parked is None:
        raise ResumeSkipped("this run is not parked at a node")

    started = _run_started_data(log)
    graph = parse_graph(workflow)

    stored_fingerprint = started.get("fingerprint")
    if stored_fingerprint and stored_fingerprint != graph.fingerprint:
        # The workflow was edited while the call was in flight. Resuming would
        # execute a graph this run did not start on, and there is no stored copy
        # of the one it did — workflows are mutable and versions are not kept.
        # Refuse and hand it to a person, who can at least see both.
        log.record(
            node_type=RUN_RESUMED,
            label="Not resumed",
            status=BLOCKED,
            message=(
                f"The workflow changed while the call was in progress "
                f"(started on graph {stored_fingerprint}, now {graph.fingerprint}). "
                f"The rest of the run needs a human rather than a graph it did "
                f"not begin on."
            ),
        )
        _persist(scope, call_log_id, log=log, status=None, needs_review=True)
        return RunResult(
            call_log_id=call_log_id, status=BLOCKED_RUN, execution_log=log.as_list()
        )

    patient_id = call_log.get("patient_id")
    if not patient_id:
        raise ResumeSkipped("this run has no patient to act on")
    patient = scope.get_owned("patients", str(patient_id))

    parked_node = graph.nodes.get(str(parked.get("node_id")))
    if parked_node is None:
        raise ResumeSkipped(
            f"the node this run parked at ({parked.get('node_id')}) is no longer "
            f"in the graph"
        )

    metadata = started.get("metadata")
    ctx = RunContext(
        scope=scope,
        workflow=workflow,
        patient=dict(patient),
        graph=graph,
        call_log_id=call_log_id,
        log=log,
        settings=get_settings(),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
        call_result=result,
        # The call this run parked on has been placed. Without this a second
        # call_patient node downstream would look like the first.
        call_placed=True,
    )

    log.record(
        node_type=RUN_RESUMED,
        label="Run resumed",
        status=OK,
        message=(
            f"Post-call webhook received: outcome "
            f"{result.call_outcome or 'unknown'}, reached patient "
            f"{result.reached_patient}, confirmed {result.patient_confirmed}."
        ),
    )

    # The visited set comes from the log rather than from anywhere in memory,
    # which is the whole reason a resume needs no state carried between
    # requests.
    visited = _visited_from(log)
    parked_at = _walk(ctx, ctx.graph.children(parked_node), visited)

    status = _report_status(log, parked_at)
    log.record(
        node_type=RUN_FINISHED,
        label="Run finished" if status != PARKED_RUN else "Run parked",
        status=OK if status == COMPLETED else status,
        message=_finish_message(ctx, status, parked_at),
    )

    # `status` is not written back unless the run parked again. The webhook has
    # already recorded the call as completed, and a downstream step failing
    # afterwards does not make the call not have happened. The failure is in the
    # log and in needs_review, where it belongs.
    _persist(
        scope,
        call_log_id,
        log=log,
        status=PARKED_RUN if status == PARKED_RUN else None,
        needs_review=(
            status != COMPLETED or bool(ctx.review_reasons) or result.needs_human_review
        ),
    )

    logger.info(
        "Resumed run %s: status=%s steps=%d", call_log_id, status, len(log.steps)
    )
    return RunResult(
        call_log_id=call_log_id, status=status, execution_log=log.as_list()
    )


def _last_parked_step(log: ExecutionLog) -> dict[str, Any] | None:
    for step in reversed(log.steps):
        if step.get("status") == PARKED and step.get("node_id"):
            return step
    return None


def _run_started_data(log: ExecutionLog) -> dict[str, Any]:
    for step in log.steps:
        if step.get("node_type") == RUN_STARTED:
            data = step.get("data")
            return data if isinstance(data, dict) else {}
    return {}


def _visited_from(log: ExecutionLog) -> set[str]:
    """Every node the run has already reached, whatever the outcome was.

    Status is not consulted. A node that returned `skipped` still ran, and a
    resume that let it run again would repeat whatever it decided not to do —
    which for `schedule_appointment` means a second look at a call result that
    has not changed.
    """
    return {str(step["node_id"]) for step in log.steps if step.get("node_id")}


def graph_fingerprint(workflow: dict) -> str:
    """Exposed for callers that want to pin a graph without walking it."""
    return fingerprint(workflow.get("nodes"), workflow.get("edges"))


__all__ = [
    "BLOCKED_RUN",
    "COMPLETED",
    "FAILED_RUN",
    "Graph",
    "GraphError",
    "PARKED_RUN",
    "ResumeSkipped",
    "RunResult",
    "execute_workflow",
    "graph_fingerprint",
    "resume_run",
]
