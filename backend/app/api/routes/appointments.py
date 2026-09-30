"""The practice's calendar.

    GET  /api/appointments              every live appointment, soonest first
    POST /api/appointments              add one by hand
    POST /api/appointments/{id}/cancel  free its slot

This table is the calendar the agent reads during a call: what is booked here
is what it will not offer. Workflow bookings land here too, from the
schedule_appointment node.

Hand-entered appointments may fall outside opening hours — staff can see a
patient early on purpose — but may not overlap another appointment, because
the agent would then have offered that slot to nobody and the calendar would
say two patients are in one room.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, status

from app.api.deps import TenantDep
from app.core.config import get_settings
from app.core.errors import Conflict
from app.events.broker import Event, broker
from app.scheduling.availability import parse_hhmm
from app.scheduling.practice import appointment_minutes, load_schedule
from app.schemas.appointment import AppointmentCreate, AppointmentRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentRead])
def list_appointments(scope: TenantDep) -> list[dict]:
    return scope.list_owned("appointments", order_by="starts_at", descending=False)


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
def create_appointment(body: AppointmentCreate, scope: TenantDep) -> dict:
    settings = get_settings()
    # The patient must be this practice's; insert_owned verifies it too, but a
    # 404 here comes before the schedule is read.
    scope.get_owned("patients", body.patient_id)

    minutes = body.duration_minutes or appointment_minutes(
        scope.practice_settings(), settings
    )
    schedule = load_schedule(scope, settings, minutes=minutes)
    starts_at = datetime.combine(body.date, parse_hhmm(body.time), tzinfo=schedule.zone)

    problem = schedule.booking_problem(starts_at, minutes, enforce_hours=False)
    if problem:
        raise Conflict(problem)

    row = scope.insert_owned(
        "appointments",
        {
            "patient_id": body.patient_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(minutes=minutes)).isoformat(),
            "status": "scheduled",
            "reason": body.reason,
            "notes": body.notes,
        },
    )
    scope.record_audit(
        action="appointment.create",
        entity_type="appointment",
        entity_id=str(row["id"]),
        patient_id=body.patient_id,
        metadata={"source": "manual"},
    )
    broker.publish(scope.doctor_id, Event("appointment.updated", str(row["id"])))
    return row


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(appointment_id: str, scope: TenantDep) -> dict:
    """Cancel rather than delete: the record stays, and the slot is free again."""
    existing = scope.get_owned("appointments", appointment_id)
    row = scope.update_owned("appointments", appointment_id, {"status": "cancelled"})
    scope.record_audit(
        action="appointment.cancel",
        entity_type="appointment",
        entity_id=appointment_id,
        patient_id=existing.get("patient_id"),
        metadata={"previous_status": existing.get("status")},
    )
    broker.publish(scope.doctor_id, Event("appointment.updated", appointment_id))
    return row
