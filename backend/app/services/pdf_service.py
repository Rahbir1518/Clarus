"""
PDF Extraction Service
-----------------------
Parses uploaded medical PDF documents (lab reports, patient records, etc.)
and extracts structured data that can be used by the workflow engine.

Primary strategy:  Use Google Gemini to interpret the PDF content and return
                   structured JSON — works with *any* PDF layout.
Fallback strategy: If no Gemini API key is configured, fall back to
                   pdfplumber + regex-based heuristics (limited to common
                   medical document patterns).
"""
from __future__ import annotations

import io
import json
import logging
import re
from datetime import datetime
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text / table extraction (used by both strategies)
# ---------------------------------------------------------------------------

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


# ===========================================================================
# Strategy 1 — LLM-powered extraction (Google Gemini)
# ===========================================================================

_EXTRACTION_PROMPT = """\
You are a medical document parser. Analyze the following medical PDF text and
extract ALL available structured data. The document may be a lab report,
patient intake form, prescription list, discharge summary, referral letter,
or any other clinical document. Adapt to whatever layout or format is present.

CRITICAL — Multi-column table layouts:
Medical PDFs often use side-by-side columns (e.g. "Patient Name: James Okafor
Date of Birth: 1968-03-15" on ONE line). When text is extracted, adjacent
columns get concatenated.  You MUST identify field-label boundaries
(e.g. "Date of Birth", "DOB", "MRN", "Phone", "Age", "Insurance",
"Collection Date", "Ordering Physician") and use them to split values
correctly. A patient name NEVER contains phrases like "Date of Birth", "DOB",
"MRN", "Age", "Phone", "Insurance", etc. — those mark the START of a new
field on the same line.

Return a single JSON object (no markdown fences, no explanation) with exactly
these top-level keys:

{
  "patient_info": {
    "name": "<full name ONLY — stop before any next field label>",
    "dob": "<date of birth in MM/DD/YYYY format or null>",
    "mrn": "<medical record number or null>",
    "phone": "<phone number or null>",
    "email": "<email or null>",
    "address": "<address or null>",
    "insurance": "<insurance provider/plan and number or null>",
    "sex": "<M/F/Other or null>",
    "age": "<age as string or null>"
  },
  "lab_results": [
    {
      "test_name": "<name of lab test>",
      "value": <numeric value as a number>,
      "unit": "<unit of measure or empty string>",
      "reference_range": "<reference range as string or empty string>",
      "flag": "<high | low | normal | critical | abnormal>"
    }
  ],
  "medications": [
    {
      "name": "<medication name>",
      "dosage": "<dosage string or empty>",
      "frequency": "<frequency or empty>",
      "route": "<oral/IV/etc or empty>",
      "status": "<active | discontinued | prn>"
    }
  ],
  "diagnoses": [
    {
      "name": "<diagnosis or condition>",
      "icd_code": "<ICD code if present or null>",
      "status": "<active | resolved | chronic>"
    }
  ],
  "vitals": {
    "blood_pressure": "<e.g. 120/80 or null>",
    "heart_rate": "<bpm or null>",
    "temperature": "<temp or null>",
    "weight": "<weight or null>",
    "height": "<height or null>",
    "bmi": "<bmi or null>",
    "respiratory_rate": "<rate or null>",
    "oxygen_saturation": "<SpO2 or null>"
  },
  "allergies": ["<allergy 1>", "<allergy 2>"],
  "notes": "<any clinician notes, plan, or assessment as a single string or null>",
  "document_type": "<lab_report | intake_form | discharge_summary | prescription | referral | progress_note | other>",
  "document_date": "<document/report date in YYYY-MM-DD format or null>",
  "provider_name": "<ordering/attending provider name or null>",
  "facility_name": "<hospital/clinic name or null>"
}

Rules:
- Return ONLY the JSON object. No markdown code fences. No explanation.
- Use null for fields you cannot determine. Use empty arrays [] where no items found.
- For lab_results, determine the flag by comparing value to reference_range when available.
- Normalize medication names to title case.
- Extract everything you can find — do not skip data that is present in the text.
- NEVER include a field label (like "Date of Birth", "MRN", "Age", etc.) as
  part of another field's value. If you see "James Okafor Date of Birth" in
  the raw text, the name is "James Okafor" and "Date of Birth" starts the
  next field.
- If TABLE DATA is provided below, use it to resolve ambiguities — each cell
  in a table row is a separate column, so values don't bleed into each other.

"""


def _format_tables_for_prompt(tables: list[list[list[str | None]]]) -> str:
    """Format extracted tables into a readable string for the LLM prompt."""
    if not tables:
        return ""

    parts = ["\n\nTABLE DATA (each row is a list of cell values, columns are separated by | ):"]
    for i, table in enumerate(tables, 1):
        parts.append(f"\n--- Table {i} ---")
        for row in table:
            cleaned = [str(cell).strip() if cell else "" for cell in row]
            parts.append(" | ".join(cleaned))
    return "\n".join(parts)




def _parse_gemini_response(response_text: str) -> dict[str, Any]:
    """
    Parse the JSON from Gemini's response, tolerating markdown code fences
    or extra whitespace.
    """
    text = response_text.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        # Remove opening fence (possibly ```json)
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the response
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise


async def _extract_with_gemini(
    text: str,
    tables: list[list[list[str | None]]] | None = None,
) -> dict[str, Any]:
    """
    Call Google Gemini to extract structured data from PDF text.
    Optionally includes table data to help resolve multi-column ambiguities.
    """
    from app.core.config import settings

    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    from google import genai

    client = genai.Client(api_key=api_key)

    table_text = _format_tables_for_prompt(tables) if tables else ""
    prompt = (
        _EXTRACTION_PROMPT
        + "PDF TEXT:\n"
        + text[:28000]
        + table_text[:2000]
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    raw_text = response.text
    logger.debug("Gemini raw response length: %d", len(raw_text))

    parsed = _parse_gemini_response(raw_text)

    # Normalize the structure to ensure all expected keys exist
    result: dict[str, Any] = {
        "patient_info": parsed.get("patient_info", {}),
        "lab_results": parsed.get("lab_results", []),
        "medications": parsed.get("medications", []),
        "diagnoses": parsed.get("diagnoses", []),
        "vitals": parsed.get("vitals", {}),
        "allergies": parsed.get("allergies", []),
        "notes": parsed.get("notes"),
        "document_type": parsed.get("document_type", "other"),
        "document_date": parsed.get("document_date"),
        "provider_name": parsed.get("provider_name"),
        "facility_name": parsed.get("facility_name"),
    }

    # Ensure medication status defaults
    for med in result["medications"]:
        if not med.get("status"):
            med["status"] = "active"

    # Ensure lab result flags
    for lab in result["lab_results"]:
        if not lab.get("flag"):
            lab["flag"] = "normal"
        # Ensure value is numeric
        if isinstance(lab.get("value"), str):
            try:
                lab["value"] = float(lab["value"])
            except (ValueError, TypeError):
                pass

    return result


# ===========================================================================
# Strategy 2 — Regex fallback (original logic, for when no API key exists)
# ===========================================================================

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


def _parse_patient_info_regex(text: str) -> dict[str, str | None]:
    """Extract patient demographic info from PDF text using regex."""
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


def _parse_lab_results_regex(text: str) -> list[dict[str, Any]]:
    """Extract lab result rows from PDF text using regex."""
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


def _parse_medications_regex(text: str) -> list[dict[str, str]]:
    """Extract medications from PDF text using regex."""
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


def _extract_with_regex(text: str) -> dict[str, Any]:
    """Regex-based fallback extraction."""
    return {
        "patient_info": _parse_patient_info_regex(text),
        "lab_results": _parse_lab_results_regex(text),
        "medications": _parse_medications_regex(text),
        "diagnoses": [],
        "vitals": {},
        "allergies": [],
        "notes": None,
        "document_type": "other",
        "document_date": None,
        "provider_name": None,
        "facility_name": None,
    }


# ===========================================================================
# Public API  (unchanged interface — drop-in replacement)
# ===========================================================================

# Keep the old public names available for any code that imports them directly
parse_patient_info = _parse_patient_info_regex
parse_lab_results = _parse_lab_results_regex
parse_medications = _parse_medications_regex


async def parse_pdf_document_async(file_bytes: bytes) -> dict[str, Any]:
    """
    Full PDF parsing pipeline — returns structured data extracted from
    a medical PDF document.

    Uses Gemini when available, falls back to regex otherwise.

    Returns:
        {
            "raw_text": str,
            "patient_info": { name, dob, mrn, phone, insurance, ... },
            "lab_results": [ { test_name, value, unit, reference_range, flag } ],
            "medications": [ { name, dosage, status, ... } ],
            "diagnoses": [ ... ],
            "vitals": { ... },
            "allergies": [ ... ],
            "tables": [ ... ],
            "page_count": int,
            "extracted_at": str (ISO timestamp),
            "extraction_method": "gemini" | "regex",
        }
    """
    text = extract_text_from_pdf(file_bytes)
    tables = extract_tables_from_pdf(file_bytes)

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)

    # Try Gemini first
    extraction_method = "regex"
    try:
        from app.core.config import settings
        if settings.gemini_api_key:
            extracted = await _extract_with_gemini(text, tables=tables)
            extraction_method = "gemini"
            logger.info("PDF extracted via Gemini (%d chars of text)", len(text))
        else:
            extracted = _extract_with_regex(text)
            logger.info("PDF extracted via regex fallback (no GEMINI_API_KEY)")
    except Exception as exc:
        logger.warning("Gemini extraction failed, falling back to regex: %s", exc)
        extracted = _extract_with_regex(text)

    return {
        "raw_text": text,
        "patient_info": extracted.get("patient_info", {}),
        "lab_results": extracted.get("lab_results", []),
        "medications": extracted.get("medications", []),
        "diagnoses": extracted.get("diagnoses", []),
        "vitals": extracted.get("vitals", {}),
        "allergies": extracted.get("allergies", []),
        "notes": extracted.get("notes"),
        "document_type": extracted.get("document_type", "other"),
        "document_date": extracted.get("document_date"),
        "provider_name": extracted.get("provider_name"),
        "facility_name": extracted.get("facility_name"),
        "tables": tables,
        "page_count": page_count,
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "extraction_method": extraction_method,
    }


def parse_pdf_document(file_bytes: bytes) -> dict[str, Any]:
    """
    Synchronous wrapper around parse_pdf_document_async.

    If called from within a running event loop (e.g. a FastAPI endpoint),
    callers should use parse_pdf_document_async directly. This wrapper
    exists for backwards compatibility.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        text = extract_text_from_pdf(file_bytes)
        tables = extract_tables_from_pdf(file_bytes)
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)

        extracted = _extract_with_regex(text)
        return {
            "raw_text": text,
            **extracted,
            "tables": tables,
            "page_count": page_count,
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "extraction_method": "regex",
        }
    else:
        return asyncio.run(parse_pdf_document_async(file_bytes))
