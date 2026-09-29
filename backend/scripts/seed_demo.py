#!/usr/bin/env python
"""Demo data: patient PDFs to import, and a busy week on the calendar.

    python scripts/seed_demo.py pdfs            # write patient PDFs to ../demo/pdfs
    python scripts/seed_demo.py week            # book the next five open days
    python scripts/seed_demo.py week --dry-run  # show what would be booked
    python scripts/seed_demo.py clear           # remove everything `week` added

`week` books against the practice's own clinic hours (Settings -> Clinic hours)
in its timezone, starting tomorrow, so the agent's earliest offers land in the
busy days. Each open day gets a different shape, so every branch of the agent's
behaviour has something to hit:

    day 1   full except 10:00-11:00   "only ten or half past ten"
    day 2   fully booked              "that day is full — the next free is ..."
    day 3   booked all morning        "afternoon only"
    day 4   two bookings              "most of the day"
    day 5   lunch hour only           "anything but twelve"

Closed days are skipped and stay closed. The appointments belong to placeholder
patients named "Demo ..." and carry SEED_MARKER in their notes; `clear`
soft-deletes exactly those rows and nothing else, so real bookings are safe.

Writes go through TenantScope, the same checks a signed-in request gets. The
PDFs are synthetic — no real person — and parse with the app's own importer
before they are written, so a PDF that would import badly is never produced.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.db.client import get_supabase  # noqa: E402
from app.db.tenancy import TenantScope  # noqa: E402
from app.ingest.pdf import parse_pdf  # noqa: E402
from app.scheduling.practice import load_schedule  # noqa: E402
from tests.pdf_fixtures import make_pdf  # noqa: E402

SEED_MARKER = "clarus-demo-seed"
DEFAULT_PDF_DIR = Path(__file__).resolve().parents[2] / "demo" / "pdfs"

# Busy blocks per day, in clinic-local time. The shapes are described in the
# module docstring; they assume a day open at least 09:00-17:00, and a block
# that falls outside a day's actual hours is skipped with a note.
DAY_SHAPES: list[tuple[str, list[tuple[str, str]]]] = [
    ("full except 10:00-11:00", [("09:00", "10:00"), ("11:00", "13:00"), ("13:00", "15:00"), ("15:00", "17:00")]),
    ("fully booked", [("09:00", "11:00"), ("11:00", "13:00"), ("13:00", "15:00"), ("15:00", "17:00")]),
    ("booked all morning", [("09:00", "10:30"), ("10:30", "13:00")]),
    ("two bookings", [("09:30", "10:30"), ("14:00", "15:00")]),
    ("lunch hour only", [("12:00", "13:00")]),
]

# Placeholder patients who own the busy blocks. Never called by a workflow:
# their phones are unassigned numbers in the allowlist-free web transport, and
# they are removed by `clear`.
FILLER_PATIENTS = [
    ("Demo Karim Hossain", "+8801700000101"),
    ("Demo Nasrin Akter", "+8801700000102"),
    ("Demo Jamal Uddin", "+8801700000103"),
    ("Demo Farhana Begum", "+8801700000104"),
]

# Synthetic patients for the PDF importer. Dates of birth have a day above 12,
# because the importer rightly refuses to guess whether 03/04 is March or April.
PDF_PATIENTS = [
    {
        "file": "01-rahim-uddin-lab-report.pdf",
        "lines": [
            "Dhaka Diagnostic Centre - Laboratory Report",
            "Patient Name: Rahim Uddin   Date of Birth: 15/03/1968",
            "MRN: DDC-30101   Phone: +8801711000101",
            "Insurance: Green Delta Health",
            "Collection Date: 21/09/2026",
            "Test Result Unit Reference",
            "HbA1c 8.2 % 4.0-5.6",
            "Fasting Glucose 142 mg/dL 70-100",
            "Haemoglobin 13.1 g/dL 13.0-17.0",
            "Current Medications:",
            "1. Metformin 500 mg twice daily",
            "2. Amlodipine 5mg",
        ],
    },
    {
        "file": "02-fatema-khatun-follow-up.pdf",
        "lines": [
            "Square Hospital - Outpatient Summary",
            "Patient Name: Fatema Khatun   Date of Birth: 22/07/1975",
            "MRN: SQH-44821   Phone: +8801811000202",
            "Insurance: MetLife Bangladesh",
            "Visit Date: 18/09/2026",
            "Test Result Unit Reference",
            "Systolic BP 148 mmHg 90-130",
            "Total Cholesterol 231 mg/dL 125-200",
            "Current Medications:",
            "1. Losartan 50 mg once daily",
            "2. Atorvastatin 20 mg at night",
        ],
    },
    {
        "file": "03-abdul-karim-annual-check.pdf",
        "lines": [
            "Labaid Diagnostic - Annual Health Check",
            "Patient Name: Abdul Karim   Date of Birth: 30/11/1959",
            "MRN: LAB-77310   Phone: +8801911000303",
            "Insurance: Pragati Life",
            "Report Date: 24/09/2026",
            "Test Result Unit Reference",
            "Creatinine 1.4 mg/dL 0.7-1.3",
            "TSH 2.1 mIU/L 0.4-4.0",
            "Current Medications:",
            "1. Aspirin 75 mg once daily",
        ],
    },
    {
        "file": "04-sharmin-sultana-prenatal.pdf",
        "lines": [
            "Evercare Hospital - Antenatal Clinic",
            "Patient Name: Sharmin Sultana   Date of Birth: 14/02/1994",
            "MRN: EVC-12094   Phone: +8801611000404",
            "Insurance: Guardian Life",
            "Visit Date: 25/09/2026",
            "Test Result Unit Reference",
            "Haemoglobin 10.8 g/dL 11.0-15.0",
            "Ferritin 9 ng/mL 15-150",
            "Current Medications:",
            "1. Folic acid 5 mg once daily",
            "2. Ferrous sulfate 200 mg twice daily",
        ],
    },
]


def _hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def write_pdfs(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for patient in PDF_PATIENTS:
        data = make_pdf(patient["lines"])
        doc = parse_pdf(data)
        info = doc.patient_info
        # Refuse to write a PDF the importer would read badly.
        missing = [f for f in ("name", "phone", "dob") if not info.get(f)]
        if missing:
            print(f"ERROR: {patient['file']} parses without {missing}: {doc.warnings}", file=sys.stderr)
            return 1
        (out_dir / patient["file"]).write_bytes(data)
        print(
            f"  {patient['file']}: {info['name']}, {info['phone']}, born {info['dob']}, "
            f"{len(doc.medications)} medications, {len(doc.lab_results)} lab results"
        )
    print(f"\nWrote {len(PDF_PATIENTS)} PDFs to {out_dir}")
    return 0


def _resolve_doctor(client, doctor_id: str | None) -> str:
    if doctor_id:
        return doctor_id
    rows = list(getattr(client.table("doctors").select("id").execute(), "data", None) or [])
    if len(rows) != 1:
        raise SystemExit(
            f"Found {len(rows)} practices; pass --doctor-id (the Clerk user id, "
            f"shown on Settings as Clerk ID)."
        )
    return rows[0]["id"]


def _filler_patients(scope: TenantScope, dry_run: bool) -> list[str]:
    existing = {
        p["name"]: p["id"]
        for p in scope.list_owned("patients")
        if (p.get("notes") or "") == SEED_MARKER
    }
    ids = []
    for name, phone in FILLER_PATIENTS:
        if name in existing:
            ids.append(existing[name])
        elif dry_run:
            ids.append(f"<new {name}>")
        else:
            row = scope.insert_owned(
                "patients", {"name": name, "phone": phone, "notes": SEED_MARKER}
            )
            ids.append(row["id"])
    return ids


def seed_week(doctor_id: str | None, dry_run: bool) -> int:
    settings = get_settings()
    client = get_supabase()
    scope = TenantScope(client, _resolve_doctor(client, doctor_id))
    schedule = load_schedule(scope, settings)
    if not schedule.configured:
        print(
            "ERROR: this practice has no clinic hours yet. Set them in the app "
            "(Settings -> Clinic hours) and run this again.",
            file=sys.stderr,
        )
        return 1

    patients = _filler_patients(scope, dry_run)
    today = datetime.now(schedule.zone).date()
    day = today
    booked = skipped = 0
    shapes = iter(DAY_SHAPES)
    shape = next(shapes)
    print(f"Practice {scope.doctor_id}, times in {settings.default_timezone}\n")

    for _ in range(settings.availability_horizon_days):
        day += timedelta(days=1)
        if not schedule.ranges_on(day):
            continue
        label, blocks = shape
        print(f"{day.strftime('%A %d %B')}: {label}")
        for i, (start, end) in enumerate(blocks):
            starts = datetime.combine(day, _hhmm(start), tzinfo=schedule.zone)
            minutes = int((datetime.combine(day, _hhmm(end)) - datetime.combine(day, _hhmm(start))).total_seconds() // 60)
            # Outside this day's hours, or on top of something already booked
            # (a real appointment, or a previous seed run): leave it.
            problem = schedule.booking_problem(starts, minutes, enforce_hours=True)
            if problem:
                print(f"    skip {start}-{end}: {problem}")
                skipped += 1
                continue
            print(f"    book {start}-{end}")
            if not dry_run:
                scope.insert_owned(
                    "appointments",
                    {
                        "patient_id": patients[i % len(patients)],
                        "starts_at": starts.isoformat(),
                        "ends_at": (starts + timedelta(minutes=minutes)).isoformat(),
                        "status": "scheduled",
                        "reason": "Demo booking",
                        "notes": SEED_MARKER,
                    },
                )
            booked += 1
        shape = next(shapes, None)
        if shape is None:
            break

    verb = "Would book" if dry_run else "Booked"
    print(f"\n{verb} {booked} appointments ({skipped} skipped).")
    if not dry_run:
        print("Remove them later with: python scripts/seed_demo.py clear")
    return 0


def clear(doctor_id: str | None) -> int:
    client = get_supabase()
    scope = TenantScope(client, _resolve_doctor(client, doctor_id))
    appointments = [
        a for a in scope.list_owned("appointments") if (a.get("notes") or "") == SEED_MARKER
    ]
    patients = [
        p for p in scope.list_owned("patients") if (p.get("notes") or "") == SEED_MARKER
    ]
    for row in appointments:
        scope.delete_owned("appointments", row["id"])
    for row in patients:
        scope.delete_owned("patients", row["id"])
    print(f"Removed {len(appointments)} demo appointments and {len(patients)} demo patients.")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    pdfs = sub.add_parser("pdfs", help="write synthetic patient PDFs")
    pdfs.add_argument("--out", type=Path, default=DEFAULT_PDF_DIR)
    week = sub.add_parser("week", help="book the next five open days")
    week.add_argument("--doctor-id")
    week.add_argument("--dry-run", action="store_true")
    wipe = sub.add_parser("clear", help="remove what `week` added")
    wipe.add_argument("--doctor-id")
    args = parser.parse_args()

    if args.command == "pdfs":
        return write_pdfs(args.out)
    if args.command == "week":
        return seed_week(args.doctor_id, args.dry_run)
    return clear(args.doctor_id)


if __name__ == "__main__":
    raise SystemExit(main())
