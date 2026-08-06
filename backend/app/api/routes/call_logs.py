"""Call log reads.

Read-only by design. A call log is a record of something that happened on a
phone line: it is created by the workflow engine when a call is placed and
completed by the provider webhook when the call ends. Nothing a browser does
should be able to author one, so there is no POST and no PUT here.

Marking a call reviewed is the one client-driven change the review queue needs,
and it belongs on its own narrow route rather than a general update — see
`needs_review` in migrations/002_call_outcomes.sql. It is not built yet.

Follows the shape set by routes/patients.py.
"""
from fastapi import APIRouter

from app.api.deps import TenantDep
from app.schemas.call_log import CallLogRead, CallLogSummary

router = APIRouter(prefix="/call-logs", tags=["call-logs"])


@router.get("", response_model=list[CallLogSummary])
def list_call_logs(
    scope: TenantDep,
    workflow_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List the caller's call logs, newest first.

    The frontend also sends ?doctor_id=... — undeclared, unread, no effect.
    Scoping comes from the token.

    No transcripts in the response; see schemas/call_log.py.
    """
    return scope.list_owned(
        "call_logs", filters={"workflow_id": workflow_id, "status": status}
    )


@router.get("/{call_log_id}", response_model=CallLogRead)
def get_call_log(call_log_id: str, scope: TenantDep) -> dict:
    """One call, including its transcript.

    Audited, and this is the read worth auditing. PHIPA wants a record of
    access rather than only of change, and opening a specific call is someone
    reading a conversation with a named patient — which the list of statuses
    that preceded it is not.

    The audit row goes in after the read succeeds. Recording an access that
    404'd would put calls the caller never saw, and does not own, into their
    own trail.
    """
    row = scope.get_owned("call_logs", call_log_id)
    scope.record_audit(
        action="read",
        entity_type="call_log",
        entity_id=row["id"],
        patient_id=row.get("patient_id"),
        # No transcript, no outcome, nothing about the conversation. The trail
        # records that an access happened, not a second copy of what was
        # accessed — it lands in the same log exports as everything else.
        metadata={"has_transcript": bool(row.get("transcript"))},
    )
    return row
