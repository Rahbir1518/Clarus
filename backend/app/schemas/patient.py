"""Patient request/response models.

`doctor_id` is deliberately absent from every request model. The frontend still
sends it in the create payload; `extra="ignore"` drops it on the floor and the
tenant key is taken from the verified token instead.
"""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 'moderate', not 'medium'. The risk select in the patient detail page has always
# sent 'moderate' while this model and the database CHECK both said 'medium', so
# saving a moderate-risk patient was rejected — by the API with a 422, and by the
# database behind it. One spelling, and it is the one the UI already sends.
RiskLevel = Literal["low", "moderate", "high"]

_REQUEST_CONFIG = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _blank_to_none(value: Any) -> Any:
    """HTML form fields submit "" where the API means "no value"."""
    return None if isinstance(value, str) and not value.strip() else value


class PatientCreate(BaseModel):
    model_config = _REQUEST_CONFIG

    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    dob: date | None = None
    mrn: str | None = Field(default=None, max_length=64)
    insurance: str | None = Field(default=None, max_length=200)
    primary_physician: str | None = Field(default=None, max_length=200)
    last_visit: date | None = None
    risk_level: RiskLevel = "low"
    notes: str | None = None

    _normalise = field_validator(
        "email", "dob", "mrn", "insurance", "primary_physician", "last_visit", "notes",
        mode="before",
    )(_blank_to_none)


class PatientUpdate(BaseModel):
    model_config = _REQUEST_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    dob: date | None = None
    mrn: str | None = Field(default=None, max_length=64)
    insurance: str | None = Field(default=None, max_length=200)
    primary_physician: str | None = Field(default=None, max_length=200)
    last_visit: date | None = None
    risk_level: RiskLevel | None = None
    notes: str | None = None

    _normalise = field_validator(
        "email", "dob", "mrn", "insurance", "primary_physician", "last_visit", "notes",
        mode="before",
    )(_blank_to_none)


class PatientRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    doctor_id: str
    name: str
    phone: str
    email: str | None = None
    dob: date | None = None
    mrn: str | None = None
    insurance: str | None = None
    primary_physician: str | None = None
    last_visit: date | None = None
    risk_level: str = "low"
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
