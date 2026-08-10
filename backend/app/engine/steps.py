"""The shape of `call_logs.execution_log`.

One decision, recorded here because the column is JSONB and the database will
therefore accept anything at all. `execution_log` is a **flat, append-only JSON
array of step objects**, oldest first:

    [
      {"seq": 0, "node_id": null, "node_type": "run.started",
       "label": "Run started", "status": "ok", "at": "2026-08-09T18:22:01Z",
       "message": "Workflow 'Lab follow-up' (fingerprint 4f2a1c9e), trigger lab_results_received",
       "branch": null, "entity": null},
      {"seq": 1, "node_id": "n1", "node_type": "lab_results_received", ...},
      ...
    ]

Why flat and not a tree, when the graph branches: the log answers "what
happened, in order", and a reader following a run down a branch wants the
sequence they would have watched. The branch a conditional took is recorded on
the conditional's own step, so the shape of the walk is recoverable without
nesting it.

Why append-only: a step is a fact about a moment. Rewriting one to reflect a
later outcome is how a log stops being evidence. The parked call step stays
`parked` forever; the webhook appends `run.resumed` after it rather than editing
it.

`seq` rather than relying on array position, because the array is written across
two requests — the execute call and the webhook that resumes it — and a reader
that assumes position is index has no way to notice a gap.

Field names are not free. `status`, `label`, `node_type` and `message` are read
directly by the run panel in `frontend/components/workflow/WorkflowBuilder.tsx`.
Renaming one silently empties a line in the UI rather than failing.

Clinical values are allowed in `message`. See the destinations table in
AI_CALL_SAFETY_POLICY.md — this log is the run's own tenant-scoped record and a
run that branched on a value has to be able to say which value. `audit_log`
metadata and SSE events are the ones that must stay clean.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final

# A step's terminal state. Five, and the distinctions between them are load
# bearing rather than descriptive:
#
#   ok       — did its work
#   skipped  — did not apply, and that is a normal outcome. The branch continues.
#   blocked  — a safety rule refused it. The branch halts. See policy.py.
#   failed   — it tried and could not. The branch halts.
#   parked   — waiting on the outside world. The whole walk stops here and
#              resumes from a webhook.
#
# blocked and failed are separate because they mean different things to whoever
# reads the log: blocked is the system working as designed and is a question for
# the workflow's author, failed is the system not working and is a question for
# us. Collapsing them would bury one in the other.
OK: Final[str] = "ok"
SKIPPED: Final[str] = "skipped"
BLOCKED: Final[str] = "blocked"
FAILED: Final[str] = "failed"
PARKED: Final[str] = "parked"

# Statuses that stop the branch they are on. A failed step must not let the
# nodes after it run — "send the summary" after a call that never connected is
# the shape of bug this prevents.
HALTING: Final[frozenset[str]] = frozenset({BLOCKED, FAILED})

# Statuses that mean a human has to look at this run.
NEEDS_REVIEW: Final[frozenset[str]] = frozenset({BLOCKED, FAILED, PARKED})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Step:
    """One entry in the execution log."""

    seq: int
    node_type: str
    label: str
    status: str
    message: str
    at: str
    node_id: str | None = None
    # Which handle a conditional left by, "true" or "false". None on every
    # other kind of node, and None is different from "false".
    branch: str | None = None
    # A row this step created, as {"table": ..., "id": ...}. Never the row
    # itself: the log is read by the builder UI and an id is enough to find it
    # through the ordinary audited route.
    entity: dict[str, str] | None = None
    # Run-level context, set on `run.started` and nowhere else. It holds the
    # graph fingerprint and the triggering event, which is what lets the webhook
    # rebuild a parked run without any state carried between the two requests.
    #
    # Not a general-purpose payload. A node step putting its own data here would
    # make the log a place to look things up rather than a record of what
    # happened, and the next question would be which steps can be trusted to
    # have it.
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "at": self.at,
            "branch": self.branch,
            "entity": self.entity,
            "data": self.data,
        }


@dataclass
class ExecutionLog:
    """Accumulates steps for one run, across however many requests it spans.

    Constructed empty for a new run and from the stored array when a webhook
    resumes a parked one, so `seq` keeps counting rather than restarting.
    """

    steps: list[dict[str, Any]] = field(default_factory=list)
    _next_seq: int = 0

    @classmethod
    def from_stored(cls, stored: Any) -> "ExecutionLog":
        """Rebuild from whatever is in the column.

        Tolerant on purpose. This runs on the resume path, where the input is a
        JSONB value written by an earlier version of this code, and a run that
        cannot be resumed because its log is an unexpected shape is a call whose
        outcome is silently dropped. A log that cannot be read is replaced by
        one that can, and the run continues.
        """
        steps = [s for s in stored if isinstance(s, dict)] if isinstance(stored, list) else []
        highest = -1
        for step in steps:
            seq = step.get("seq")
            if isinstance(seq, int) and seq > highest:
                highest = seq
        return cls(steps=steps, _next_seq=highest + 1)

    def record(
        self,
        *,
        node_type: str,
        label: str,
        status: str,
        message: str,
        node_id: str | None = None,
        branch: str | None = None,
        entity: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Step:
        step = Step(
            seq=self._next_seq,
            node_id=node_id,
            node_type=node_type,
            label=label,
            status=status,
            message=message,
            at=_now_iso(),
            branch=branch,
            entity=entity,
            data=data,
        )
        self._next_seq += 1
        self.steps.append(step.to_dict())
        return step

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.steps)

    def contains(self, node_type: str) -> bool:
        """Whether a step of this type has already been recorded.

        The resume path's idempotency check: providers deliver webhooks twice,
        and a second delivery must not walk the graph again.
        """
        return any(step.get("node_type") == node_type for step in self.steps)

    def has_status(self, *statuses: str) -> bool:
        wanted = set(statuses)
        return any(step.get("status") in wanted for step in self.steps)
