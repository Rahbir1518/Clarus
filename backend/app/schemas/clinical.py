"""Conditions and medications.

Both hang off a patient, both are clinical records, and both are edited from
the same patient-detail screen — so they share a file. Neither carries a
`patient_id` field: it comes from the verified path segment, and accepting it
in the body would let a payload file a diagnosis against a different chart.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import READ_CONFIG, REQUEST_CONFIG, blank_to_none

# Both must stay in step with their CHECK constraints.
ConditionStatus = Literal["documented", "review_needed", "pending_review"]
MedicationStatus = Literal["active", "discontinued", "on_hold"]


# -- conditions -------------------------------------------------------------


class ConditionCreate(BaseModel):
    model_config = REQUEST_CONFIG

    icd10_code: str = Field(min_length=1, max_length=16)
    description: str = Field(min_length=1, max_length=500)
    hcc_category: str | None = Field(default=None, max_length=100)

    # NUMERIC(6,3) in the schema: three decimal places, three digits before.
    # Bounded here so an out-of-range value is a 422 naming the field rather
    # than a numeric overflow surfacing as a 500.
    raf_impact: float | None = Field(default=None, ge=-999.999, le=999.999)

    status: ConditionStatus = "documented"

    _normalise = field_validator("hcc_category", "raf_impact", mode="before")(
        blank_to_none
    )


class ConditionUpdate(BaseModel):
    model_config = REQUEST_CONFIG

    icd10_code: str | None = Field(default=None, min_length=1, max_length=16)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    hcc_category: str | None = Field(default=None, max_length=100)
    raf_impact: float | None = Field(default=None, ge=-999.999, le=999.999)
    status: ConditionStatus | None = None

    _normalise = field_validator("hcc_category", "raf_impact", mode="before")(
        blank_to_none
    )


class ConditionRead(BaseModel):
    model_config = READ_CONFIG

    id: str
    patient_id: str
    icd10_code: str
    description: str
    hcc_category: str | None = None
    raf_impact: float | None = None
    status: str = "documented"
    created_at: datetime | None = None
    updated_at: datetime | None = None


# -- medications ------------------------------------------------------------


class MedicationCreate(BaseModel):
    model_config = REQUEST_CONFIG

    name: str = Field(min_length=1, max_length=200)
    dosage: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=50)

    # Free text for an outside prescriber. The typed foreign key beside it in
    # the schema, prescriber_doctor_id, is deliberately not exposed: it names a
    # clinician on this system, and a request body is not where that claim
    # should come from. See _SELF_REFERENCES in app/db/tenancy.py.
    prescriber: str | None = Field(default=None, max_length=200)

    start_date: date | None = None
    end_date: date | None = None
    status: MedicationStatus = "active"
    notes: str | None = None

    _normalise = field_validator(
        "dosage", "frequency", "route", "prescriber", "start_date", "end_date",
        "notes", mode="before",
    )(blank_to_none)


class MedicationUpdate(BaseModel):
    model_config = REQUEST_CONFIG

    name: str | None = Field(default=None, min_length=1, max_length=200)
    dosage: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=50)
    prescriber: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    status: MedicationStatus | None = None
    notes: str | None = None

    _normalise = field_validator(
        "dosage", "frequency", "route", "prescriber", "start_date", "end_date",
        "notes", mode="before",
    )(blank_to_none)


class MedicationRead(BaseModel):
    model_config = READ_CONFIG

    id: str
    patient_id: str
    name: str
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    prescriber: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = "active"
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
