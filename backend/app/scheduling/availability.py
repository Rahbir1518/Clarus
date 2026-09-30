"""Free slots, and whether a proposed time can be booked.

Three questions, asked from three places:

  * "What is free?"          — the agent, mid-call, to offer times.
  * "Is this time bookable?" — the agent, when the patient proposes one.
  * "Can this be booked now?" — the booking step after the call, and staff
    adding an appointment by hand. The same check again, because the slot the
    patient agreed to may have been taken while the call was still going.

Clinic hours are stored per practice as
``{"mon": [{"start": "09:00", "end": "17:00"}], ...}`` — see
app/schemas/practice.py, which validates them on the way in. A weekday that is
absent or empty is a day the clinic is closed. Hours are wall-clock times in
the practice's zone (DEFAULT_TIMEZONE), the same zone the agent resolves
"next Tuesday at four" in.

Nothing here says who an appointment is with. The agent is told when the
practice is busy, never why — another patient's name must not be one tool call
away from whoever is on the phone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Final
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Monday first, matching date.weekday().
WEEKDAYS: Final[tuple[str, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_NAMES: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

# Appointments in these states no longer occupy their slot.
RELEASED_STATUSES: Final[frozenset[str]] = frozenset({"cancelled", "no_show"})

# Why a time cannot be booked. Stable strings: the agent's prompt and the tests
# both read them.
FREE: Final[str] = "free"
NOT_CONFIGURED: Final[str] = "hours_not_set"
CLOSED: Final[str] = "closed"
OUTSIDE_HOURS: Final[str] = "outside_hours"
TAKEN: Final[str] = "taken"
PAST: Final[str] = "past"
TOO_FAR: Final[str] = "too_far"
INVALID: Final[str] = "invalid"


def parse_hhmm(value: str) -> time:
    """"09:30" -> time(9, 30). Raises ValueError on anything else."""
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"{value!r} is not a time in HH:MM form")
    hours, minutes = int(value[:2]), int(value[3:])
    return time(hours, minutes)


def parse_hours(raw: Any) -> dict[str, list[tuple[time, time]]] | None:
    """Stored clinic hours, as ranges per weekday. None when never set.

    Tolerant of a malformed range — skipped and logged — because this runs on
    the read path, during a call, where refusing to answer is worse than
    answering from the ranges that do parse. Writes are validated strictly in
    app/schemas/practice.py, so a malformed range means someone edited the
    database by hand.
    """
    if not isinstance(raw, dict):
        return None
    hours: dict[str, list[tuple[time, time]]] = {}
    for day in WEEKDAYS:
        ranges: list[tuple[time, time]] = []
        for entry in raw.get(day) or []:
            try:
                start = parse_hhmm(entry["start"])
                end = parse_hhmm(entry["end"])
            except (KeyError, TypeError, ValueError):
                logger.warning("Ignoring malformed clinic-hours range %r on %s", entry, day)
                continue
            if start < end:
                ranges.append((start, end))
        hours[day] = sorted(ranges)
    return hours


def _as_aware(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # timestamptz always comes back with an offset; a naive value is UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def busy_intervals(
    appointments: list[dict], default_minutes: int
) -> list[tuple[datetime, datetime]]:
    """The time each live appointment occupies.

    An appointment with no end is assumed to last `default_minutes` — the
    practice's own appointment length — rather than nothing, which would leave
    its slot looking free.
    """
    busy = []
    for row in appointments:
        if row.get("status") in RELEASED_STATUSES:
            continue
        start = _as_aware(row.get("starts_at"))
        if start is None:
            continue
        end = _as_aware(row.get("ends_at")) or start + timedelta(minutes=default_minutes)
        if end > start:
            busy.append((start, end))
    return busy


def _hm(value: time | datetime) -> str:
    return value.strftime("%H:%M")


@dataclass(frozen=True)
class SlotCheck:
    """The answer to "can this time be booked?"."""

    available: bool
    reason: str
    message: str
    day: date | None = None
    start: datetime | None = None
    open_hours: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Schedule:
    """One practice's week, as the booking rules see it."""

    hours: dict[str, list[tuple[time, time]]] | None
    slot_minutes: int
    zone: ZoneInfo
    busy: list[tuple[datetime, datetime]]

    @classmethod
    def build(
        cls,
        *,
        clinic_hours: Any,
        slot_minutes: int,
        zone: ZoneInfo,
        appointments: list[dict],
    ) -> "Schedule":
        return cls(
            hours=parse_hours(clinic_hours),
            slot_minutes=slot_minutes,
            zone=zone,
            busy=busy_intervals(appointments, slot_minutes),
        )

    # -- the week -----------------------------------------------------------

    @property
    def configured(self) -> bool:
        """False until the practice has saved hours with at least one open day."""
        return bool(self.hours) and any(self.hours.values())

    def ranges_on(self, day: date) -> list[tuple[datetime, datetime]]:
        if not self.hours:
            return []
        return [
            (
                datetime.combine(day, start, tzinfo=self.zone),
                datetime.combine(day, end, tzinfo=self.zone),
            )
            for start, end in self.hours.get(WEEKDAYS[day.weekday()], [])
        ]

    def open_hours_on(self, day: date) -> list[str]:
        return [f"{_hm(a)}-{_hm(b)}" for a, b in self.ranges_on(day)]

    def _overlaps(self, start: datetime, end: datetime) -> bool:
        return any(start < b_end and b_start < end for b_start, b_end in self.busy)

    def _within_hours(self, start: datetime, end: datetime) -> bool:
        return any(a <= start and end <= b for a, b in self.ranges_on(start.date()))

    # -- the three questions ------------------------------------------------

    def free_slots(self, day: date, *, now: datetime) -> list[datetime]:
        """Start times on `day`, on the slot grid, that are free and upcoming."""
        step = timedelta(minutes=self.slot_minutes)
        slots = []
        for open_at, close_at in self.ranges_on(day):
            start = open_at
            while start + step <= close_at:
                if start > now and not self._overlaps(start, start + step):
                    slots.append(start)
                start += step
        return slots

    def next_free_days(
        self,
        *,
        start_day: date,
        now: datetime,
        horizon_days: int,
        max_days: int,
    ) -> list[tuple[date, list[datetime]]]:
        """The first `max_days` days from `start_day` that have a free slot."""
        found = []
        for offset in range(horizon_days + 1):
            day = start_day + timedelta(days=offset)
            slots = self.free_slots(day, now=now)
            if slots:
                found.append((day, slots))
                if len(found) >= max_days:
                    break
        return found

    def check(
        self,
        start: datetime,
        *,
        now: datetime,
        horizon_days: int,
        minutes: int | None = None,
    ) -> SlotCheck:
        """Whether an appointment starting at `start` can be booked.

        Any start time within opening hours counts, not only times on the slot
        grid — a patient who asks for quarter past ten can have it if nothing
        is booked then.
        """
        # The weekday and opening hours are the practice's, so read the date in
        # its zone — a UTC time near midnight is otherwise the wrong day.
        start = start.astimezone(self.zone)
        length = timedelta(minutes=minutes or self.slot_minutes)
        end = start + length
        day = start.date()
        spoken = f"{WEEKDAY_NAMES[day.weekday()]} {day.isoformat()} at {_hm(start)}"
        open_hours = self.open_hours_on(day)

        if not self.configured:
            return SlotCheck(
                False,
                NOT_CONFIGURED,
                "The practice has not set its opening hours, so no time can be "
                "confirmed on this call.",
                day,
                start,
            )
        if start <= now:
            return SlotCheck(False, PAST, f"{spoken} has already passed.", day, start)
        if day > now.astimezone(self.zone).date() + timedelta(days=horizon_days):
            return SlotCheck(
                False,
                TOO_FAR,
                f"{spoken} is more than {horizon_days} days away; bookings are only "
                f"taken within the next {horizon_days} days.",
                day,
                start,
            )
        if not open_hours:
            return SlotCheck(
                False,
                CLOSED,
                f"The clinic is closed on {WEEKDAY_NAMES[day.weekday()]}s.",
                day,
                start,
            )
        if not self._within_hours(start, end):
            return SlotCheck(
                False,
                OUTSIDE_HOURS,
                f"{spoken} is outside opening hours. On "
                f"{WEEKDAY_NAMES[day.weekday()]}s the clinic is open "
                f"{', '.join(open_hours)}, and an appointment lasts "
                f"{int(length.total_seconds() // 60)} minutes.",
                day,
                start,
                open_hours,
            )
        if self._overlaps(start, end):
            return SlotCheck(
                False, TAKEN, f"{spoken} is already booked.", day, start, open_hours
            )
        return SlotCheck(True, FREE, f"{spoken} is free.", day, start, open_hours)

    def booking_problem(
        self, start: datetime, minutes: int, *, enforce_hours: bool
    ) -> str | None:
        """Why an appointment cannot be written, or None if it can.

        The after-the-call check. No "past" or horizon rule: the time was
        agreed on the call, and whether it has since passed is for the person
        reviewing it, not a reason to lose it silently. Hours are only enforced
        when the practice has set them, and only when the caller asks — staff
        adding an appointment by hand may book outside hours on purpose.
        """
        start = start.astimezone(self.zone)
        end = start + timedelta(minutes=minutes)
        if enforce_hours and self.configured and not self._within_hours(start, end):
            day = start.date()
            hours = ", ".join(self.open_hours_on(day)) or "closed"
            return (
                f"{WEEKDAY_NAMES[day.weekday()]} {day.isoformat()} "
                f"{_hm(start)}-{_hm(end)} is outside clinic hours ({hours})."
            )
        if self._overlaps(start, end):
            return f"{start.date().isoformat()} {_hm(start)}-{_hm(end)} overlaps an existing appointment."
        return None


def day_summary(schedule: Schedule, day: date, slots: list[datetime], limit: int) -> dict:
    """One day as the agent is told it: when open, and some free times."""
    return {
        "date": day.isoformat(),
        "weekday": WEEKDAY_NAMES[day.weekday()],
        "open_hours": schedule.open_hours_on(day),
        "free_times": [_hm(s) for s in slots[:limit]],
        "more_free_times": max(0, len(slots) - limit),
    }
