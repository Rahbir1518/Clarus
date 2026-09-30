"""A practice's schedule, read through its TenantScope.

The one place that turns stored rows into a `Schedule`, used by the agent tools,
the booking step and the appointments routes. Three copies of "which length,
which zone, which appointments" is how two of them would drift apart.
"""
from __future__ import annotations

from app.core.config import Settings
from app.db.tenancy import TenantScope
from app.engine.policy import calling_zone
from app.scheduling.availability import Schedule


def appointment_minutes(practice: dict, settings: Settings) -> int:
    value = practice.get("appointment_minutes")
    return value if isinstance(value, int) and value > 0 else settings.default_appointment_minutes


def load_schedule(
    scope: TenantScope, settings: Settings, *, minutes: int | None = None
) -> Schedule:
    """The practice's hours and every live appointment it has.

    `minutes` overrides the practice's appointment length — the booking step
    passes the length its node was configured with.
    """
    practice = scope.practice_settings()
    return Schedule.build(
        clinic_hours=practice.get("clinic_hours"),
        slot_minutes=minutes or appointment_minutes(practice, settings),
        # Raises PolicyRefusal on a zone the platform cannot load, rather than
        # quietly reading opening hours in UTC.
        zone=calling_zone(settings),
        appointments=scope.list_owned("appointments"),
    )
