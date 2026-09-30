"""Build small, real PDFs in memory, so no sample patient document is committed.

Deliberately minimal: one Helvetica page, one text line per entry, with a valid
xref table so pypdf reads it the same way it reads a lab's output.
"""
from __future__ import annotations


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str]) -> bytes:
    stream = "BT /F1 10 Tf 14 TL 40 800 Td\n" + "".join(
        f"({_escape(line)}) Tj T*\n" for line in lines
    ) + "ET"
    return _wrap(stream)


def make_table_pdf(rows: list[list[str]], column_x: list[int]) -> bytes:
    """Each cell drawn as its own text object, the way many lab systems do.

    pypdf's default extraction reads this one cell per line.
    """
    stream = "".join(
        f"BT /F1 9 Tf {column_x[col]} {800 - 16 * row} Td ({_escape(cell)}) Tj ET\n"
        for row, cells in enumerate(rows)
        for col, cell in enumerate(cells)
        if cell
    )
    return _wrap(stream)


def _wrap(stream: str) -> bytes:
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


LAB_REPORT = [
    "Dhaka Diagnostic Centre",
    "Patient Name: Rahim Uddin   Date of Birth: 15/03/1968   Age: 58",
    "MRN: DDC-20931   Phone: +8801712345678",
    "Insurance: Green Delta Health",
    "House 12, Road 5, Dhanmondi 1209",
    "Collection Date: 02/09/2026",
    "Test Result Unit Reference",
    "HbA1c 8.2 % 4.0-5.6",
    "Fasting Glucose 142 mg/dL 70-100",
    "Haemoglobin 13.1 g/dL 13.0-17.0",
    "Potassium 3.2 L mmol/L 3.5-5.1",
    "Allergies: aspirin",
    "Current Medications:",
    "1. Metformin 500 mg twice daily",
    "2. Amlodipine 5mg",
    "",
    "Page 1 of 1",
]


# Letterhead, a two-column demographics block and a results table, drawn cell
# by cell. Mirrors a North American lab report.
TABLE_REPORT_COLUMNS = [40, 150, 330, 420]
TABLE_REPORT = [
    ["Lakeshore Diagnostic Laboratories", "", "Tel: 416-555-0142"],
    ["Patient Name:", "DOE, JANE A.", "Collected:", "2026-09-22 08:14"],
    ["DOB / Sex:", "1984-03-17 / F", "Accession:", "LSD-26-0922-7731"],
    ["MRN:", "MRN-TEST-48213", "Status:", "FINAL"],
    ["Phone:", "+1 416 555 0199", "", ""],
    ["Test", "Result", "Units", "Reference Range"],
    ["Cholesterol, Total", "6.1 H", "mmol/L", "< 5.2"],
    ["HDL Cholesterol", "1.2", "mmol/L", "> 1.0"],
    ["Hematocrit", "0.30 L", "L/L", "0.36 - 0.46"],
    ["Vitamin D, 25-OH", "<25 L", "nmol/L", "> 50"],
    ["Ferritin", "Pending", "ug/L", "15 - 150"],
]
