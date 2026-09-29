"""What the PDF intake reads, what it refuses to guess, and what it writes.

Every rule in app/ingest/pdf.py is a decision to miss rather than guess; most of
these tests pin one of those decisions, using the failure the old parser had.
"""
import pytest

from app.db.tenancy import TenantScope
from app.ingest.pdf import PdfRejected, parse_pdf
from tests.pdf_fixtures import LAB_REPORT, make_pdf

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture
def report():
    return parse_pdf(make_pdf(LAB_REPORT))


# -- demographics -----------------------------------------------------------


def test_side_by_side_fields_split_on_the_next_label(report):
    info = report.patient_info
    assert info["name"] == "Rahim Uddin"
    assert info["dob"] == "1968-03-15"
    assert info["mrn"] == "DDC-20931"
    assert info["phone"] == "+8801712345678"
    assert info["insurance"] == "Green Delta Health"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("15/03/1968", "1968-03-15"),  # day > 12: day first
        ("03/15/1968", "1968-03-15"),  # second part > 12: month first
        ("1968-03-15", "1968-03-15"),
        ("03/04/1968", None),  # March or April — refuses to choose
    ],
)
def test_an_ambiguous_date_of_birth_is_left_empty(written, expected):
    doc = parse_pdf(make_pdf([f"Name: A B", f"DOB: {written}"]))
    assert doc.patient_info.get("dob") == expected
    if expected is None:
        assert any("ambiguous" in w for w in doc.warnings)


def test_a_local_phone_number_is_not_given_a_country_code():
    doc = parse_pdf(make_pdf(["Name: Karim", "Mobile: 01712-345678"]))
    assert doc.patient_info["phone"] == "01712345678"
    assert any("country code" in w for w in doc.warnings)


def test_an_unlabelled_name_is_not_read_as_one():
    doc = parse_pdf(make_pdf(["Rahim Uddin", "Phone: +8801712345678"]))
    assert "name" not in doc.patient_info


def test_a_bangla_name_is_accepted():
    # Type1 Helvetica cannot draw Bangla, so test the field logic directly.
    from app.ingest.pdf import extract_patient_info

    info, _ = extract_patient_info("Patient Name: রহিম উদ্দিন   Age: 58")
    assert info["name"] == "রহিম উদ্দিন"


# -- lab results ------------------------------------------------------------


def test_only_lines_with_a_unit_and_reference_range_are_results(report):
    names = [r["test_name"] for r in report.lab_results]
    assert names == ["HbA1c", "Fasting Glucose", "Haemoglobin", "Potassium"]
    # The old "any words followed by a number" rule took all of these.
    for noise in ("House", "Page", "Age", "Collection Date", "Dhanmondi"):
        assert not any(noise in n for n in names)


def test_flags_come_from_the_range_not_the_lab_marker(report):
    flags = {r["test_name"]: r["flag"] for r in report.lab_results}
    assert flags == {
        "HbA1c": "high",
        "Fasting Glucose": "high",
        "Haemoglobin": "normal",
        "Potassium": "low",
    }


# -- medications ------------------------------------------------------------


def test_medications_come_only_from_the_medications_section(report):
    assert report.medications == [
        {"name": "Metformin", "dosage": "500 mg", "status": "active"},
        {"name": "Amlodipine", "dosage": "5mg", "status": "active"},
    ]


def test_an_allergy_is_not_recorded_as_a_prescription(report):
    # The old keyword scan found "aspirin" anywhere in the text.
    assert "aspirin" not in {m["name"].lower() for m in report.medications}


# -- rejection --------------------------------------------------------------


def test_a_file_that_is_not_a_pdf_is_refused():
    with pytest.raises(PdfRejected, match="not a PDF"):
        parse_pdf(b"<html>definitely a pdf</html>")


def test_a_damaged_pdf_is_refused_without_quoting_it():
    with pytest.raises(PdfRejected) as caught:
        parse_pdf(b"%PDF-1.4\nRahim Uddin garbage")
    assert "Rahim" not in str(caught.value)


def test_a_scanned_pdf_with_no_text_says_so():
    doc = parse_pdf(make_pdf([]))
    assert doc.patient_info == {}
    assert any("scanned" in w for w in doc.warnings)


# -- the route --------------------------------------------------------------


def _upload(client, auth_header, lines, subject=ALICE, **form):
    return client.post(
        "/api/pdf/intake",
        files={"file": ("report.pdf", make_pdf(lines), "application/pdf")},
        data=form,
        headers=auth_header(subject),
    )


def test_intake_creates_the_patient_medications_and_document(client, fake_db, auth_header):
    response = _upload(client, auth_header, LAB_REPORT)
    assert response.status_code == 201, response.text
    body = response.json()

    patient = body["patient"]
    assert patient["name"] == "Rahim Uddin"
    assert patient["doctor_id"] == ALICE
    assert body["created_medications"] == 2
    assert len(body["extracted"]["lab_results"]) == 4

    (document,) = fake_db.store["pdf_documents"]
    assert document["patient_id"] == patient["id"]
    assert document["uploaded_by"] == ALICE
    assert "HbA1c" in document["raw_text"]
    assert len(fake_db.store["patient_medications"]) == 2


def test_the_doctor_id_form_field_is_ignored(client, fake_db, auth_header):
    response = _upload(client, auth_header, LAB_REPORT, doctor_id=BOB)
    assert response.status_code == 201
    assert response.json()["patient"]["doctor_id"] == ALICE
    assert TenantScope(fake_db, BOB).list_owned("patients") == []


def test_no_patient_is_invented_when_name_or_phone_is_missing(client, fake_db, auth_header):
    response = _upload(client, auth_header, ["Name: Rahim Uddin", "HbA1c 8.2 % 4.0-5.6"])
    assert response.status_code == 422
    assert "phone number" in response.json()["error"]["message"]
    assert not fake_db.store.get("patients")


def test_a_non_pdf_upload_is_422(client, fake_db, auth_header):
    response = client.post(
        "/api/pdf/intake",
        files={"file": ("report.pdf", b"not a pdf", "application/pdf")},
        headers=auth_header(ALICE),
    )
    assert response.status_code == 422
    assert not fake_db.store.get("patients")


def test_intake_requires_a_token(unauthenticated_client):
    response = unauthenticated_client.post(
        "/api/pdf/intake",
        files={"file": ("report.pdf", make_pdf(LAB_REPORT), "application/pdf")},
    )
    assert response.status_code == 401
