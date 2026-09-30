"""Tools the agent calls during a call.

    POST /api/elevenlabs/tools/available-slots   what is free
    POST /api/elevenlabs/tools/check-slot        can this time be booked

ElevenLabs calls these mid-conversation, as "webhook tools" registered on the
agent by scripts/sync_agent.py. They are how the agent offers the patient real
free times and answers "what about Thursday at six?" with the truth.

Access control, and why it is two things:

  * `X-Clarus-Tool-Secret` must match ELEVENLABS_TOOL_SECRET. It says the
    request came from our ElevenLabs tool configuration. An empty setting
    refuses everything, as an empty webhook secret does.
  * `conversation_id` must belong to a call this system placed and that is
    still in progress. It is filled by ElevenLabs from the system variable
    `system__conversation_id`, never by the model, and it decides which
    practice's calendar is read — the same capability the post-call webhook
    uses, via the same lookup.

What comes back is times and opening hours, nothing else. Not who is booked,
not why: the person on the phone has only proved they answered it, and an
appointment list is a list of other patients.

Failures the agent should talk its way around — hours not set, a call it
cannot place — are 200s with `ok: false` and a sentence it can act on. A tool
error is hidden from the model by default, which would leave it improvising.
Only a bad secret is a 401.
"""
from __future__ import annotations

import hmac
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Header, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SupabaseDep
from app.core.config import Settings, get_settings
from app.core.errors import NotFound
from app.db.system import get_call_log_by_conversation, tenant_scope_for_row
from app.engine.policy import PolicyRefusal
from app.scheduling.availability import FREE, Schedule, day_summary, parse_hhmm
from app.scheduling.practice import load_schedule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/elevenlabs/tools", tags=["agent-tools"])

# A call log in this state is a live conversation. Anything else — completed,
# failed, never started — is not a call the agent is on.
_LIVE_STATUS = "in_progress"


class _ToolRequest(BaseModel):
    # Ignore rather than forbid: ElevenLabs may add fields, and a tool that
    # 422s mid-call leaves the agent with nothing to say.
    model_config = ConfigDict(extra="ignore")

    conversation_id: str = Field(default="", max_length=128)


class AvailableSlotsRequest(_ToolRequest):
    # Optional: "anything on Wednesday?" names a day, "when can I come?" does not.
    date: str | None = Field(default=None, max_length=10)


class CheckSlotRequest(_ToolRequest):
    date: str = Field(default="", max_length=10)
    time: str = Field(default="", max_length=5)


def _authorised(header: str | None, settings: Settings) -> bool:
    secret = settings.elevenlabs_tool_secret
    if not secret or not header:
        return False
    return hmac.compare_digest(header.encode(), secret.encode())


def _unavailable(message: str) -> dict:
    return {"ok": False, "message": message}


_CANNOT_CHECK = (
    "Availability cannot be checked on this call. Do not offer or promise any "
    "time. Note the patient's preferred days and times and say the practice "
    "will call back to confirm."
)


def _schedule_for_call(client, conversation_id: str, settings: Settings) -> Schedule | None:
    try:
        row = get_call_log_by_conversation(client, conversation_id)
    except NotFound:
        logger.warning("Agent tool called for unknown conversation %s", conversation_id)
        return None
    if row.get("status") != _LIVE_STATUS:
        logger.warning(
            "Agent tool called for call log %s in state %s", row.get("id"), row.get("status")
        )
        return None
    try:
        return load_schedule(tenant_scope_for_row(client, row), settings)
    except PolicyRefusal:
        logger.exception("Practice timezone could not be loaded")
        return None


def _today(schedule: Schedule, now: datetime) -> date:
    return now.astimezone(schedule.zone).date()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.post("/available-slots", status_code=status.HTTP_200_OK, response_model=None)
def available_slots(
    body: AvailableSlotsRequest,
    client: SupabaseDep,
    x_clarus_tool_secret: str | None = Header(default=None),
) -> dict | Response:
    settings = get_settings()
    if not _authorised(x_clarus_tool_secret, settings):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    schedule = _schedule_for_call(client, body.conversation_id, settings)
    if schedule is None:
        return _unavailable(_CANNOT_CHECK)
    if not schedule.configured:
        return _unavailable(
            "The practice has not set its opening hours. " + _CANNOT_CHECK
        )

    now = datetime.now(timezone.utc)
    today = _today(schedule, now)
    per_day = settings.availability_times_per_day
    response: dict = {
        "ok": True,
        "today": today.isoformat(),
        "timezone": settings.default_timezone,
        "appointment_minutes": schedule.slot_minutes,
    }

    requested = _parse_date(body.date)
    if body.date and requested is None:
        response["message"] = f"{body.date!r} is not a date in YYYY-MM-DD form."
    start_day = today
    if requested is not None:
        # The asked-for day first, whatever it holds — "Wednesday is full" is
        # itself the answer the patient needs.
        in_range = today <= requested <= today + timedelta(days=settings.availability_horizon_days)
        slots = schedule.free_slots(requested, now=now) if in_range else []
        response["requested_day"] = day_summary(schedule, requested, slots, per_day)
        if not in_range:
            response["message"] = (
                f"{requested.isoformat()} is outside the booking window (today to "
                f"{settings.availability_horizon_days} days ahead)."
            )
        elif not schedule.open_hours_on(requested):
            response["message"] = "The clinic is closed that day."
        elif not slots:
            response["message"] = "That day is fully booked."
        start_day = max(today, requested + timedelta(days=1)) if in_range else today

    days = schedule.next_free_days(
        start_day=start_day,
        now=now,
        horizon_days=max(0, (today + timedelta(days=settings.availability_horizon_days) - start_day).days),
        max_days=settings.availability_days_offered,
    )
    response["next_available_days"] = [
        day_summary(schedule, day, slots, per_day) for day, slots in days
    ]
    if not days and "requested_day" not in response:
        response["message"] = (
            f"Nothing is free in the next {settings.availability_horizon_days} days. "
            + _CANNOT_CHECK
        )
    return response


@router.post("/check-slot", status_code=status.HTTP_200_OK, response_model=None)
def check_slot(
    body: CheckSlotRequest,
    client: SupabaseDep,
    x_clarus_tool_secret: str | None = Header(default=None),
) -> dict | Response:
    settings = get_settings()
    if not _authorised(x_clarus_tool_secret, settings):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    schedule = _schedule_for_call(client, body.conversation_id, settings)
    if schedule is None:
        return _unavailable(_CANNOT_CHECK)

    day = _parse_date(body.date)
    try:
        at = parse_hhmm(body.time)
    except ValueError:
        at = None
    if day is None or at is None:
        return {
            "ok": True,
            "available": False,
            "reason": "invalid",
            "message": (
                "Pass the date as YYYY-MM-DD and the time as 24-hour HH:MM, e.g. "
                "2026-03-04 and 16:00. If the patient did not say morning, "
                "afternoon or evening, ask before checking."
            ),
        }

    now = datetime.now(timezone.utc)
    start = datetime.combine(day, at, tzinfo=schedule.zone)
    result = schedule.check(
        start, now=now, horizon_days=settings.availability_horizon_days
    )
    response: dict = {
        "ok": True,
        "available": result.available,
        "reason": result.reason,
        "message": result.message,
        "date": day.isoformat(),
        "time": body.time,
        "open_hours": schedule.open_hours_on(day),
    }
    if result.reason != FREE and schedule.configured:
        # Nearest alternatives: the same day first if it has anything, then the
        # following days — what a receptionist would offer.
        per_day = settings.availability_times_per_day
        today = _today(schedule, now)
        horizon_end = today + timedelta(days=settings.availability_horizon_days)
        first = min(max(day, today), horizon_end)
        days = schedule.next_free_days(
            start_day=first,
            now=now,
            horizon_days=max(0, (horizon_end - first).days),
            max_days=settings.availability_days_offered,
        )
        response["alternatives"] = [day_summary(schedule, d, s, per_day) for d, s in days]
    return response
