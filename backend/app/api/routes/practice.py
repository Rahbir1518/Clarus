"""Practice settings the doctor edits in the app.

    GET /api/practice/settings
    PUT /api/practice/settings   opening hours and appointment length
    PUT /api/practice/profile    the doctor's and the practice's names

Opening hours and appointment length. They stay as saved until the doctor
changes them, and the agent reads them on every call — so a practice that
closes on Thursdays says so once, here, and no patient is offered a Thursday.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TenantDep
from app.core.config import get_settings
from app.scheduling.practice import appointment_minutes
from app.schemas.practice import (
    PracticeProfileUpdate,
    PracticeSettingsRead,
    PracticeSettingsUpdate,
)

router = APIRouter(prefix="/practice", tags=["practice"])


def _read(practice: dict) -> dict:
    settings = get_settings()
    return {
        "clinic_hours": practice.get("clinic_hours"),
        "appointment_minutes": appointment_minutes(practice, settings),
        "timezone": settings.default_timezone,
        "doctor_name": practice.get("doctor_name"),
        "practice_name": practice.get("practice_name"),
    }


@router.get("/settings", response_model=PracticeSettingsRead)
def get_practice_settings(scope: TenantDep) -> dict:
    return _read(scope.practice_settings())


@router.put("/settings", response_model=PracticeSettingsRead)
def update_practice_settings(body: PracticeSettingsUpdate, scope: TenantDep) -> dict:
    saved = scope.update_practice_settings(
        clinic_hours=body.clinic_hours.model_dump(),
        appointment_minutes=body.appointment_minutes,
    )
    scope.record_audit(
        action="practice.settings.update",
        entity_type="practice_settings",
        # No entity id: audit_log.entity_id is a UUID and the practice is keyed
        # by its Clerk user id, which doctor_id and actor on the row already hold.
        entity_id=None,
        metadata={"appointment_minutes": body.appointment_minutes},
    )
    return _read(saved)


@router.put("/profile", response_model=PracticeSettingsRead)
def update_practice_profile(body: PracticeProfileUpdate, scope: TenantDep) -> dict:
    """The names the agent says: "calling from <practice> on behalf of <doctor>"."""
    saved = scope.update_practice_profile(
        doctor_name=body.doctor_name, practice_name=body.practice_name
    )
    scope.record_audit(
        action="practice.profile.update",
        entity_type="practice_settings",
        entity_id=None,
    )
    return _read(saved)
