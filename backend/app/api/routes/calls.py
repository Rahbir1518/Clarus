"""Placing calls.

Two routes, and between them they close the gap that made routes/call_logs.py
read-only: something has to create the call log a provider webhook later
completes.

    POST /api/calls/web            start a browser conversation
    POST /api/calls/web/{id}/bind  report the conversation id back

Why two, rather than one that does everything: a WebRTC session is opened by
the browser, so the conversation id is minted there. On the phone path
ElevenLabs returns it to the server at queue time, and there is nothing to
report. The split is the price of the browser holding the session.

The transport is the only thing that differs. Same agent, same dynamic
variables, same webhook, same call_logs row — see the note at the foot of
app/integrations/elevenlabs/client.py. Nothing downstream of here knows or
cares whether a call arrived over WebRTC or a phone line, and it must stay that
way: the moment the webhook grows an `if channel == "web"`, the phone path
stops being swappable.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, status

from app.api.deps import TenantDep
from app.core.config import get_settings
from app.integrations.elevenlabs.client import ElevenLabsClient
from app.schemas.call import BindConversation, StartWebCall, WebCallStarted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


def build_dynamic_variables(
    *, patient: dict, body: StartWebCall, doctor_id: str
) -> dict[str, str]:
    """Every {{placeholder}} the agent prompt references.

    Must stay in step with agents/*.yaml. A name missing here is not an error
    at the API — it reaches the patient as the literal text "{{patient_name}}",
    spoken aloud. scripts/test_call.py has the same list for the phone path;
    if you add a placeholder to the spec, both change.

    Values are strings because ElevenLabs accepts nothing else.
    """
    settings = get_settings()
    return {
        "patient_name": str(patient.get("name") or "there"),
        # TODO: read these off the doctors row once it carries them. Hardcoded
        # here rather than accepted from the request on purpose — they are
        # spoken to a patient as the identity of the caller.
        "doctor_name": str(patient.get("primary_physician") or "your doctor"),
        "practice_name": "Clarus",
        "appointment_reason": body.appointment_reason,
        "callback_number": body.callback_number,
        "timezone": settings.default_timezone,
        "today_date": date.today().isoformat(),
    }


@router.post("/web", response_model=WebCallStarted, status_code=status.HTTP_201_CREATED)
def start_web_call(body: StartWebCall, scope: TenantDep) -> dict:
    """Create the call log, then mint a token for the browser to talk with.

    Order matters. The row is written first so that a conversation can never
    exist without somewhere to record its outcome; the reverse order loses the
    result of any call whose insert then fails.

    The row starts with conversation_id NULL and needs_review defaulting to
    true, so a session the caller abandons stays visible as an unfinished call
    rather than disappearing.
    """
    # Scoped read: a patient_id belonging to another practice is a 404 here,
    # before anything is created and before any token is minted.
    patient = scope.get_owned("patients", body.patient_id)

    call_log = scope.insert_owned(
        "call_logs",
        {
            "patient_id": body.patient_id,
            "workflow_id": body.workflow_id,
            "status": "in_progress",
            "trigger_node": "web",
        },
    )

    variables = build_dynamic_variables(
        patient=patient, body=body, doctor_id=scope.doctor_id
    )

    # After the insert: a token minted for a call log that failed to write is a
    # conversation whose outcome has nowhere to go.
    token = ElevenLabsClient().conversation_token()

    logger.info(
        "Web call started: call_log=%s patient=%s", call_log["id"], body.patient_id
    )
    return {
        "call_log_id": str(call_log["id"]),
        "token": token,
        "dynamic_variables": variables,
    }


@router.post("/web/{call_log_id}/bind", status_code=status.HTTP_204_NO_CONTENT)
def bind_conversation(
    call_log_id: str, body: BindConversation, scope: TenantDep
) -> None:
    """Attach the conversation id the browser was given to its call log.

    Until this lands, the post-call webhook has no row to resolve and drops the
    outcome on the floor — deliberately, since it may only ever complete a call
    this system initiated. So the browser should call this immediately after
    startSession resolves, not when the conversation ends.

    Write-once and tenant-scoped; see TenantScope.bind_conversation for why
    that matters. 409 on a second, different id.
    """
    scope.bind_conversation(call_log_id, body.conversation_id)
    logger.info(
        "Bound conversation %s to call log %s", body.conversation_id, call_log_id
    )
