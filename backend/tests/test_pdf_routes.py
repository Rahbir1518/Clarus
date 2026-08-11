"""Endpoint tests for PDF intake and import.

The parser is stubbed (its own unit tests cover the regex logic); what matters
here is the route wiring: the token's doctor owns the created rows, children and
the source document are written, missing demographics become placeholders with a
warning, and the import path is non-destructive.
"""
import pytest

from app.services import pdf_service

FULL_PARSE = {
    "patient_info": {
        "name": "Jane Doe",
        "dob": "1990-02-01",
        "mrn": "M999",
        "phone": "555-000-1111",
        "email": "jane@example.com",
        "insurance": "Aetna",
    },
    "medications": [
        {"name": "Lisinopril", "dosage": "10 mg", "frequency": "once daily"},
        {"name": "Metformin", "dosage": "500 mg"},
    ],
    "conditions": [{"icd10_code": "E11.9", "description": "Type 2 diabetes"}],
    "lab_results": [
        {"test_name": "Glucose", "value": "105", "unit": "mg/dL",
         "reference_range": "70-99", "flag": "high"},
    ],
    "tables_data": [],
    "raw_text": "raw text here",
    "page_count": 2,
}


def _upload(monkeypatch, parsed):
    monkeypatch.setattr(pdf_service, "parse_pdf", lambda _data: parsed)


def _pdf_file():
    return {"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")}


def test_intake_creates_patient_and_children(client, auth_header, monkeypatch):
    _upload(monkeypatch, FULL_PARSE)
    resp = client.post(
        "/api/pdf/intake",
        files=_pdf_file(),
        data={"doctor_id": "ignored"},
        headers=auth_header("user_doc"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["patient"]["name"] == "Jane Doe"
    assert body["patient"]["mrn"] == "M999"
    # doctor_id comes from the token, never the ignored form field.
    assert body["patient"]["doctor_id"] == "user_doc"
    assert body["created_medications"] == 2
    assert body["created_conditions"] == 1
    assert body["document_id"]
    assert body["warnings"] == []
    # Response echoes the lab results in the shape the patient page renders.
    assert body["extracted"]["lab_results"][0]["test_name"] == "Glucose"
    assert body["extracted"]["lab_results"][0]["flag"] == "high"


def test_intake_flags_missing_name_and_phone(client, auth_header, monkeypatch):
    _upload(monkeypatch, {**FULL_PARSE, "patient_info": {"mrn": "X1"}})
    resp = client.post(
        "/api/pdf/intake",
        files=_pdf_file(),
        data={"doctor_id": "ignored"},
        headers=auth_header("user_doc"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["patient"]["name"] == "Unknown Patient"
    assert body["patient"]["phone"] == "UNKNOWN"
    assert len(body["warnings"]) == 2


def test_intake_rejects_empty_file(client, auth_header, monkeypatch):
    _upload(monkeypatch, FULL_PARSE)
    resp = client.post(
        "/api/pdf/intake",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"doctor_id": "x"},
        headers=auth_header("user_doc"),
    )
    assert resp.status_code == 400


def test_import_to_existing_is_non_destructive(client, auth_header, monkeypatch):
    # Create a patient with a phone already on file and no MRN.
    created = client.post(
        "/api/patients",
        json={"name": "Existing", "phone": "555-222-3333"},
        headers=auth_header("user_doc"),
    )
    assert created.status_code == 201, created.text
    patient_id = created.json()["id"]

    _upload(monkeypatch, FULL_PARSE)
    resp = client.post(
        f"/api/patients/{patient_id}/import-pdf",
        files=_pdf_file(),
        headers=auth_header("user_doc"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Blank fields filled from the PDF; existing phone/name untouched.
    assert body["patient"]["mrn"] == "M999"
    assert body["patient"]["dob"] == "1990-02-01"
    assert body["patient"]["phone"] == "555-222-3333"
    assert body["patient"]["name"] == "Existing"
    assert "mrn" in body["updated_fields"]
    assert body["created_medications"] == 2
    assert body["created_conditions"] == 1


def test_import_dedupes_existing_medications(client, auth_header, monkeypatch):
    created = client.post(
        "/api/patients",
        json={"name": "Existing", "phone": "555-222-3333"},
        headers=auth_header("user_doc"),
    )
    patient_id = created.json()["id"]
    # Pre-load Lisinopril so the import should only add Metformin.
    client.post(
        f"/api/patients/{patient_id}/medications",
        json={"name": "Lisinopril", "dosage": "5 mg"},
        headers=auth_header("user_doc"),
    )

    _upload(monkeypatch, FULL_PARSE)
    resp = client.post(
        f"/api/patients/{patient_id}/import-pdf",
        files=_pdf_file(),
        headers=auth_header("user_doc"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created_medications"] == 1


def test_import_to_foreign_patient_is_404(client, auth_header, monkeypatch):
    created = client.post(
        "/api/patients",
        json={"name": "Owned", "phone": "555-1"},
        headers=auth_header("owner"),
    )
    patient_id = created.json()["id"]

    _upload(monkeypatch, FULL_PARSE)
    resp = client.post(
        f"/api/patients/{patient_id}/import-pdf",
        files=_pdf_file(),
        headers=auth_header("intruder"),
    )
    assert resp.status_code == 404
