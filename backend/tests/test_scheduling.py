"""Opening hours, the calendar, and what the agent is told about both.

Dates are computed from today rather than written down, because the rules
themselves depend on "now": a slot in the past is not free, and a day beyond the
booking window is not offered. A fixed date would pass this month and fail the
next.
"""
import datetime as dt

import pytest

from app.core.config import get_settings
from app.db.tenancy import TenantScope
from app.engine.policy import calling_zone
from app.scheduling.availability import (
    CLOSED,
    FREE,
    NOT_CONFIGURED,
    OUTSIDE_HOURS,
    PAST,
    TAKEN,
    TOO_FAR,
    Schedule,
    parse_hours,
)
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"
TOOL_SECRET = "tool_secret_for_tests"

WEEKDAY_HOURS = {
    day: [{"start": "09:00", "end": "17:00"}] for day in ("mon", "tue", "wed", "thu", "sun")
}  # Friday and Saturday closed.


def _zone():
    return calling_zone(get_settings())


def _next(weekday: int, *, after_days: int = 1) -> dt.date:
    """The first date with this weekday (Mon=0) at least `after_days` ahead."""
    day = dt.datetime.now(_zone()).date() + dt.timedelta(days=after_days)
    return day + dt.timedelta(days=(weekday - day.weekday()) % 7)


def _at(day: dt.date, hhmm: str) -> dt.datetime:
    hours, minutes = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hours, minutes), tzinfo=_zone())


def _appointment(day: dt.date, start: str, end: str, status: str = "scheduled") -> dict:
    return {
        "starts_at": _at(day, start).isoformat(),
        "ends_at": _at(day, end).isoformat(),
        "status": status,
    }


def _full_except_ten(day: dt.date) -> list[dict]:
    """Booked 09:00-10:00 and 11:00-17:00: only 10:00-11:00 is left."""
    return [_appointment(day, "09:00", "10:00"), _appointment(day, "11:00", "17:00")]


def _schedule(appointments: list[dict], hours=WEEKDAY_HOURS, minutes: int = 30) -> Schedule:
    return Schedule.build(
        clinic_hours=hours, slot_minutes=minutes, zone=_zone(), appointments=appointments
    )


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


def test_a_full_day_offers_only_its_gap():
    wednesday = _next(2)
    schedule = _schedule(_full_except_ten(wednesday))

    slots = schedule.free_slots(wednesday, now=_now())

    assert [s.strftime("%H:%M") for s in slots] == ["10:00", "10:30"]


def test_a_cancelled_appointment_frees_its_slot():
    wednesday = _next(2)
    appointments = _full_except_ten(wednesday) + [
        _appointment(wednesday, "10:00", "11:00", status="cancelled")
    ]

    slots = _schedule(appointments).free_slots(wednesday, now=_now())

    assert [s.strftime("%H:%M") for s in slots] == ["10:00", "10:30"]


def test_an_appointment_with_no_end_still_occupies_its_length():
    wednesday = _next(2)
    appointments = [{"starts_at": _at(wednesday, "09:00").isoformat(), "status": "scheduled"}]

    slots = _schedule(appointments).free_slots(wednesday, now=_now())

    assert slots[0].strftime("%H:%M") == "09:30"


def test_a_closed_day_has_no_slots():
    friday = _next(4)
    assert _schedule([]).free_slots(friday, now=_now()) == []


def test_split_opening_hours_are_both_offered():
    wednesday = _next(2)
    hours = {"wed": [{"start": "09:00", "end": "10:00"}, {"start": "14:00", "end": "15:00"}]}

    slots = _schedule([], hours=hours, minutes=60).free_slots(wednesday, now=_now())

    assert [s.strftime("%H:%M") for s in slots] == ["09:00", "14:00"]


def test_a_slot_that_would_run_past_closing_is_not_offered():
    wednesday = _next(2)
    hours = {"wed": [{"start": "09:00", "end": "10:15"}]}

    slots = _schedule([], hours=hours, minutes=30).free_slots(wednesday, now=_now())

    assert [s.strftime("%H:%M") for s in slots] == ["09:00", "09:30"]


def test_the_reasons_a_time_cannot_be_booked():
    wednesday = _next(2)
    schedule = _schedule(_full_except_ten(wednesday))
    horizon = get_settings().availability_horizon_days

    def reason(day, hhmm):
        return schedule.check(_at(day, hhmm), now=_now(), horizon_days=horizon).reason

    assert reason(wednesday, "10:00") == FREE
    # Off the slot grid is fine when nothing is booked then.
    assert reason(wednesday, "10:15") == FREE
    assert reason(wednesday, "12:00") == TAKEN
    # Starts inside the gap, runs into the next appointment.
    assert reason(wednesday, "10:45") == TAKEN
    assert reason(wednesday, "18:00") == OUTSIDE_HOURS
    # Starts before closing, ends after it.
    assert reason(wednesday, "16:45") == OUTSIDE_HOURS
    assert reason(_next(4), "10:00") == CLOSED
    assert reason(dt.date(2020, 1, 1), "10:00") == PAST
    assert reason(_next(2, after_days=horizon + 7), "10:00") == TOO_FAR


def test_no_hours_means_nothing_can_be_confirmed():
    schedule = _schedule([], hours=None)
    check = schedule.check(
        _at(_next(2), "10:00"), now=_now(), horizon_days=14
    )
    assert not schedule.configured
    assert check.reason == NOT_CONFIGURED


def test_a_week_with_every_day_closed_counts_as_unset():
    assert not _schedule([], hours={"mon": []}).configured


def test_a_malformed_stored_range_is_skipped_not_fatal():
    hours = parse_hours({"wed": [{"start": "9am", "end": "5pm"}, {"start": "09:00", "end": "12:00"}]})
    assert hours["wed"] == [(dt.time(9), dt.time(12))]


def test_staff_may_book_outside_hours_but_the_agent_may_not():
    wednesday = _next(2)
    schedule = _schedule([])
    early = _at(wednesday, "07:00")

    assert schedule.booking_problem(early, 30, enforce_hours=False) is None
    assert "outside clinic hours" in schedule.booking_problem(early, 30, enforce_hours=True)


def test_nobody_may_book_on_top_of_another_appointment():
    wednesday = _next(2)
    schedule = _schedule(_full_except_ten(wednesday))

    problem = schedule.booking_problem(_at(wednesday, "11:30"), 30, enforce_hours=False)

    assert "overlaps" in problem


# ---------------------------------------------------------------------------
# Practice settings
# ---------------------------------------------------------------------------


def _save_hours(client, auth_header, doctor_id=ALICE, hours=WEEKDAY_HOURS, minutes=30):
    return client.put(
        "/api/practice/settings",
        json={"clinic_hours": hours, "appointment_minutes": minutes},
        headers=auth_header(doctor_id),
    )


def test_hours_are_unset_until_the_practice_saves_them(client, auth_header):
    response = client.get("/api/practice/settings", headers=auth_header(ALICE))

    assert response.status_code == 200
    assert response.json()["clinic_hours"] is None
    assert response.json()["appointment_minutes"] == get_settings().default_appointment_minutes
    assert response.json()["timezone"] == get_settings().default_timezone


def test_saved_hours_are_kept_until_changed(client, auth_header):
    assert _save_hours(client, auth_header, minutes=20).status_code == 200

    read = client.get("/api/practice/settings", headers=auth_header(ALICE)).json()

    assert read["clinic_hours"]["wed"] == [{"start": "09:00", "end": "17:00"}]
    assert read["clinic_hours"]["fri"] == []
    assert read["appointment_minutes"] == 20


def test_each_practice_has_its_own_hours(client, auth_header):
    _save_hours(client, auth_header, doctor_id=ALICE)

    bob = client.get("/api/practice/settings", headers=auth_header(BOB)).json()

    assert bob["clinic_hours"] is None


@pytest.mark.parametrize(
    "hours",
    [
        {"mon": [{"start": "17:00", "end": "09:00"}]},
        {"mon": [{"start": "09:00", "end": "09:00"}]},
        {"mon": [{"start": "9am", "end": "5pm"}]},
        {"mon": [{"start": "09:00", "end": "13:00"}, {"start": "12:00", "end": "17:00"}]},
        {"funday": [{"start": "09:00", "end": "17:00"}]},
    ],
)
def test_malformed_hours_are_refused(client, auth_header, hours):
    assert _save_hours(client, auth_header, hours=hours).status_code == 422


@pytest.mark.parametrize("minutes", [0, 4, 241])
def test_an_unreasonable_appointment_length_is_refused(client, auth_header, minutes):
    assert _save_hours(client, auth_header, minutes=minutes).status_code == 422


# ---------------------------------------------------------------------------
# The calendar
# ---------------------------------------------------------------------------


def _patient(db: FakeSupabase, doctor_id: str = ALICE) -> dict:
    return TenantScope(db, doctor_id).insert_owned(
        "patients", {"name": "রহিম", "phone": "+8801700000000"}
    )


def _book(client, auth_header, patient_id, day, hhmm, doctor_id=ALICE, **extra):
    return client.post(
        "/api/appointments",
        json={"patient_id": patient_id, "date": day.isoformat(), "time": hhmm, **extra},
        headers=auth_header(doctor_id),
    )


def test_an_appointment_added_by_hand_is_listed(client, fake_db, auth_header):
    _save_hours(client, auth_header)
    patient = _patient(fake_db)
    wednesday = _next(2)

    created = _book(client, auth_header, patient["id"], wednesday, "10:00", reason="Check-up")
    listed = client.get("/api/appointments", headers=auth_header(ALICE)).json()

    assert created.status_code == 201
    assert created.json()["status"] == "scheduled"
    assert dt.datetime.fromisoformat(created.json()["starts_at"]) == _at(wednesday, "10:00")
    # The practice's 30-minute length, not a hard-coded one.
    assert dt.datetime.fromisoformat(created.json()["ends_at"]) == _at(wednesday, "10:30")
    assert [a["id"] for a in listed] == [created.json()["id"]]


def test_a_double_booking_is_refused(client, fake_db, auth_header):
    patient = _patient(fake_db)
    wednesday = _next(2)
    _book(client, auth_header, patient["id"], wednesday, "10:00", duration_minutes=60)

    clash = _book(client, auth_header, patient["id"], wednesday, "10:30")

    assert clash.status_code == 409


def test_cancelling_frees_the_slot(client, fake_db, auth_header):
    patient = _patient(fake_db)
    wednesday = _next(2)
    first = _book(client, auth_header, patient["id"], wednesday, "10:00").json()

    cancelled = client.post(
        f"/api/appointments/{first['id']}/cancel", headers=auth_header(ALICE)
    )
    again = _book(client, auth_header, patient["id"], wednesday, "10:00")

    assert cancelled.json()["status"] == "cancelled"
    assert again.status_code == 201


def test_one_practices_calendar_does_not_block_another(client, fake_db, auth_header):
    wednesday = _next(2)
    _book(client, auth_header, _patient(fake_db)["id"], wednesday, "10:00")

    bob = _book(client, auth_header, _patient(fake_db, BOB)["id"], wednesday, "10:00", doctor_id=BOB)

    assert bob.status_code == 201


def test_another_practices_patient_or_appointment_is_a_404(client, fake_db, auth_header):
    wednesday = _next(2)
    alice_patient = _patient(fake_db)
    booked = _book(client, auth_header, alice_patient["id"], wednesday, "10:00").json()

    assert _book(client, auth_header, alice_patient["id"], wednesday, "11:00", doctor_id=BOB).status_code == 404
    assert (
        client.post(f"/api/appointments/{booked['id']}/cancel", headers=auth_header(BOB)).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# The agent's tools
# ---------------------------------------------------------------------------


@pytest.fixture
def tool_secret(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOOL_SECRET", TOOL_SECRET)
    get_settings.cache_clear()
    yield TOOL_SECRET
    get_settings.cache_clear()


def _live_call(db: FakeSupabase, doctor_id: str = ALICE, conversation_id: str = "conv_live") -> dict:
    scope = TenantScope(db, doctor_id)
    patient = _patient(db, doctor_id)
    row = scope.insert_owned("call_logs", {"patient_id": patient["id"], "status": "in_progress"})
    scope.bind_conversation(row["id"], conversation_id)
    return row


def _tool(client, path, secret=TOOL_SECRET, **body):
    headers = {"X-Clarus-Tool-Secret": secret} if secret is not None else {}
    return client.post(f"/api/elevenlabs/tools/{path}", json=body, headers=headers)


def _fill_wednesday(client, auth_header, fake_db, wednesday, doctor_id=ALICE):
    patient = _patient(fake_db, doctor_id)
    _book(client, auth_header, patient["id"], wednesday, "09:00", doctor_id=doctor_id, duration_minutes=60)
    _book(client, auth_header, patient["id"], wednesday, "11:00", doctor_id=doctor_id, duration_minutes=360)


def test_tools_refuse_everything_without_a_configured_secret(client, fake_db):
    _live_call(fake_db)
    assert _tool(client, "available-slots", secret="", conversation_id="conv_live").status_code == 401
    assert _tool(client, "available-slots", secret=None, conversation_id="conv_live").status_code == 401


def test_tools_refuse_a_wrong_secret(client, fake_db, tool_secret):
    _live_call(fake_db)
    response = _tool(client, "check-slot", secret="guess", conversation_id="conv_live", date="2030-01-01", time="10:00")
    assert response.status_code == 401


def test_a_conversation_nobody_placed_gets_no_calendar(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)

    response = _tool(client, "available-slots", conversation_id="conv_unknown")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "call back" in response.json()["message"]


def test_a_finished_call_gets_no_calendar(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    row = _live_call(fake_db)
    TenantScope(fake_db, ALICE).update_owned("call_logs", row["id"], {"status": "completed"})

    assert _tool(client, "available-slots", conversation_id="conv_live").json()["ok"] is False


def test_without_hours_the_agent_is_told_to_promise_nothing(client, fake_db, auth_header, tool_secret):
    _live_call(fake_db)

    response = _tool(client, "available-slots", conversation_id="conv_live").json()

    assert response["ok"] is False
    assert "opening hours" in response["message"]


def test_the_agent_is_offered_the_only_free_wednesday_slot(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    wednesday = _next(2)
    _fill_wednesday(client, auth_header, fake_db, wednesday)
    _live_call(fake_db)

    response = _tool(
        client, "available-slots", conversation_id="conv_live", date=wednesday.isoformat()
    ).json()

    assert response["ok"] is True
    assert response["requested_day"]["weekday"] == "Wednesday"
    assert response["requested_day"]["free_times"] == ["10:00", "10:30"]
    assert response["requested_day"]["open_hours"] == ["09:00-17:00"]
    # And days after it, for "anything later?".
    assert response["next_available_days"]
    assert all(d["date"] > wednesday.isoformat() for d in response["next_available_days"])


def test_the_agent_never_learns_who_is_booked(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    wednesday = _next(2)
    _fill_wednesday(client, auth_header, fake_db, wednesday)
    _live_call(fake_db)

    body = _tool(client, "check-slot", conversation_id="conv_live", date=wednesday.isoformat(), time="12:00").text
    body += _tool(client, "available-slots", conversation_id="conv_live", date=wednesday.isoformat()).text

    assert "রহিম" not in body
    for patient in fake_db.store["patients"]:
        assert patient["id"] not in body
    for appointment in fake_db.store["appointments"]:
        assert appointment["id"] not in body


def test_a_taken_time_comes_back_with_alternatives(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    wednesday = _next(2)
    _fill_wednesday(client, auth_header, fake_db, wednesday)
    _live_call(fake_db)

    response = _tool(
        client, "check-slot", conversation_id="conv_live", date=wednesday.isoformat(), time="14:00"
    ).json()

    assert response["available"] is False
    assert response["reason"] == TAKEN
    # The same day's gap first.
    assert response["alternatives"][0]["date"] == wednesday.isoformat()
    assert response["alternatives"][0]["free_times"] == ["10:00", "10:30"]


def test_a_time_outside_hours_says_when_the_clinic_is_open(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    _live_call(fake_db)

    response = _tool(
        client, "check-slot", conversation_id="conv_live", date=_next(2).isoformat(), time="19:00"
    ).json()

    assert response["reason"] == OUTSIDE_HOURS
    assert "09:00-17:00" in response["message"]


def test_a_closed_day_is_named(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    _live_call(fake_db)

    response = _tool(
        client, "check-slot", conversation_id="conv_live", date=_next(4).isoformat(), time="10:00"
    ).json()

    assert response["reason"] == CLOSED
    assert "Friday" in response["message"]


def test_a_free_time_is_confirmed(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    _live_call(fake_db)

    response = _tool(
        client, "check-slot", conversation_id="conv_live", date=_next(2).isoformat(), time="10:15"
    ).json()

    assert response["available"] is True
    assert "alternatives" not in response


def test_an_ambiguous_time_is_sent_back_rather_than_guessed(client, fake_db, auth_header, tool_secret):
    _save_hours(client, auth_header)
    _live_call(fake_db)

    response = _tool(
        client, "check-slot", conversation_id="conv_live", date=_next(2).isoformat(), time="4pm"
    ).json()

    assert response["available"] is False
    assert response["reason"] == "invalid"


def test_the_calendar_read_is_the_calling_practices(client, fake_db, auth_header, tool_secret):
    """Bob's Wednesday is full; Alice's is empty. Alice's call sees Alice's."""
    wednesday = _next(2)
    _save_hours(client, auth_header, doctor_id=ALICE)
    _save_hours(client, auth_header, doctor_id=BOB)
    _fill_wednesday(client, auth_header, fake_db, wednesday, doctor_id=BOB)
    _live_call(fake_db, ALICE, "conv_alice")

    response = _tool(
        client, "check-slot", conversation_id="conv_alice", date=wednesday.isoformat(), time="14:00"
    ).json()

    assert response["available"] is True
