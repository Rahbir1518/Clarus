"""
PDF Extraction Service
-----------------------
Parses uploaded medical PDF documents (lab reports, patient records, etc.)
and extracts structured data that can be used by the workflow engine.

Uses pdfplumber for text extraction and regex-based parsing for common
medical document patterns.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common lab-test patterns   name: value  unit  reference-range
# ---------------------------------------------------------------------------
_LAB_LINE_RE = re.compile(
    r"(?P<test_name>[A-Za-z\s\-/()]+?)\s+"
    r"(?P<value>[\d]+\.?\d*)\s*"
    r"(?P<unit>[a-zA-Z/%]+)?\s*"
    r"(?P<ref_range>[\d.\-–]+\s*[-–]\s*[\d.]+)?",
)

_PATIENT_NAME_RE = re.compile(
    r"(?:Patient\s*(?:Name)?|Name)\s*[:\-]?\s*(?P<name>[A-Z][a-zA-Z\s\-'.]+)",
    re.IGNORECASE,
)
_DOB_RE = re.compile(
    r"(?:D\.?O\.?B\.?|Date\s*of\s*Birth|Birth\s*Date)\s*[:\-]?\s*"
    r"(?P<dob>\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    re.IGNORECASE,
)
_MRN_RE = re.compile(
    r"(?:MRN|Medical\s*Record\s*(?:Number|No\.?|#))\s*[:\-]?\s*(?P<mrn>[A-Z0-9\-]+)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?:Phone|Tel|Telephone|Contact)\s*[:\-]?\s*"
    r"(?P<phone>\+?[\d\s\-().]{7,20})",
    re.IGNORECASE,
)
_INSURANCE_RE = re.compile(
    r"(?:Insurance|Insurer|Carrier|Plan)\s*[:\-]?\s*(?P<insurance>[A-Za-z\s\-&.]+?)(?:\n|$)",
    re.IGNORECASE,
)

_MEDICATION_SECTION_RE = re.compile(
    r"(?:Medications?|Current\s+Medications?|Active\s+Medications?|Rx|Prescriptions?)"
    r"\s*[:\-]?\s*\n(?P<block>(?:.*\n?){1,30})",
    re.IGNORECASE,
)
_MEDICATION_LINE_RE = re.compile(
    r"(?P<name>[A-Za-z][\w\-]+(?:\s+[\w\-]+)?)"
    r"(?:\s+(?P<dosage>\d+\s*(?:mg|mcg|ml|g|IU|units?)(?:/\w+)?))?",
    re.IGNORECASE,
)
_MEDICATION_KEYWORDS = {
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "omeprazole",
    "losartan", "gabapentin", "hydrochlorothiazide", "sertraline", "simvastatin",
    "levothyroxine", "acetaminophen", "ibuprofen", "aspirin", "warfarin",
    "clopidogrel", "insulin", "glipizide", "prednisone", "albuterol",
    "amoxicillin", "azithromycin", "ciprofloxacin", "furosemide", "pantoprazole",
    "rosuvastatin", "carvedilol", "metoprolol", "montelukast", "tamsulosin",
    "duloxetine", "escitalopram", "fluoxetine", "bupropion", "trazodone",
    "tramadol", "oxycodone", "hydrocodone", "morphine", "cephalexin",
    "doxycycline", "clindamycin", "meloxicam", "naproxen", "diclofenac",
    "cyclobenzaprine", "alprazolam", "lorazepam", "clonazepam", "zolpidem",
}


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF file."""
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_tables_from_pdf(file_bytes: bytes) -> list[list[list[str | None]]]:
    """Extract all tables from a PDF as lists of rows."""
    tables: list[list[list[str | None]]] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if page_tables:
                tables.extend(page_tables)
    return tables


def parse_patient_info(text: str) -> dict[str, str | None]:
    """Extract patient demographic info from PDF text."""
    info: dict[str, str | None] = {}

    m = _PATIENT_NAME_RE.search(text)
    if m:
        info["name"] = m.group("name").strip()

    m = _DOB_RE.search(text)
    if m:
        info["dob"] = m.group("dob").strip()

    m = _MRN_RE.search(text)
    if m:
        info["mrn"] = m.group("mrn").strip()

    m = _PHONE_RE.search(text)
    if m:
        info["phone"] = m.group("phone").strip()

    m = _INSURANCE_RE.search(text)
    if m:
        info["insurance"] = m.group("insurance").strip()

    return info


def parse_lab_results(text: str) -> list[dict[str, Any]]:
    """
    Extract lab result rows from PDF text.

    Returns a list of dicts with keys:
      test_name, value (float), unit, reference_range, flag
    """
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in _LAB_LINE_RE.finditer(text):
        test_name = m.group("test_name").strip()
        if not test_name or test_name.lower() in seen:
            continue

        try:
            value = float(m.group("value"))
        except (TypeError, ValueError):
            continue

        unit = (m.group("unit") or "").strip()
        ref_range = (m.group("ref_range") or "").strip().replace("–", "-")

        flag = "normal"
        if ref_range and "-" in ref_range:
            try:
                parts = ref_range.split("-")
                low, high = float(parts[0].strip()), float(parts[1].strip())
                if value < low:
                    flag = "low"
                elif value > high:
                    flag = "high"
            except (ValueError, IndexError):
                pass

        results.append({
            "test_name": test_name,
            "value": value,
            "unit": unit,
            "reference_range": ref_range,
            "flag": flag,
        })
        seen.add(test_name.lower())

    return results


def parse_medications(text: str) -> list[dict[str, str]]:
    """
    Extract medications from PDF text.
    Looks for a medications section first, then falls back to keyword matching.
    """
    medications: list[dict[str, str]] = []
    seen: set[str] = set()

    section_match = _MEDICATION_SECTION_RE.search(text)
    if section_match:
        block = section_match.group("block")
        for line in block.strip().split("\n"):
            line = line.strip().lstrip("•-–*123456789. ")
            if not line or len(line) < 3:
                continue
            if any(kw in line.lower() for kw in ("diagnosis", "condition", "allerg", "history", "lab ", "result")):
                break
            m = _MEDICATION_LINE_RE.match(line)
            if m:
                name = m.group("name").strip()
                dosage = (m.group("dosage") or "").strip()
                if name.lower() not in seen and len(name) > 2:
                    medications.append({"name": name, "dosage": dosage, "status": "active"})
                    seen.add(name.lower())

    for keyword in _MEDICATION_KEYWORDS:
        if keyword in seen:
            continue
        pattern = re.compile(
            rf"\b({re.escape(keyword)})\s*(\d+\s*(?:mg|mcg|ml|g|IU|units?)?(?:/\w+)?)?",
            re.IGNORECASE,
        )
        m = pattern.search(text)
        if m:
            name = m.group(1).strip()
            dosage = (m.group(2) or "").strip()
            if name.lower() not in seen:
                medications.append({"name": name.capitalize(), "dosage": dosage, "status": "active"})
                seen.add(name.lower())

    return medications


def parse_pdf_document(file_bytes: bytes) -> dict[str, Any]:
    """
    Full PDF parsing pipeline — returns structured data extracted from
    a medical PDF document.

    Returns:
        {
            "raw_text": str,
            "patient_info": { name, dob, mrn, phone, insurance },
            "lab_results": [ { test_name, value, unit, reference_range, flag } ],
            "tables": [ ... ],
            "page_count": int,
            "extracted_at": str (ISO timestamp),
        }
    """
    text = extract_text_from_pdf(file_bytes)
    tables = extract_tables_from_pdf(file_bytes)
    patient_info = parse_patient_info(text)
    lab_results = parse_lab_results(text)
    medications = parse_medications(text)

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)

    return {
        "raw_text": text,
        "patient_info": patient_info,
        "lab_results": lab_results,
        "medications": medications,
        "tables": tables,
        "page_count": page_count,
        "extracted_at": datetime.utcnow().isoformat() + "Z",
    }
