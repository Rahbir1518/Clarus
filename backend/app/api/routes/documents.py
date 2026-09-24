"""PDF intake: create a patient from an uploaded clinical document.

    POST /api/pdf/intake     multipart `file`; returns the patient and what was read

The URL and response shape are what frontend/app/(app)/dashboard/page.tsx
already calls. `doctor_id`, which that page still sends as a form field, is not
declared and has no effect — the tenant comes from the token, as everywhere.

Parsing is app.ingest.pdf, which is local and deterministic: the document is
never shown to an AI model. That constraint covers this module too. Nothing
here imports app.integrations, and tests/test_pdf_ingest_isolation.py fails if
that changes.

What is written:

  * a patient, from the labelled demographics only;
  * one medication row per line of a "Medications" section;
  * a pdf_documents row holding the text and the extraction, so a clinician can
    check what was read against the source.

The PDF bytes themselves are not stored. Nothing downstream needs them, and a
copy that exists nowhere cannot leak.

Lab results are recorded on the document row and not acted on. Turning one into
a workflow trigger is a decision about a patient, and it belongs to whoever
reads the result — not to a regex.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import TenantDep
from app.ingest.pdf import MAX_PDF_BYTES, PdfRejected, parse_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pdf", tags=["documents"])


@router.post("/intake", status_code=status.HTTP_201_CREATED)
def pdf_intake(scope: TenantDep, file: UploadFile = File(...)) -> dict:
    # One byte past the limit is enough to know it is over, without reading a
    # multi-gigabyte upload into memory to find out.
    data = file.file.read(MAX_PDF_BYTES + 1)
    try:
        doc = parse_pdf(data)
    except PdfRejected as exc:
        # Literal 422 for the reason given in app/core/errors.py.
        raise HTTPException(422, str(exc)) from exc

    info = doc.patient_info
    extracted = {
        "patient_info": info,
        "medications": doc.medications,
        "lab_results": doc.lab_results,
        "page_count": doc.page_count,
        "warnings": doc.warnings,
    }

    # A patient needs both. Inventing either — "Patient from report.pdf", an
    # empty phone — creates a record that looks complete and is not, and a
    # phone number is what the call path dials.
    missing = [
        label
        for key, label in (("name", "name"), ("phone", "phone number"))
        if not info.get(key)
    ]
    if missing:
        raise HTTPException(
            422,
            f"Could not find the patient's {' or '.join(missing)} in this PDF. "
            "Add the patient by hand.",
        )

    patient = scope.insert_owned(
        "patients",
        {k: info[k] for k in ("name", "phone", "dob", "mrn", "insurance") if info.get(k)},
    )

    created_medications = 0
    for med in doc.medications:
        scope.insert_for_patient("patient_medications", patient["id"], med)
        created_medications += 1

    document = scope.insert_for_patient(
        "pdf_documents",
        patient["id"],
        {
            "filename": (file.filename or "upload.pdf")[:255],
            "page_count": doc.page_count,
            "raw_text": doc.raw_text,
            "patient_info": info,
            "lab_results": doc.lab_results,
            "tables_data": [],
        },
    )

    # Counts only. The log is not a place for a patient's details.
    logger.info(
        "PDF intake: patient=%s pages=%d labs=%d meds=%d warnings=%d",
        patient["id"],
        doc.page_count,
        len(doc.lab_results),
        created_medications,
        len(doc.warnings),
    )
    return {
        "patient": patient,
        "document_id": str(document["id"]),
        "extracted": extracted,
        "created_medications": created_medications,
    }
