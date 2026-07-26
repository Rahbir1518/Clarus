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
from app.db.system import update_call_log_by_conversation
from app.integrations.elevenlabs.webhook import (
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
        update_call_log_by_conversation(client, result.conversation_id, updates)
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
    return Response(status_code=status.HTTP_204_NO_CONTENT)
