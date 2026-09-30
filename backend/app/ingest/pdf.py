"""Extract structured fields from a clinical PDF — locally, with no AI.

**No model reads these documents.** A lab report or discharge summary carries a
patient's name, date of birth, record number, phone, insurance and results all
on one page. The previous backend sent the whole text, tables included, to
Google Gemini whenever GEMINI_API_KEY happened to be set, and fell back to
regex only when it was not — so whether patient records left the building
depended on an environment variable. This module has one strategy, and it never
leaves the process: pypdf pulls the text, and fixed patterns pull the fields.

tests/test_pdf_ingest_isolation.py holds that line. It fails if this package
imports anything outside a short allowlist (no HTTP clients, no AI SDKs, no
app.integrations), and it parses a document with sockets disabled.

The trade-off is recall. A pattern only finds a field that is labelled the way
it expects, so every rule below is written to miss rather than to guess:

  * A field must be introduced by a known label and a colon. "Name: X" is a
    name; "X" on its own line is not.
  * A lab result needs a name, a number, a unit AND a reference range on one
    line. The old fallback accepted "any words followed by a number", which
    extracted addresses, dates and page numbers as lab results.
  * Medications come only from a section headed "Medications". The old keyword
    scan found "aspirin" in "Allergies: aspirin" and recorded it as an active
    prescription.
  * A date whose day and month are both 12 or under is left empty rather than
    read as either — 03/04/1980 is April in Dhaka and March in Chicago.
  * A field the document gives two different values for is left empty, and
    labels above the first patient field (the letterhead, with the lab's own
    "Tel:") are ignored.
  * A phone number is stored as written. Turning 017... into +88017... is the
    country guess app.engine.policy.assert_dialable refuses to make.

Everything missed is reported in `warnings`, for the clinician to fill in by
hand. That is the correct failure: an empty field is visible, a wrong one is not.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES: Final[int] = 20 * 1024 * 1024
MAX_PAGES: Final[int] = 50
# pdf_documents.raw_text is a text column, not a file store. Anything past this
# is almost certainly not a single clinical document.
MAX_STORED_TEXT: Final[int] = 50_000


class PdfRejected(ValueError):
    """The upload is not a PDF this module will read.

    The message is shown to the uploader, so it never quotes document content.
    """


@dataclass
class ExtractedDocument:
    raw_text: str
    page_count: int
    patient_info: dict[str, str] = field(default_factory=dict)
    lab_results: list[dict[str, Any]] = field(default_factory=list)
    medications: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def read_text(data: bytes) -> tuple[str, int]:
    """Text of every page, and the page count. Opens the document once."""
    if len(data) > MAX_PDF_BYTES:
        raise PdfRejected("PDF must be under 20 MB.")
    # The magic number, not the filename: an extension is whatever the
    # uploader typed.
    if not data.lstrip()[:5] == b"%PDF-":
        raise PdfRejected("This file is not a PDF.")

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfRejected(
                "This PDF is password-protected. Remove the password and upload it again."
            )
        page_count = len(reader.pages)
        if page_count > MAX_PAGES:
            raise PdfRejected(f"PDF has {page_count} pages; the limit is {MAX_PAGES}.")
        text = "\n".join(_page_text(page) for page in reader.pages)
    except PdfRejected:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise PdfRejected("This PDF could not be read. It may be damaged.") from exc

    return _tidy(text), page_count


def _page_text(page: Any) -> str:
    """The page as it looks, rows kept on one line.

    pypdf's default mode emits text in drawing order, and a lab system that
    draws a table cell by cell comes out one cell per line: "Patient Name:" on
    one line, the name on the next, and no result row ever whole. Layout mode
    places text by position, so a row stays a row and columns are separated by
    runs of spaces, which _labelled_fields uses as a boundary.
    """
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except Exception:  # layout mode is newer and less forgiving of odd fonts
        return page.extract_text() or ""


def _tidy(text: str) -> str:
    """Drop the trailing padding and blank runs layout mode leaves behind."""
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n")


# ---------------------------------------------------------------------------
# Labelled fields
# ---------------------------------------------------------------------------

# Label spellings, per field. Longest first within the alternation below, so
# "Patient Name" wins over "Name".
_FIELD_LABELS: Final[dict[str, tuple[str, ...]]] = {
    "name": ("Patient Name", "Patient", "Name"),
    "dob": ("Date of Birth", "Birth Date", "D.O.B.", "DOB"),
    "mrn": ("Medical Record Number", "Medical Record No.", "Medical Record No", "MRN"),
    "phone": ("Mobile Number", "Phone Number", "Telephone", "Mobile", "Phone", "Tel"),
    "insurance": ("Insurance", "Insurer"),
    "sex": ("Gender", "Sex"),
}

# Labels that end the value before them but are not themselves captured.
# Multi-column layouts put "Name: X   Date of Birth: Y" on one extracted line,
# and without knowing where the next field starts, X swallows it.
_STOP_LABELS: Final[tuple[str, ...]] = (
    "Age", "Address", "Email", "Collection Date", "Report Date", "Date",
    "Ordering Physician", "Physician", "Doctor", "Referred By", "Specimen",
    "Sample", "Visit", "Ward", "Bed", "Blood Group", "Collected", "Received",
    "Reported", "Accession", "Ordering Provider", "Provider", "Clinic", "Status",
    "Health Card",
)

_LABEL_TO_FIELD: Final[dict[str, str | None]] = {
    **{label.lower(): name for name, labels in _FIELD_LABELS.items() for label in labels},
    **{label.lower(): None for label in _STOP_LABELS},
}

_ANY_LABEL: Final[str] = "|".join(
    re.escape(label)
    for label in sorted(
        {*(l for ls in _FIELD_LABELS.values() for l in ls), *_STOP_LABELS},
        key=len,
        reverse=True,
    )
)
# "Name:", "MRN#", "Health Card #:", and combined labels such as "DOB / Sex:"
# whose value is written the same way, "1984-03-17 / F".
_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?<![A-Za-z])((?:{_ANY_LABEL})(?:\s*/\s*(?:{_ANY_LABEL}))*)\s*(?:#\s*:?|:)",
    re.IGNORECASE,
)
# A value ends at a column gap or a "|" separator as well as at the next label.
_VALUE_END_RE: Final[re.Pattern[str]] = re.compile(r"\s{3,}|\s*\|")

# Fields that say whose document this is. Everything above the first of them
# is the letterhead, where "Tel:" is the lab's number, not the patient's.
_PATIENT_FIELDS: Final[frozenset[str]] = frozenset({"name", "dob", "mrn"})


def _line_fields(line: str) -> list[tuple[str | None, str]]:
    """(field or None for a stop label, value) for each label on the line."""
    out: list[tuple[str | None, str]] = []
    matches = list(_LABEL_RE.finditer(line))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        value = line[match.end():end].strip()
        value = _VALUE_END_RE.split(value, maxsplit=1)[0].strip(" \t,;")
        labels = re.split(r"\s*/\s*", match.group(1))
        # "DOB / Sex: 1984-03-17 / F" — only a spaced slash separates the
        # parts, since a date may contain unspaced ones. If the counts differ
        # the pairing is a guess, so none of it is taken.
        values = re.split(r"\s+/\s+", value) if len(labels) > 1 else [value]
        if len(values) != len(labels):
            continue
        out.extend(
            (_LABEL_TO_FIELD.get(label.lower()), part.strip())
            for label, part in zip(labels, values)
        )
    return out


def _labelled_fields(text: str) -> dict[str, list[str]]:
    """Every distinct value per field, skipping the letterhead."""
    lines = [_line_fields(line) for line in text.splitlines()]
    start = next(
        (i for i, fields in enumerate(lines) if any(f in _PATIENT_FIELDS for f, _ in fields)),
        0,
    )
    found: dict[str, list[str]] = {}
    for fields in lines[start:]:
        for field_name, value in fields:
            if field_name is None or not value:
                continue
            values = found.setdefault(field_name, [])
            if _same_key(field_name, value) not in {_same_key(field_name, v) for v in values}:
                values.append(value)
    return found


def _same_key(field_name: str, value: str) -> str:
    if field_name == "phone":
        return re.sub(r"\D", "", value)
    return " ".join(value.casefold().split())


_FIELD_TITLES: Final[dict[str, str]] = {
    "name": "name", "dob": "date of birth", "mrn": "record number",
    "phone": "phone number", "insurance": "insurance", "sex": "sex",
}


def _one_value(
    found: dict[str, list[str]], field_name: str, warnings: list[str]
) -> str | None:
    """The field's value, or None if the document gives two different ones."""
    values = found.get(field_name, [])
    if len(values) > 1:
        warnings.append(
            f"The document gives more than one {_FIELD_TITLES[field_name]}; "
            "enter it by hand."
        )
        return None
    return values[0] if values else None


_PHONE_CHARS_RE: Final[re.Pattern[str]] = re.compile(r"^\+?[\d\s\-().]{7,20}$")


def _clean_phone(raw: str) -> str | None:
    if not _PHONE_CHARS_RE.match(raw):
        return None
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        return None
    return ("+" if raw.lstrip().startswith("+") else "") + digits


_DATE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"
    r"|(?P<a>\d{1,2})[/\-.](?P<b>\d{1,2})[/\-.](?P<yy>\d{4}))$"
)


def _parse_dob(raw: str) -> tuple[str | None, str | None]:
    """(ISO date, warning). Refuses to pick between day-first and month-first."""
    match = _DATE_RE.match(raw.strip())
    if not match:
        return None, "Date of birth is not in a recognised numeric format."
    try:
        if match.group("y"):
            return date(
                int(match.group("y")), int(match.group("m")), int(match.group("d"))
            ).isoformat(), None
        a, b, year = int(match.group("a")), int(match.group("b")), int(match.group("yy"))
        if a > 12 >= b:
            return date(year, b, a).isoformat(), None  # day first
        if b > 12 >= a:
            return date(year, a, b).isoformat(), None  # month first
        if a == b:
            return date(year, a, b).isoformat(), None
    except ValueError:
        return None, "Date of birth is not a real calendar date."
    return None, (
        "Date of birth is ambiguous (day and month could be swapped); enter it by hand."
    )


def extract_patient_info(text: str) -> tuple[dict[str, str], list[str]]:
    found = _labelled_fields(text)
    info: dict[str, str] = {}
    warnings: list[str] = []
    fields = {name: _one_value(found, name, warnings) for name in _FIELD_TITLES}

    if name := fields.get("name"):
        # Refuse what a name cannot contain rather than requiring what it must:
        # Bangla vowel signs are combining marks, not \w, so a letters-only
        # rule would reject most Bangla names.
        if len(name) <= 100 and not re.search(r"[\d@:/\\|#$%=<>_]", name):
            info["name"] = name
        else:
            warnings.append("A 'Name' label was found but its value did not look like a name.")

    if raw_dob := fields.get("dob"):
        iso, warning = _parse_dob(raw_dob)
        if iso:
            info["dob"] = iso
        if warning:
            warnings.append(warning)

    if mrn := fields.get("mrn"):
        if re.fullmatch(r"[A-Za-z0-9\-/]{2,64}", mrn):
            info["mrn"] = mrn

    if raw_phone := fields.get("phone"):
        phone = _clean_phone(raw_phone)
        if phone is None:
            warnings.append("A phone label was found but its value is not a phone number.")
        else:
            info["phone"] = phone
            if not phone.startswith("+"):
                warnings.append(
                    "Phone number has no country code. It is saved as written and "
                    "cannot be called until it is corrected to international form, "
                    "e.g. +8801712345678."
                )

    if insurance := fields.get("insurance"):
        info["insurance"] = insurance[:200]

    if sex := fields.get("sex"):
        info["sex"] = sex[:16]

    return info, warnings


# ---------------------------------------------------------------------------
# Lab results
# ---------------------------------------------------------------------------

_NUMBER = r"-?\d+(?:\.\d+)?"
_LAB_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ,()/%+\-]{1,60}?)\s+"
    rf"(?P<value>{_NUMBER})\s*(?P<marker>\*|HH|LL|H|L)?\s+"
    r"(?P<unit>[A-Za-zµμ%/^*0-9.]*[A-Za-zµμ%][A-Za-zµμ%/^*0-9.]*)\s+"
    rf"(?:(?P<low>{_NUMBER})\s*[-–]\s*(?P<high>{_NUMBER})"
    rf"|(?P<cmp>[<>]=?|[≤≥])\s*(?P<bound>{_NUMBER}))"
    r"(?:\s+(?:H|L|HH|LL|High|Low|Normal|\*))?\s*$"
)
# A line that ends in a reference range but did not match above: a result
# written as "Pending" or "<25". Not read, but not silently dropped either.
_RANGE_TAIL_RE: Final[re.Pattern[str]] = re.compile(
    rf"^\s*[A-Za-z].*\s(?:{_NUMBER}\s*[-–]\s*{_NUMBER}|(?:[<>]=?|[≤≥])\s*{_NUMBER})\s*$"
)

# A name that is really a label means the line is demographics, not a result.
_NOT_A_TEST: Final[re.Pattern[str]] = re.compile(
    r"\b(page|phone|mobile|tel|date|age|dob|mrn|room|bed|ward|house|road|"
    r"street|flat|sector|block|zip|post|id|no)\b",
    re.IGNORECASE,
)


def _range_flag(value: float, match: re.Match[str]) -> tuple[str, str] | None:
    """(reference range as written, flag), or None if the range is impossible."""
    if match.group("low") is not None:
        low, high = float(match.group("low")), float(match.group("high"))
        if low > high:
            return None
        flag = "low" if value < low else "high" if value > high else "normal"
        return f"{match.group('low')}-{match.group('high')}", flag
    cmp = {"≤": "<=", "≥": ">="}.get(match.group("cmp"), match.group("cmp"))
    bound = float(match.group("bound"))
    if cmp[0] == "<":
        normal = value < bound or (cmp == "<=" and value == bound)
        flag = "normal" if normal else "high"
    else:
        normal = value > bound or (cmp == ">=" and value == bound)
        flag = "normal" if normal else "low"
    return f"{cmp}{match.group('bound')}", flag


def extract_lab_results(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    unread = 0
    for line in text.splitlines():
        match = _LAB_LINE_RE.match(line)
        if not match:
            unread += bool(_RANGE_TAIL_RE.match(line)) and not _NOT_A_TEST.search(line)
            continue
        name = " ".join(match.group("name").split())
        if _NOT_A_TEST.search(name) or name.lower() in seen:
            continue
        value = float(match.group("value"))
        ranged = _range_flag(value, match)
        if ranged is None:
            continue
        reference_range, flag = ranged
        results.append(
            {
                "test_name": name,
                "value": value,
                "unit": match.group("unit"),
                "reference_range": reference_range,
                "flag": flag,
            }
        )
        seen.add(name.lower())
    warnings = []
    if unread:
        warnings.append(
            f"{unread} result line(s) have no plain numeric value (e.g. 'Pending' "
            "or '<25') and were not imported; check the document."
        )
    return results, warnings


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

_MED_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:current\s+|active\s+)?(?:medications?|prescriptions?)\s*:?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
# Any other "Heading:" line ends the section.
_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"^\s*[A-Za-z][A-Za-z /&]{2,40}:\s*$")
_MED_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z\-]+(?:\s+[A-Za-z][A-Za-z\-]+)?)"
    r"(?:\s+(?P<dosage>\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ml|g|iu|units?)(?:/\w+)?))?"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
_NO_MEDS: Final[frozenset[str]] = frozenset({"none", "nil", "n/a", "na", "nkda"})


def extract_medications(text: str) -> list[dict[str, str]]:
    medications: list[dict[str, str]] = []
    seen: set[str] = set()
    in_section = False
    started = False  # a blank line under the heading is spacing, not the end

    for line in text.splitlines():
        header = _MED_HEADER_RE.match(line)
        if header and not in_section:
            in_section = True
            line = header.group("rest")
            if not line.strip():
                continue
        elif not in_section:
            continue
        elif not line.strip() and not started:
            continue
        elif not line.strip() or _HEADER_RE.match(line):
            break
        started = True

        stripped = line.strip()
        entry = stripped.lstrip("•*-–·0123456789.) ").strip()
        if not entry or entry.lower() in _NO_MEDS:
            continue
        match = _MED_LINE_RE.match(entry)
        # Text extraction drops blank lines, so a blank line cannot be relied on
        # to end the section. A line that is neither a list item nor carries a
        # dose is the next part of the document, not another drug — otherwise
        # "Page 1 of 1" becomes a prescription.
        is_list_item = entry != stripped
        if not match or not (is_list_item or match.group("dosage")):
            break
        name = match.group("name").strip()
        if len(name) < 3 or name.lower() in seen:
            continue
        medications.append(
            {
                "name": name,
                "dosage": " ".join((match.group("dosage") or "").split()),
                "status": "active",
            }
        )
        seen.add(name.lower())
    return medications


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_pdf(data: bytes) -> ExtractedDocument:
    """Read a PDF and extract what can be extracted without guessing."""
    text, page_count = read_text(data)
    doc = ExtractedDocument(raw_text=text[:MAX_STORED_TEXT], page_count=page_count)

    if not text.strip():
        doc.warnings.append(
            "No text could be read. This is probably a scanned image; enter the "
            "details by hand."
        )
        return doc

    doc.patient_info, doc.warnings = extract_patient_info(text)
    doc.lab_results, lab_warnings = extract_lab_results(text)
    doc.warnings.extend(lab_warnings)
    doc.medications = extract_medications(text)
    return doc
