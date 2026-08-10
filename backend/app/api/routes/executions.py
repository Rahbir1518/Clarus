"""Starting workflow runs.

    POST /api/workflows/{workflow_id}/execute   run one, named explicitly
    POST /api/lab-event                         fan one event out to whatever listens

Two routers in one module, the way clinical.py holds two, because the pair is one
idea: something happened, walk the graphs that care. They differ in who chose the
workflow, and that difference decides one rule.

**`/execute` will run a DRAFT workflow. `/lab-event` will not.** A doctor pressing
Run in the builder is testing something they are looking at, and refusing to
execute it until it is enabled would make the builder's own Run button useless.
An event arriving from a lab feed chose nothing — it fans out to every workflow
that listens, so a half-drawn draft being in that set would mean a workflow
starts phoning patients before anyone decided it was finished. ARCHIVED is
refused on both: a retired workflow is kept so its old call logs still point at
something, not so it can run again.

Both paths converge on `app.engine.runner.execute_workflow`, which creates the
`call_logs` row before any node runs. Nothing here places a call itself.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import TenantDep
from app.engine.graph import GraphError, parse_graph
from app.engine.runner import RunResult, execute_workflow
from app.schemas.execution import (
    ExecuteWorkflow,
    LabEvent,
    LabEventResult,
    RunRead,
    UnrunnableWorkflow,
)

logger = logging.getLogger(__name__)

workflow_router = APIRouter(prefix="/workflows", tags=["workflows"])
lab_event_router = APIRouter(tags=["workflows"])

# A workflow in this state is not run by either path.
_RETIRED = "ARCHIVED"


def _as_run_read(result: RunResult, workflow_id: str) -> RunRead:
    return RunRead(
        call_log_id=result.call_log_id,
        status=result.status,
        execution_log=result.execution_log,
        workflow_id=workflow_id,
    )


@workflow_router.post("/{workflow_id}/execute", response_model=RunRead)
def run_workflow(
    workflow_id: str, payload: ExecuteWorkflow, scope: TenantDep
) -> RunRead:
    """Walk one workflow for one patient.

    Both ids are resolved through the caller's own scope first, so a workflow or
    a patient belonging to another practice is a 404 before a run record exists.

    200 rather than 201. A run that was blocked by policy or that failed on its
    first node has still been recorded and still returns its log — the response
    describes what happened, and a 201 claiming creation would be answering a
    different question. Read `status`.
    """
    workflow = scope.get_owned("workflows", workflow_id)
    if workflow.get("status") == _RETIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workflow is archived. Restore it to DRAFT or ENABLED to run it.",
        )

    patient = scope.get_owned("patients", payload.patient_id)

    try:
        result = execute_workflow(
            scope,
            workflow=workflow,
            patient=patient,
            trigger_node_type=payload.trigger_node_type,
            metadata=payload.metadata,
        )
    except GraphError as exc:
        # The workflow cannot be walked as drawn. 422 rather than 500: the
        # request was fine and the stored graph is not, which is something the
        # caller can fix in the builder.
        raise HTTPException(
            status_code=422, detail=f"This workflow cannot be run: {exc}"
        ) from exc

    return _as_run_read(result, workflow_id)


@lab_event_router.post("/lab-event", response_model=LabEventResult)
def lab_event(payload: LabEvent, scope: TenantDep) -> LabEventResult:
    """Fan one event out to every enabled workflow that listens for it.

    The trigger simulation the dashboard uses, and the shape a real lab feed
    would take: a trigger type, a patient, and the event body.

    Matching a workflow means parsing its graph and looking for a trigger node of
    this type. It is not a stored subscription, which would be faster and would
    also be a second copy of something the graph already says — and the two would
    disagree the first time somebody changed a trigger node without re-saving
    whatever kept the index.

    Nothing matching is a 200 with `matched: 0`. An event that no workflow listens
    for is an ordinary thing for a lab feed to deliver.
    """
    patient = scope.get_owned("patients", payload.patient_id)

    runs: list[RunRead] = []
    unrunnable: list[UnrunnableWorkflow] = []

    for workflow in scope.list_owned("workflows", filters={"status": "ENABLED"}):
        workflow_id = str(workflow.get("id"))
        try:
            graph = parse_graph(workflow)
        except GraphError as exc:
            # Only reported if it was going to be relevant. Every enabled
            # workflow is parsed here, and listing the broken ones that do not
            # listen for this trigger would make an unrelated draft look like the
            # reason nothing happened.
            if _mentions_trigger(workflow, payload.trigger_type):
                unrunnable.append(
                    UnrunnableWorkflow(
                        workflow_id=workflow_id,
                        name=workflow.get("name"),
                        reason=str(exc),
                    )
                )
            continue

        if not any(n.node_type == payload.trigger_type for n in graph.triggers):
            continue

        try:
            result = execute_workflow(
                scope,
                workflow=workflow,
                patient=patient,
                trigger_node_type=payload.trigger_type,
                metadata=payload.metadata,
            )
        except GraphError as exc:
            # Reachable when the graph parses but the trigger is ambiguous — two
            # nodes of the same type, so which one starts the run is undecidable.
            unrunnable.append(
                UnrunnableWorkflow(
                    workflow_id=workflow_id, name=workflow.get("name"), reason=str(exc)
                )
            )
            continue

        runs.append(_as_run_read(result, workflow_id))

    logger.info(
        "Lab event %s for patient %s: %d run(s), %d unrunnable",
        payload.trigger_type,
        payload.patient_id,
        len(runs),
        len(unrunnable),
    )
    return LabEventResult(
        trigger_type=payload.trigger_type,
        patient_id=payload.patient_id,
        matched=len(runs),
        runs=runs,
        unrunnable=unrunnable,
    )


def _mentions_trigger(workflow: dict, trigger_type: str) -> bool:
    """Whether an unparseable graph looks like it listens for this trigger.

    Deliberately crude: the graph did not parse, so there is nothing structured
    left to ask. This only decides whether to mention the workflow in the
    response, never whether to run it.
    """
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        data = node.get("data") if isinstance(node, dict) else None
        if isinstance(data, dict) and data.get("nodeType") == trigger_type:
            return True
    return False
