"""Unit tests for the deterministic PDF parser.

These exercise the regex/table logic directly on text and synthetic table grids
— no real PDF and no pdfplumber round-trip — because that logic, not the byte
extraction, is where the ingestion is fragile and where behaviour matters.
"""
from app.services import pdf_service

SAMPLE_TEXT = """\
LabCorp Patient Report

Patient Name: John A Smith
DOB: 03/15/1980
MRN: A123456
Phone: (555) 123-4567
Email: john.smith@example.com
Insurance: Blue Cross PPO

Medications:
Lisinopril 10 mg oral once daily
Metformin 500mg twice daily
Atorvastatin 20 mg at bedtime

Diagnoses:
E11.9 - Type 2 diabetes mellitus
I10 Essential hypertension

Lab Results:
Glucose 105 mg/dL 70-99 H
Sodium 140 mmol/L 135-145 N
"""


# -- patient_info -----------------------------------------------------------


def test_parse_patient_info_all_fields():
    info = pdf_service.parse_patient_info(SAMPLE_TEXT)
    assert info["name"] == "John A Smith"
    assert info["dob"] == "1980-03-15"  # normalized to ISO, month-first
    assert info["mrn"] == "A123456"
    assert "555" in info["phone"]
    assert info["email"] == "john.smith@example.com"
    assert info["insurance"] == "Blue Cross PPO"


def test_parse_patient_info_missing_fields_are_absent():
    # No fabrication: a document with nothing recognisable yields an empty dict,
    # never blank placeholders.
    info = pdf_service.parse_patient_info("Some unrelated prose without labels.")
    assert info == {}


def test_normalize_dob_iso_input():
    assert pdf_service._normalize_dob("1975-12-01") == "1975-12-01"


def test_normalize_dob_rejects_garbage():
    assert pdf_service._normalize_dob("99/99/9999") is None


# -- medications ------------------------------------------------------------


def test_parse_medications_from_section():
    meds = pdf_service.parse_medications(SAMPLE_TEXT)
    names = {m["name"] for m in meds}
    assert names == {"Lisinopril", "Metformin", "Atorvastatin"}

    by_name = {m["name"]: m for m in meds}
    assert by_name["Lisinopril"]["dosage"] == "10 mg"
    assert by_name["Lisinopril"]["route"] == "oral"
    assert by_name["Lisinopril"]["frequency"] == "once daily"
    assert by_name["Metformin"]["dosage"] == "500mg"


def test_parse_medications_requires_a_section():
    # Drug names in prose are not a prescription list and must be ignored.
    text = "The patient reports taking Lisinopril in the past."
    assert pdf_service.parse_medications(text) == []


# -- conditions -------------------------------------------------------------


def test_parse_conditions_extracts_icd10():
    conds = pdf_service.parse_conditions(SAMPLE_TEXT)
    codes = {c["icd10_code"] for c in conds}
    assert "E11.9" in codes
    assert "I10" in codes
    by_code = {c["icd10_code"]: c for c in conds}
    assert "diabetes" in by_code["E11.9"]["description"].lower()


def test_parse_conditions_dedupes():
    text = "E11.9 diabetes\nsomething\nE11.9 diabetes again"
    conds = pdf_service.parse_conditions(text)
    assert [c["icd10_code"] for c in conds] == ["E11.9"]


# -- lab results ------------------------------------------------------------


def test_parse_lab_results_from_table():
    tables = [
        [
            ["Test", "Result", "Unit", "Reference Range", "Flag"],
            ["Glucose", "105", "mg/dL", "70-99", "H"],
            ["Sodium", "140", "mmol/L", "135-145", "N"],
            ["Notes", "", "", "", ""],  # no numeric value -> skipped
        ]
    ]
    results = pdf_service.parse_lab_results("", tables)
    assert len(results) == 2
    glucose = next(r for r in results if r["test_name"] == "Glucose")
    assert glucose["value"] == "105"
    assert glucose["unit"] == "mg/dL"
    assert glucose["reference_range"] == "70-99"
    assert glucose["flag"] == "high"


def test_parse_lab_results_line_fallback():
    # No tables -> fall back to line parsing of the text.
    results = pdf_service.parse_lab_results(SAMPLE_TEXT, [])
    by_name = {r["test_name"]: r for r in results}
    assert by_name["Glucose"]["value"] == "105"
    assert by_name["Glucose"]["flag"] == "high"
    assert by_name["Sodium"]["flag"] == "normal"


def test_flag_mapping():
    assert pdf_service._flag("H") == "high"
    assert pdf_service._flag("Low") == "low"
    assert pdf_service._flag("") == "normal"
    assert pdf_service._flag("WNL") == "normal"
