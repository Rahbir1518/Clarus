"""Response models for PDF ingestion.

The field names here are a contract with the frontend, not a free choice: the
dashboard reads `patient` and `created_medications`, and the patient page renders
`extracted.lab_results[].{test_name,value,unit,reference_range,flag}` out of
sessionStorage. Renaming any of these silently breaks that display, so they are
pinned to what frontend/app/(app)/patients/[patientId]/page.tsx already expects.
"""
from pydantic import BaseModel

from app.schemas.common import READ_CONFIG
from app.schemas.patient import PatientRead


class LabResult(BaseModel):
    model_config = READ_CONFIG

    test_name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    flag: str = "normal"


class ExtractedData(BaseModel):
    model_config = READ_CONFIG

    # Kept as loose dicts: these are informational echoes of what was parsed,
    # not the authoritative records (those are the rows written to Supabase).
    patient_info: dict = {}
    lab_results: list[LabResult] = []
    medications: list[dict] = []
    conditions: list[dict] = []


class PdfIntakeResult(BaseModel):
    """Result of creating a new patient from a PDF (dashboard intake)."""

    model_config = READ_CONFIG

    patient: PatientRead
    created_medications: int = 0
    created_conditions: int = 0
    extracted: ExtractedData
    document_id: str | None = None
    # Human-readable notes about anything that needed a placeholder or was
    # dropped — e.g. "phone not found; placeholder saved". Surfaced so a
    # clinician knows what to fill in rather than trusting a silent default.
    warnings: list[str] = []


class PdfImportResult(BaseModel):
    """Result of enriching an existing patient from a PDF (chart import)."""

    model_config = READ_CONFIG

    patient: PatientRead
    created_medications: int = 0
    created_conditions: int = 0
    # Patient columns that were empty and got filled from the PDF. Empty list
    # means the merge added no demographics (only meds/labs, or all present).
    updated_fields: list[str] = []
    extracted: ExtractedData
    document_id: str | None = None
    warnings: list[str] = []
