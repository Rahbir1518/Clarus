"""Placing calls.

Two routes, and between them they close the gap that made routes/call_logs.py
read-only: something has to create the call log a provider webhook later
completes.

    POST /api/calls/web              start a browser conversation
    POST /api/calls/web/{id}/bind    report the conversation id back
    GET  /api/calls/web/pending      workflow calls waiting to be answered
    POST /api/calls/web/{id}/answer  answer one of them

The last two exist for CALL_TRANSPORT=web, where a workflow's call_patient
node dials nothing and parks instead. Answering hands the browser the
variables the run stored when it parked, and from there it is the same path as
the first two: bind on connect, and the webhook resumes the run.

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

from fastapi import APIRouter, status

from app.api.deps import TenantDep
from app.core.errors import Conflict
from app.engine.policy import call_language, resolve_call_reason
from app.integrations.elevenlabs.client import ElevenLabsClient, agent_for_phone
from app.integrations.elevenlabs.variables import build_dynamic_variables
from app.integrations.elevenlabs.webhook import AWAITING_BROWSER
from app.schemas.call import (
    BindConversation,
    PendingWebCall,
    StartWebCall,
    WebCallStarted,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])


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

    # The reason is resolved from a fixed vocabulary, not taken as text. Same
    # rule the workflow engine's call_patient node follows, for the same reason:
    # anything here is spoken to a patient.
    variables = build_dynamic_variables(
        patient=patient,
        appointment_reason=resolve_call_reason(
            body.model_dump(), call_language(patient.get("phone"))
        ),
        practice=scope.practice_settings(),
    )

    # After the insert: a token minted for a call log that failed to write is a
    # conversation whose outcome has nowhere to go. The agent speaks the
    # patient's language, chosen by their number.
    token = ElevenLabsClient().conversation_token(agent_for_phone(patient.get("phone")))

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


@router.get("/web/pending", response_model=list[PendingWebCall])
def list_pending_web_calls(scope: TenantDep) -> list[dict]:
    """Workflow calls parked on CALL_TRANSPORT=web, newest first.

    A row stops being pending the moment a conversation is bound to it, so a
    call already answered in another tab is not offered twice.
    """
    rows = scope.list_owned("call_logs", filters={"outcome": AWAITING_BROWSER})
    return [
        {
            "call_log_id": str(row["id"]),
            "patient_id": row.get("patient_id"),
            "workflow_id": row.get("workflow_id"),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if not row.get("conversation_id")
    ]


@router.post("/web/{call_log_id}/answer", response_model=WebCallStarted)
def answer_web_call(call_log_id: str, scope: TenantDep) -> dict:
    """Answer a parked workflow call: a token, and the variables it stored.

    The variables come off the row, exactly as the run built them — never from
    the request, which has no body. 409 for a row that is not waiting to be
    answered, including one already bound to a conversation: answering it again
    would open a second conversation whose outcome has nowhere to go.

    Answering twice before binding is harmless. It mints a second token; the
    first conversation to bind wins, and the other's bind is a 409.
    """
    row = scope.get_owned("call_logs", call_log_id)
    variables = row.get("call_variables")
    if (
        row.get("outcome") != AWAITING_BROWSER
        or row.get("conversation_id")
        or not isinstance(variables, dict)
        or not variables
    ):
        raise Conflict("This call is not waiting to be answered")

    # Same language rule as the run that parked this call used for its reason.
    patient = scope.get_owned("patients", row["patient_id"]) if row.get("patient_id") else {}
    token = ElevenLabsClient().conversation_token(agent_for_phone(patient.get("phone")))

    logger.info("Web call answered: call_log=%s", call_log_id)
    return {
        "call_log_id": str(row["id"]),
        "token": token,
        "dynamic_variables": {str(k): str(v) for k, v in variables.items()},
    }
