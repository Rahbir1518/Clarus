"""Deterministic lab-report PDF parsing.

No AI, no network: pdfplumber pulls the text and tables out of the bytes, and
everything below is regex over that text. The trade-off is deliberate and was
chosen by the user — it is cheap, offline and reproducible, but its precision
tracks how regular the source layout is. So two rules run through this module:

  * Never guess a value into existence. A field that isn't clearly present is
    left absent rather than filled with a wrong-but-plausible string, because a
    wrong MRN on a chart is worse than a missing one.
  * Never lose the source. `parse_pdf` returns the full `raw_text`, so a caller
    can store it verbatim and a better parser can be run over it later without
    asking the clinic to re-upload.

The output dict shapes match the write side on purpose:
  * medications -> app.schemas.clinical.MedicationCreate
  * conditions  -> app.schemas.clinical.ConditionCreate
  * lab_results -> the keys the patient page renders
    (test_name, value, unit, reference_range, flag)
"""
from __future__ import annotations

import io
import re
from datetime import date
from typing import Any

import pdfplumber

# Stored raw_text is capped so one pathological scan can't write a multi-MB row
# into pdf_documents.raw_text. 50 KB is ~15 pages of dense text — past that the
# tables/structured fields are what matter, not more prose.
_RAW_TEXT_LIMIT = 50_000


# ---------------------------------------------------------------------------
# Extraction (pdfplumber)
# ---------------------------------------------------------------------------


def extract_text_and_pages(data: bytes) -> tuple[str, int]:
    """Concatenated page text and the page count.

    Pages are joined with form-feed-ish blank lines so section detection later
    doesn't accidentally weld the bottom of one page to the top of the next.
    """
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n\n".join(parts), page_count


def extract_tables(data: bytes) -> list[list[list[str | None]]]:
    """Every table on every page, as raw cell grids.

    Kept unstructured (list of rows of cells) because lab layouts vary too much
    to impose a schema here; `parse_lab_results` is what interprets them.
    """
    tables: list[list[list[str | None]]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                tables.append(table)
    return tables


# ---------------------------------------------------------------------------
# Patient demographics
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(
    r"(?:Patient\s*Name|Patient|Name)\s*[:\-][ \t]*"
    # First token is a real word (>= 2 chars); later tokens may be single-letter
    # middle initials, so "John A Smith" survives rather than truncating to "John".
    # Separators are spaces/tabs only — \s would cross the newline and swallow the
    # next line's label ("...Smith\nDOB").
    r"(?P<name>[A-Z][A-Za-z'\-.]+(?:[ \t]+[A-Z][A-Za-z'\-.]*){0,3})",
)
_DOB_RE = re.compile(
    r"(?:D\.?O\.?B\.?|Date\s*of\s*Birth|Birth\s*Date)\s*[:\-]?\s*"
    r"(?P<dob>\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4})",
    re.IGNORECASE,
)
_MRN_RE = re.compile(
    r"(?:MRN|Medical\s*Record\s*(?:Number|No\.?|#)?)\s*[:\-#]?\s*"
    r"(?P<mrn>[A-Z0-9][A-Z0-9\-]{2,})",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?:Phone|Tel|Telephone|Mobile|Cell|Contact)\s*[:\-]?\s*"
    # Allow a leading '(' so "(555) 123-4567" matches, not just bare digits.
    r"(?P<phone>\+?\(?\d[\d\s().\-]{7,}\d)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_INSURANCE_RE = re.compile(
    r"(?:Insurance|Insurer|Payer|Health\s*Plan)\s*[:\-]?\s*"
    r"(?P<insurance>[A-Za-z0-9][A-Za-z0-9 &'\-.]{2,60})",
    re.IGNORECASE,
)


def _normalize_dob(raw: str) -> str | None:
    """Coerce a matched date to ISO ``YYYY-MM-DD``; ``None`` if implausible.

    Handles the two orderings that actually show up on North-American and
    ISO-formatted reports. Ambiguous day/month pairs (both <= 12) are read as
    month-first, matching US lab convention — noted here because it is a genuine
    guess and the one place this parser can be silently wrong.
    """
    parts = re.split(r"[/\-.]", raw)
    if len(parts) != 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None

    if len(parts[0]) == 4:  # YYYY-MM-DD
        year, month, day = nums
    else:  # M/D/YYYY or M/D/YY
        month, day, year = nums
        if year < 100:
            year += 2000 if year <= (date.today().year % 100) else 1900

    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _first(pattern: re.Pattern[str], text: str, group: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(group).strip()
    return value or None


def parse_patient_info(text: str) -> dict[str, str]:
    """Best-effort demographics. Absent keys are omitted, never blanked."""
    info: dict[str, str] = {}

    if name := _first(_NAME_RE, text, "name"):
        info["name"] = name
    if raw_dob := _first(_DOB_RE, text, "dob"):
        if iso := _normalize_dob(raw_dob):
            info["dob"] = iso
    if mrn := _first(_MRN_RE, text, "mrn"):
        info["mrn"] = mrn
    if phone := _first(_PHONE_RE, text, "phone"):
        info["phone"] = re.sub(r"\s{2,}", " ", phone).strip()
    if email := _first(_EMAIL_RE, text, "email"):
        info["email"] = email
    if insurance := _first(_INSURANCE_RE, text, "insurance"):
        info["insurance"] = insurance.rstrip(" .")

    return info


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

# A section header we can anchor on, and the headers that end the section.
_MED_SECTION_RE = re.compile(
    r"(?:Medications?|Current\s+Medications?|Rx|Prescriptions?)\s*[:\-]?\s*\n",
    re.IGNORECASE,
)
_SECTION_BREAK_RE = re.compile(
    r"\n\s*(?:Lab(?:oratory)?\s+Results?|Results?|Diagnos[ei]s|Assessment|"
    r"Allergies|Vitals?|Plan|Impression|History)\b",
    re.IGNORECASE,
)

# dose (e.g. 500 mg, 10mg, 5 mcg) and route, pulled from a medication line.
_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu|%))", re.IGNORECASE)
_ROUTE_RE = re.compile(
    r"\b(oral|po|iv|im|subcutaneous|subq|sublingual|topical|inhaled|"
    r"nasal|rectal|pr)\b",
    re.IGNORECASE,
)
_FREQ_RE = re.compile(
    r"\b(once daily|twice daily|three times daily|four times daily|"
    r"daily|nightly|weekly|monthly|q\.?d|b\.?i\.?d|t\.?i\.?d|q\.?i\.?d|"
    r"q\d+h|prn|as needed|at bedtime|qhs)\b",
    re.IGNORECASE,
)

# A medication line starts with a capitalised drug name. Kept conservative so
# prose sentences don't get scooped up as drugs.
_MED_LINE_RE = re.compile(
    r"^\s*[-*•]?\s*(?P<name>[A-Z][A-Za-z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+)?)"
    r"(?P<rest>.*)$",
)


def _medication_section(text: str) -> str | None:
    """The slice of text between a medications header and the next section."""
    start = _MED_SECTION_RE.search(text)
    if not start:
        return None
    body = text[start.end():]
    end = _SECTION_BREAK_RE.search(body)
    return body[: end.start()] if end else body


def parse_medications(text: str) -> list[dict[str, Any]]:
    """Medications from an explicit medications section.

    Anchored on a section header rather than scanning the whole document: a lab
    report mentions drug names in prose ("patient reports taking...") that are
    not a medication list, and treating those as prescriptions would file
    fictitious meds. No section, no medications.
    """
    section = _medication_section(text)
    if not section:
        return []

    meds: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in section.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        match = _MED_LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        key = name.lower()
        if key in seen:
            continue
        rest = match.group("rest")
        med: dict[str, Any] = {"name": name}
        if dose := _DOSE_RE.search(rest):
            med["dosage"] = dose.group(1).strip()
        if freq := _FREQ_RE.search(rest):
            med["frequency"] = freq.group(1).strip()
        if route := _ROUTE_RE.search(rest):
            med["route"] = route.group(1).strip()
        meds.append(med)
        seen.add(key)
    return meds


# ---------------------------------------------------------------------------
# Conditions (ICD-10)
# ---------------------------------------------------------------------------

# ICD-10-CM: a letter (I and O excluded to avoid 1/0 confusion is *not* correct
# for ICD-10 — only U is special — so allow A-Z), two digits, optional
# subcategory. Requiring a real code keeps us honest: no code, no condition,
# because patient_conditions.icd10_code is NOT NULL and a fabricated code is a
# billing hazard.
_ICD10_RE = re.compile(
    r"\b(?P<code>[A-TV-Z]\d{2}(?:\.\d{1,4})?)\b"
    r"\s*[-:]?\s*(?P<desc>[A-Z][A-Za-z0-9 ,'/\-()]{3,80})?",
)


def parse_conditions(text: str) -> list[dict[str, Any]]:
    """ICD-10 codes with their adjacent description."""
    conditions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _ICD10_RE.finditer(text):
        code = match.group("code").upper()
        if code in seen:
            continue
        desc = (match.group("desc") or "").strip(" -:")
        conditions.append(
            {"icd10_code": code, "description": desc or code}
        )
        seen.add(code)
    return conditions


# ---------------------------------------------------------------------------
# Lab results
# ---------------------------------------------------------------------------

_FLAG_WORDS = {
    "h": "high", "high": "high", "hi": "high", "abnormal high": "high",
    "l": "low", "low": "low", "lo": "low", "abnormal low": "low",
    "n": "normal", "normal": "normal", "wnl": "normal", "": "normal",
}
# A value is a number possibly followed by a unit; a reference range is a
# lo-hi pair. Compiled once and reused for both the table and line paths.
_NUM_RE = re.compile(r"^[<>]?=?\s*-?\d+(?:\.\d+)?$")
_RANGE_RE = re.compile(r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?")
_UNIT_RE = re.compile(
    r"(mg/dL|g/dL|mmol/L|mEq/L|ng/mL|pg/mL|IU/L|U/L|%|10\^\d+/[uµ]?L|"
    r"cells/[uµ]?L|mL/min|fL|pg|µg/dL|ug/dL)",
    re.IGNORECASE,
)

# Fallback line form: "Glucose 105 mg/dL 70-99 H"
_LAB_LINE_RE = re.compile(
    r"^\s*(?P<test>[A-Za-z][A-Za-z0-9 ()/%\-]+?)\s+"
    r"(?P<value>[<>]?=?\s*-?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mg/dL|g/dL|mmol/L|mEq/L|ng/mL|pg/mL|IU/L|U/L|%|fL|pg)?\s*"
    r"(?P<range>\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?)?\s*"
    r"(?P<flag>H|L|N|HI|LO|High|Low|Normal|WNL)?\s*$",
    re.IGNORECASE,
)


def _clean(cell: Any) -> str:
    return re.sub(r"\s+", " ", str(cell or "")).strip()


def _flag(raw: str) -> str:
    return _FLAG_WORDS.get(raw.strip().lower(), "normal")


def _lab_from_table(tables: list[list[list[str | None]]]) -> list[dict[str, Any]]:
    """Interpret any table that looks like a results grid.

    Identified by a header row naming a test and a value column; rows without a
    numeric value are skipped (they are sub-headers or notes, not results).
    """
    results: list[dict[str, Any]] = []
    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [_clean(c).lower() for c in table[0]]
        if not any("test" in h or "analyte" in h or "component" in h for h in header):
            if not any("result" in h or "value" in h for h in header):
                continue

        def col(*names: str) -> int | None:
            for i, h in enumerate(header):
                if any(n in h for n in names):
                    return i
            return None

        i_test = col("test", "analyte", "component", "name") or 0
        i_val = col("result", "value")
        i_unit = col("unit")
        i_range = col("reference", "range", "interval")
        i_flag = col("flag", "abnormal")

        for row in table[1:]:
            cells = [_clean(c) for c in row]
            if i_val is None or i_val >= len(cells):
                continue
            value = cells[i_val]
            if not value or not _NUM_RE.match(value):
                continue
            test = cells[i_test] if i_test < len(cells) else ""
            if not test:
                continue
            entry: dict[str, Any] = {"test_name": test, "value": value}
            entry["unit"] = cells[i_unit] if i_unit is not None and i_unit < len(cells) else ""
            entry["reference_range"] = (
                cells[i_range] if i_range is not None and i_range < len(cells) else ""
            )
            entry["flag"] = _flag(
                cells[i_flag] if i_flag is not None and i_flag < len(cells) else ""
            )
            results.append(entry)
    return results


def _lab_from_lines(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = _LAB_LINE_RE.match(line)
        if not match:
            continue
        test = match.group("test").strip()
        # A line has to have either a unit or a reference range to be a lab
        # result and not a stray "Page 2" or "Ordered 3 tests".
        if not (match.group("unit") or match.group("range")):
            continue
        results.append(
            {
                "test_name": test,
                "value": re.sub(r"\s+", "", match.group("value")),
                "unit": (match.group("unit") or "").strip(),
                "reference_range": (match.group("range") or "").strip(),
                "flag": _flag(match.group("flag") or ""),
            }
        )
    return results


def parse_lab_results(
    text: str, tables: list[list[list[str | None]]]
) -> list[dict[str, Any]]:
    """Lab values, preferring tables (structured) over line regex (fallback).

    Tables carry the column semantics explicitly, so they are trusted first;
    the line scan only runs when the report has no usable results table (some
    are laid out as flat text).
    """
    from_table = _lab_from_table(tables)
    if from_table:
        return from_table
    return _lab_from_lines(text)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def parse_pdf(data: bytes) -> dict[str, Any]:
    """Parse raw PDF bytes into the structured payload the routes persist.

    Returns everything a caller needs to both create records and store the
    source document, so the route never has to re-open the PDF:

        {patient_info, medications, conditions, lab_results,
         tables_data, raw_text, page_count}
    """
    raw_text, page_count = extract_text_and_pages(data)
    tables = extract_tables(data)
    return {
        "patient_info": parse_patient_info(raw_text),
        "medications": parse_medications(raw_text),
        "conditions": parse_conditions(raw_text),
        "lab_results": parse_lab_results(raw_text, tables),
        "tables_data": tables,
        "raw_text": raw_text[:_RAW_TEXT_LIMIT],
        "page_count": page_count,
    }
