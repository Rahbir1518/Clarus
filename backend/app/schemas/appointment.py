"""Appointment request/response models."""
from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.scheduling.availability import parse_hhmm


class AppointmentCreate(BaseModel):
    """An appointment staff add by hand.

    Date and wall-clock time rather than a timestamp: the person entering it
    means the practice's local time, and converting in the browser is how an
    appointment lands an hour off. The server reads them in DEFAULT_TIMEZONE.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: str
    date: Date
    time: str = Field(..., description="Start time, HH:MM (24-hour)")
    # Defaults to the practice's appointment length.
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("time")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        try:
            parse_hhmm(value)
        except ValueError as exc:
            raise ValueError(f"{value!r} is not a time in HH:MM (24-hour) form") from exc
        return value


class AppointmentRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    patient_id: str | None = None
    workflow_id: str | None = None
    call_log_id: str | None = None
    starts_at: str
    ends_at: str | None = None
    status: str
    location: str | None = None
    reason: str | None = None
    notes: str | None = None
    created_at: str | None = None
