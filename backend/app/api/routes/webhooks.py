"""Provider webhooks.

These routes are unauthenticated in the JWT sense — ElevenLabs has no user
token — so the signature is the entire access control. Nothing in the payload
is trusted, and nothing is written, until it verifies.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, Response, status

from app.api.deps import RawBodyDep, SupabaseDep
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.system import (
    get_workflow_by_id,
    tenant_scope_for_row,
    update_call_log_by_conversation,
)
from app.engine.runner import ResumeSkipped, resume_run
from app.events.broker import Event, broker
from app.integrations.elevenlabs.webhook import (
    CallResult,
    WebhookVerificationError,
    loads_raw,
    parse_post_call_payload,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/elevenlabs/webhook", status_code=status.HTTP_204_NO_CONTENT)
def elevenlabs_post_call(
    raw_body: RawBodyDep,
    client: SupabaseDep,
    elevenlabs_signature: str | None = Header(default=None),
) -> Response:
    """Receive a post-call result from ElevenLabs.

    Always answers 204 once the signature is valid, including for calls this
    system does not recognise. A webhook endpoint that reports whether a
    conversation id exists is an oracle, and providers retry on non-2xx, so
    surfacing our own bookkeeping problems as errors just produces a retry
    storm that fixes nothing.
    """
    settings = get_settings()

    try:
        verify_signature(
            raw_body=raw_body,
            signature_header=elevenlabs_signature,
            secret=settings.elevenlabs_webhook_secret,
            tolerance_seconds=settings.webhook_tolerance_seconds,
        )
    except WebhookVerificationError as exc:
        # 401 with no detail. Telling an unverified caller why verification
        # failed helps them iterate towards a valid forgery.
        logger.warning("Rejected ElevenLabs webhook: %s", exc)
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = loads_raw(raw_body)
    except WebhookVerificationError as exc:
        logger.warning("Signed ElevenLabs webhook had an unreadable body: %s", exc)
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    event_type = payload.get("type")
    if event_type != "post_call_transcription":
        # Audio and failure events are signed and legitimate, just not consumed
        # here yet. Acknowledge so the provider stops retrying.
        logger.info("Ignoring ElevenLabs webhook of type %s", event_type)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    result = parse_post_call_payload(payload)
    if not result.conversation_id:
        logger.warning("post_call_transcription with no conversation_id")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    updates = {
        "status": "completed",
        "outcome": result.call_outcome,
        "patient_confirmed": result.patient_confirmed,
        "reached_patient": result.reached_patient,
        "confirmed_date": result.confirmed_date,
        "confirmed_time": result.confirmed_time,
        "availability_notes": result.patient_availability_notes,
        "callback_requested": result.callback_requested,
        "transcript": result.transcript,
        "data_collection": result.raw_data_collection,
        "needs_review": result.needs_human_review,
        "webhook_received_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        row = update_call_log_by_conversation(client, result.conversation_id, updates)
    except NotFound:
        # A conversation we have no record of. Worth investigating — it means a
        # call was placed that we did not log — but not worth a retry.
        logger.warning(
            "No call log for ElevenLabs conversation %s", result.conversation_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    logger.info(
        "Recorded call outcome: conversation=%s outcome=%s confirmed=%s review=%s",
        result.conversation_id,
        result.call_outcome,
        result.patient_confirmed,
        result.needs_human_review,
    )

    # The call was the middle of a workflow, not the end of one. Continuing it
    # here is what turns "the patient agreed to Tuesday at two thirty" into an
    # appointment; before this line existed, that agreement was recorded and
    # then nothing acted on it.
    _resume_workflow(client, row, result)

    # Nudge any open stream belonging to the tenant that owns this call. The id
    # comes from the stored row, never from the payload — the webhook is
    # unauthenticated, so nothing it sends may decide who gets told.
    #
    # After the write, after the log line, and after the resume: a notification
    # is worth nothing if the re-fetch it triggers cannot yet see the change,
    # and the resume writes more than the outcome did.
    broker.publish(
        row.get("doctor_id", ""), Event("call_log.updated", str(row.get("id", "")))
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _resume_workflow(client: object, row: dict, result: CallResult) -> None:
    """Continue the parked workflow run this call belonged to.

    Never raises. Two reasons, and they point the same way: the outcome is
    already recorded, so failing here would discard a successful write; and
    ElevenLabs retries on a non-2xx, so an exception becomes a retry storm that
    re-runs the resume it just failed. The run is left parked and flagged for
    review instead, which is a person's problem rather than a lost call.

    A call with no `workflow_id` — every web call from `routes/calls.py` — has
    nothing to resume and is not an error.
    """
    workflow_id = row.get("workflow_id")
    if not workflow_id:
        return

    call_log_id = row.get("id")
    try:
        workflow = get_workflow_by_id(client, str(workflow_id))
        # The tenant comes from the stored row's doctor_id, never from the
        # payload. See app/db/system.py for the provenance argument.
        scope = tenant_scope_for_row(client, row)
        run = resume_run(scope, row, result, workflow)
    except ResumeSkipped as exc:
        logger.info("Not resuming call log %s: %s", call_log_id, exc)
    except NotFound:
        logger.warning(
            "Call log %s references workflow %s, which no longer exists",
            call_log_id,
            workflow_id,
        )
    except Exception:  # noqa: BLE001 - see the docstring
        logger.exception("Resuming the run for call log %s failed", call_log_id)
    else:
        logger.info("Resumed run for call log %s: %s", call_log_id, run.status)
