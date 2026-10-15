"""Placing calls.

Two routes, and between them they close the gap that made routes/call_logs.py
read-only: something has to create the call log a provider webhook later
completes.

    POST /api/calls/web              start a browser conversation
    POST /api/calls/web/{id}/bind    report the conversation id back
    GET  /api/calls/web/pending      workflow calls waiting to be answered
    POST /api/calls/web/{id}/answer  answer one of them
    POST /api/calls/web/{id}/link    a link the patient can answer it from
    POST /api/calls/web/{id}/email   email the patient that link

The rest exist for CALL_TRANSPORT=web and =email, where a workflow's
call_patient node dials nothing and parks instead. Answering hands the browser
the variables the run stored when it parked, and from there it is the same
path as the first two: bind on connect, and the webhook resumes the run.

A parked call can also be answered by the patient, through a call link (see
app/integrations/call_links.py). Those routes are the second router below,
authenticated by the link instead of a session:

    GET  /api/call-links/{token}          what the link's page shows
    POST /api/call-links/{token}/answer   answer the call it names
    POST /api/call-links/{token}/bind     report the conversation id back

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
import math
import smtplib

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import SupabaseDep, TenantDep
from app.core.config import MissingConfiguration, get_settings
from app.core.errors import Conflict
from app.core.ratelimit import SlidingWindowLimiter, client_ip
from app.db.system import get_call_log_for_link, tenant_scope_for_row
from app.db.tenancy import TenantScope
from app.engine import policy
from app.engine.policy import call_language, resolve_call_reason
from app.integrations.call_links import (
    CallLink,
    ExpiredCallLink,
    InvalidCallLink,
    issue_call_link,
    read_call_link,
    send_call_link,
)
from app.integrations.elevenlabs.client import ElevenLabsClient, agent_for_phone
from app.integrations.elevenlabs.variables import build_dynamic_variables
from app.integrations.elevenlabs.webhook import AWAITING_ANSWER, AWAITING_PATIENT
from app.schemas.call import (
    BindConversation,
    CallLinkInfo,
    CallLinkIssued,
    PendingWebCall,
    StartWebCall,
    WebCallStarted,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])
public_router = APIRouter(prefix="/call-links", tags=["call links"])


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
    """Workflow calls parked to be answered in a browser, newest first —
    including those whose link has been emailed to the patient.

    A row stops being pending the moment a conversation is bound to it, so a
    call already answered in another tab, or by the patient, is not offered
    twice.
    """
    rows = [
        row
        for outcome in AWAITING_ANSWER
        for row in scope.list_owned("call_logs", filters={"outcome": outcome})
    ]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return [
        {
            "call_log_id": str(row["id"]),
            "patient_id": row.get("patient_id"),
            "workflow_id": row.get("workflow_id"),
            "created_at": row.get("created_at"),
            "emailed": row.get("outcome") == AWAITING_PATIENT,
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
    started = _answer(scope, _waiting_call(scope, call_log_id))
    logger.info("Web call answered: call_log=%s", call_log_id)
    return started


@router.post("/web/{call_log_id}/link", response_model=CallLinkIssued)
def get_call_link(call_log_id: str, scope: TenantDep) -> dict:
    """A link the patient can answer this waiting call from, to send however
    staff like — the way to reach a patient when the email did not arrive, or
    on CALL_TRANSPORT=web where none is sent."""
    _waiting_call(scope, call_log_id)
    return _as_issued(_issue_link(call_log_id))


@router.post("/web/{call_log_id}/email", response_model=CallLinkIssued)
def email_call_link(call_log_id: str, scope: TenantDep) -> dict:
    """Email the patient a link to this waiting call.

    The same gates as the call_patient node sending one: the kill switch, a
    usable address, and the allowlist. Afterwards the call counts as an
    attempt on the patient, as one emailed by a workflow does.
    """
    row = _waiting_call(scope, call_log_id)
    settings = get_settings()
    patient = scope.get_owned("patients", row["patient_id"]) if row.get("patient_id") else {}
    try:
        policy.assert_calls_enabled(settings)
        email = policy.assert_emailable(patient.get("email"))
        policy.assert_email_allowed(email, settings)
    except policy.PolicyRefusal as exc:
        raise Conflict(str(exc)) from None

    link = _issue_link(call_log_id)
    try:
        send_call_link(
            to=email,
            link=link,
            practice_name=str(row["call_variables"].get("practice_name") or settings.practice_name),
            language=call_language(patient.get("phone")),
            settings=settings,
        )
    except MissingConfiguration as exc:
        raise _unavailable(exc) from None
    except (smtplib.SMTPException, OSError):
        # Never echo the SMTP error: it can name the account and the server.
        logger.exception("Call link email for call log %s could not be sent", call_log_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The email could not be sent. Copy the link and send it another way.",
        ) from None

    scope.update_owned("call_logs", call_log_id, {"outcome": AWAITING_PATIENT})
    logger.info("Call link emailed: call_log=%s", call_log_id)
    return _as_issued(link)


# ---------------------------------------------------------------------------
# Call links: the patient answers from their own browser
# ---------------------------------------------------------------------------
#
# No session. The signed link is the credential, read_call_link checks it, and
# every query after that goes through the TenantScope of the practice that owns
# the call — the same arrangement as the post-call webhook. Rate limited per
# client, like the contact form, since anyone can send these requests.

link_limiter = SlidingWindowLimiter()
LINK_REQUESTS_PER_IP = 30
LINK_WINDOW_SECONDS = 600


@public_router.get("/{token}", response_model=CallLinkInfo)
def describe_call_link(token: str, request: Request, client: SupabaseDep) -> dict:
    """Enough for the page to greet the patient, in their language, and say
    whether the call can still be answered."""
    scope, row = _resolve_link(token, request, client)
    patient = scope.get_owned("patients", row["patient_id"]) if row.get("patient_id") else {}
    variables = row.get("call_variables") or {}
    if row.get("conversation_id"):
        link_status = "answered"
    elif row.get("outcome") in AWAITING_ANSWER:
        link_status = "ready"
    else:
        link_status = "closed"
    return {
        "status": link_status,
        "practice_name": str(variables.get("practice_name") or get_settings().practice_name),
        "language": call_language(patient.get("phone")),
    }


@public_router.post("/{token}/answer", response_model=WebCallStarted)
def answer_call_link(token: str, request: Request, client: SupabaseDep) -> dict:
    """Answer the call a link names. The same rules as staff answering it:
    only while it waits, with the variables its run stored."""
    scope, row = _resolve_link(token, request, client)
    started = _answer(scope, row)
    logger.info("Call link answered: call_log=%s", row["id"])
    return started


@public_router.post("/{token}/bind", status_code=status.HTTP_204_NO_CONTENT)
def bind_call_link(
    token: str, body: BindConversation, request: Request, client: SupabaseDep
) -> None:
    """Attach the conversation the patient's browser opened, so the webhook can
    resume the run. Write-once, as on the staff route: binding is also what
    spends the link."""
    scope, row = _resolve_link(token, request, client)
    if not row.get("conversation_id") and row.get("outcome") not in AWAITING_ANSWER:
        raise Conflict("This call is not waiting to be answered")
    scope.bind_conversation(str(row["id"]), body.conversation_id)
    logger.info("Call link bound: call_log=%s", row["id"])


# ---------------------------------------------------------------------------
# Shared by both routers
# ---------------------------------------------------------------------------


def _waiting_call(scope: TenantScope, call_log_id: str) -> dict:
    """The caller's call log, if it is waiting to be answered; 404 or 409."""
    row = scope.get_owned("call_logs", call_log_id)
    if row.get("outcome") not in AWAITING_ANSWER or row.get("conversation_id"):
        raise Conflict("This call is not waiting to be answered")
    return row


def _answer(scope: TenantScope, row: dict) -> dict:
    """A token, and the variables the run stored, for a waiting call.

    The variables come off the row exactly as the run built them — never from
    the request. 409 for a row that is not waiting, including one already bound
    to a conversation: answering it again would open a second conversation
    whose outcome has nowhere to go.
    """
    variables = row.get("call_variables")
    if (
        row.get("outcome") not in AWAITING_ANSWER
        or row.get("conversation_id")
        or not isinstance(variables, dict)
        or not variables
    ):
        raise Conflict("This call is not waiting to be answered")

    # Same language rule as the run that parked this call used for its reason.
    patient = scope.get_owned("patients", row["patient_id"]) if row.get("patient_id") else {}
    token = ElevenLabsClient().conversation_token(agent_for_phone(patient.get("phone")))
    return {
        "call_log_id": str(row["id"]),
        "token": token,
        "dynamic_variables": {str(k): str(v) for k, v in variables.items()},
    }


def _resolve_link(token: str, request: Request, client) -> tuple[TenantScope, dict]:
    """Rate-limit the caller, check the link, and load the call it names."""
    settings = get_settings()
    retry_after = link_limiter.hit(
        [(f"call-link:{client_ip(request, settings)}", LINK_REQUESTS_PER_IP, LINK_WINDOW_SECONDS)]
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment and try again.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
    try:
        call_log_id = read_call_link(token, settings)
    except ExpiredCallLink as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from None
    except InvalidCallLink as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    row = get_call_log_for_link(client, call_log_id)
    return tenant_scope_for_row(client, row), row


def _issue_link(call_log_id: str) -> CallLink:
    try:
        return issue_call_link(call_log_id, get_settings())
    except MissingConfiguration as exc:
        raise _unavailable(exc) from None


def _as_issued(link: CallLink) -> dict:
    return {"url": link.url, "expires_at": link.expires_at}


def _unavailable(exc: MissingConfiguration) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Call links are not set up on this server. {exc}.",
    )
