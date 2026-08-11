"""PDF lab-report ingestion.

Two entry points, one parser (app.services.pdf_service):

  * POST /pdf/intake                     — create a NEW patient from a report
  * POST /patients/{id}/import-pdf        — enrich an EXISTING patient's chart

Both follow the patients.py contract: the handler takes TenantDep, never touches
the Supabase client directly, and any client-supplied doctor_id is ignored in
favour of the token subject. All writes go through TenantScope, so the parsed
content is subject to the same column allowlist and ownership checks as a manual
create — a malformed PDF can produce junk, but never a cross-tenant write.

Parsing is best-effort and deliberately non-destructive on the import path:
demographics only fill blanks, and duplicate medications/conditions are skipped.
Anything that needed a placeholder is reported back in `warnings` rather than
silently defaulted.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import TenantDep
from app.schemas.clinical import ConditionCreate, MedicationCreate
from app.schemas.patient import PatientCreate
from app.schemas.pdf import ExtractedData, PdfImportResult, PdfIntakeResult
from app.services import pdf_service

router = APIRouter(prefix="/pdf", tags=["pdf"])
# Import-into-existing hangs off the patient URL the frontend already calls
# (POST /api/patients/{id}/import-pdf), so it lives on its own router with the
# patients prefix rather than under /pdf.
patient_pdf_router = APIRouter(prefix="/patients", tags=["pdf"])

# 20 MB. A lab report is a few hundred KB; anything past this is a scan dump or
# a mistake, and reading it into memory to parse is the denial-of-service we
# don't want to hand a caller.
_MAX_BYTES = 20 * 1024 * 1024

# Patient columns the import path may fill from a PDF. name/phone are excluded:
# overwriting an existing chart's identity from a parsed document is exactly the
# kind of silent corruption this feature must not cause.
_MERGEABLE_FIELDS = ("dob", "mrn", "email", "insurance", "primary_physician")


async def _read_pdf(file: UploadFile) -> bytes:
    """Validate and read the upload, or raise the right 4xx."""
    if file.content_type and "pdf" not in file.content_type.lower():
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected a PDF file"
            )
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "PDF exceeds 20 MB limit"
        )
    return data


def _parse(data: bytes) -> dict:
    try:
        return pdf_service.parse_pdf(data)
    except Exception as exc:  # noqa: BLE001 — any pdfplumber failure is a bad PDF
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Could not read PDF: {exc}",
        ) from exc


def _insert_children(scope: TenantDep, patient_id: str, parsed: dict) -> tuple[int, int]:
    """Insert parsed medications and conditions; return (meds, conditions) counts.

    Each row is validated through its Create schema and written independently —
    one unparseable medication line does not sink the rest of the import.
    """
    meds = 0
    for raw in parsed["medications"]:
        try:
            payload = MedicationCreate(**raw).model_dump(mode="json")
            scope.insert_for_patient("patient_medications", patient_id, payload)
            meds += 1
        except Exception:  # noqa: BLE001 — skip a bad row, keep the rest
            continue

    conditions = 0
    for raw in parsed["conditions"]:
        try:
            payload = ConditionCreate(**raw).model_dump(mode="json")
            scope.insert_for_patient("patient_conditions", patient_id, payload)
            conditions += 1
        except Exception:  # noqa: BLE001
            continue

    return meds, conditions


def _store_document(scope: TenantDep, patient_id: str, filename: str, parsed: dict) -> str | None:
    """Persist the source document; return its id (None if the write is refused)."""
    try:
        doc = scope.insert_for_patient(
            "pdf_documents",
            patient_id,
            {
                "filename": filename or "upload.pdf",
                "page_count": parsed["page_count"],
                "raw_text": parsed["raw_text"],
                "patient_info": parsed["patient_info"],
                "lab_results": parsed["lab_results"],
                "tables_data": parsed["tables_data"],
            },
        )
        return doc.get("id")
    except Exception:  # noqa: BLE001 — losing the archive copy must not fail intake
        return None


def _extracted(parsed: dict) -> ExtractedData:
    return ExtractedData(
        patient_info=parsed["patient_info"],
        lab_results=parsed["lab_results"],
        medications=parsed["medications"],
        conditions=parsed["conditions"],
    )


@router.post("/intake", response_model=PdfIntakeResult, status_code=status.HTTP_201_CREATED)
async def pdf_intake(
    scope: TenantDep,
    file: UploadFile = File(...),
    # Declared because the frontend sends it, read for nothing: the tenant key
    # comes from the token, same as everywhere else.
    doctor_id: str = Form(default=""),
) -> PdfIntakeResult:
    """Create a new patient from a lab-report PDF and attach everything parsed."""
    data = await _read_pdf(file)
    parsed = _parse(data)
    info = parsed["patient_info"]

    warnings: list[str] = []
    name = info.get("name")
    if not name:
        name = "Unknown Patient"
        warnings.append("Patient name not found in PDF; saved as 'Unknown Patient'.")
    phone = info.get("phone")
    if not phone:
        # PatientCreate requires a non-empty phone and the column is NOT NULL,
        # so a placeholder is needed. 'UNKNOWN' is intentional: it flags the gap
        # and fails E.164 validation if any workflow ever tries to dial it.
        phone = "UNKNOWN"
        warnings.append("Phone number not found in PDF; saved as 'UNKNOWN'.")

    try:
        patient_payload = PatientCreate(
            name=name,
            phone=phone,
            email=info.get("email"),
            dob=info.get("dob"),
            mrn=info.get("mrn"),
            insurance=info.get("insurance"),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 — parsed demographics failed validation
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Extracted patient details were invalid: {exc}",
        ) from exc

    patient = scope.insert_owned("patients", patient_payload)
    patient_id = patient["id"]

    meds, conditions = _insert_children(scope, patient_id, parsed)
    document_id = _store_document(scope, patient_id, file.filename or "", parsed)

    return PdfIntakeResult(
        patient=patient,
        created_medications=meds,
        created_conditions=conditions,
        extracted=_extracted(parsed),
        document_id=document_id,
        warnings=warnings,
    )


@patient_pdf_router.post(
    "/{patient_id}/import-pdf", response_model=PdfImportResult
)
async def import_pdf_to_patient(
    patient_id: str,
    scope: TenantDep,
    file: UploadFile = File(...),
) -> PdfImportResult:
    """Enrich an existing patient's chart from a PDF, non-destructively."""
    # 404 for both "no such patient" and "not yours" — resolved before any parse
    # work so a stranger's id costs nothing and reveals nothing.
    patient = scope.get_owned("patients", patient_id)

    data = await _read_pdf(file)
    parsed = _parse(data)
    info = parsed["patient_info"]

    # Fill blanks only. A field already on the chart wins over the PDF.
    updates: dict[str, str] = {}
    for field in _MERGEABLE_FIELDS:
        if not patient.get(field) and info.get(field):
            updates[field] = info[field]
    updated_fields = sorted(updates)
    if updates:
        patient = scope.update_owned("patients", patient_id, updates)

    # De-dupe medications and conditions against what's already on the chart.
    existing_meds = {
        (m.get("name") or "").strip().lower()
        for m in scope.list_for_patient("patient_medications", patient_id)
    }
    meds = 0
    for raw in parsed["medications"]:
        if (raw.get("name") or "").strip().lower() in existing_meds:
            continue
        try:
            payload = MedicationCreate(**raw).model_dump(mode="json")
            scope.insert_for_patient("patient_medications", patient_id, payload)
            meds += 1
        except Exception:  # noqa: BLE001
            continue

    existing_codes = {
        (c.get("icd10_code") or "").strip().upper()
        for c in scope.list_for_patient("patient_conditions", patient_id)
    }
    conditions = 0
    for raw in parsed["conditions"]:
        if (raw.get("icd10_code") or "").strip().upper() in existing_codes:
            continue
        try:
            payload = ConditionCreate(**raw).model_dump(mode="json")
            scope.insert_for_patient("patient_conditions", patient_id, payload)
            conditions += 1
        except Exception:  # noqa: BLE001
            continue

    document_id = _store_document(scope, patient_id, file.filename or "", parsed)

    return PdfImportResult(
        patient=patient,
        created_medications=meds,
        created_conditions=conditions,
        updated_fields=updated_fields,
        extracted=_extracted(parsed),
        document_id=document_id,
        warnings=[],
    )
