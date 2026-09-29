"""Unit tests for the scoping primitive itself."""
import pytest

from app.core.errors import NotFound
from app.db.tenancy import TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture
def scope(fake_db: FakeSupabase) -> TenantScope:
    return TenantScope(fake_db, ALICE)


def test_empty_doctor_id_is_refused(fake_db):
    """A falsy tenant key would match rows with NULL or empty doctor_id."""
    with pytest.raises(ValueError):
        TenantScope(fake_db, "")


def test_unknown_table_is_refused(scope):
    with pytest.raises(ValueError, match="not a tenant-owned table"):
        scope.list_owned("secrets")


def test_child_table_cannot_be_read_as_tenant_owned(scope):
    """patient_conditions has no doctor_id; reaching it this way would be unscoped."""
    with pytest.raises(ValueError, match="not a tenant-owned table"):
        scope.list_owned("patient_conditions")


def test_tenant_table_cannot_be_read_as_a_child_table(scope):
    with pytest.raises(ValueError, match="not a patient-owned table"):
        scope.list_for_patient("workflows", "some-patient-id")


def test_insert_overrides_a_forged_doctor_id(scope):
    row = scope.insert_owned(
        "workflows", {"name": "W", "doctor_id": BOB, "id": "forced-id"}
    )
    assert row["doctor_id"] == ALICE
    assert row["id"] != "forced-id"


def test_child_rows_require_an_owned_parent(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})
    alice.insert_for_patient(
        "patient_conditions", patient["id"], {"icd10_code": "E11.9", "description": "T2DM"}
    )

    assert len(alice.list_for_patient("patient_conditions", patient["id"])) == 1

    # Bob knows the patient id but does not own the patient.
    with pytest.raises(NotFound):
        bob.list_for_patient("patient_conditions", patient["id"])
    with pytest.raises(NotFound):
        bob.insert_for_patient(
            "patient_conditions", patient["id"], {"icd10_code": "I10", "description": "HTN"}
        )


def test_tenant_owned_row_may_reference_an_owned_patient(fake_db):
    """call_logs carries a real patient_id — it must survive the sanitiser."""
    alice = TenantScope(fake_db, ALICE)
    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    log = alice.insert_owned(
        "call_logs", {"patient_id": patient["id"], "status": "pending"}
    )
    assert log["patient_id"] == patient["id"]
    assert log["doctor_id"] == ALICE


def test_tenant_owned_row_cannot_reference_another_tenants_patient(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    theirs = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    with pytest.raises(NotFound):
        bob.insert_owned("call_logs", {"patient_id": theirs["id"], "status": "pending"})


def test_patient_id_cannot_be_reassigned_by_update(fake_db):
    alice = TenantScope(fake_db, ALICE)
    first = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})
    second = alice.insert_owned("patients", {"name": "John", "phone": "+1556"})

    log = alice.insert_owned("call_logs", {"patient_id": first["id"], "status": "pending"})
    updated = alice.update_owned(
        "call_logs", log["id"], {"patient_id": second["id"], "status": "done"}
    )

    assert updated["status"] == "done"
    assert updated["patient_id"] == first["id"]


def test_update_with_only_immutable_fields_is_a_no_op(scope):
    patient = scope.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    unchanged = scope.update_owned(
        "patients", patient["id"], {"id": "new", "doctor_id": BOB, "created_at": "1999"}
    )
    assert unchanged["id"] == patient["id"]
    assert unchanged["doctor_id"] == ALICE


# -- foreign keys pointing out of the tenant --------------------------------
#
# Each of these writes a row the caller genuinely owns. The row is not the
# problem; where it points is.


def test_a_referral_cannot_be_attributed_to_another_doctor(fake_db):
    """referring_doctor_id is a plain FK to doctors, so any subject satisfies
    the database. Alice's own patient, Alice's own referral — and Bob's name on
    it as the clinician who made it."""
    alice = TenantScope(fake_db, ALICE)
    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    with pytest.raises(NotFound):
        alice.insert_for_patient(
            "referrals",
            patient["id"],
            {"specialty": "cardiology", "reason": "chest pain",
             "urgency": "emergent", "referring_doctor_id": BOB},
        )


def test_a_referral_may_name_the_caller(fake_db):
    alice = TenantScope(fake_db, ALICE)
    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    referral = alice.insert_for_patient(
        "referrals",
        patient["id"],
        {"specialty": "cardiology", "reason": "chest pain",
         "referring_doctor_id": ALICE},
    )
    assert referral["referring_doctor_id"] == ALICE


def test_a_prescription_cannot_be_attributed_to_another_doctor(fake_db):
    alice = TenantScope(fake_db, ALICE)
    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    with pytest.raises(NotFound):
        alice.insert_for_patient(
            "patient_medications",
            patient["id"],
            {"name": "warfarin", "prescriber_doctor_id": BOB},
        )


def test_a_row_cannot_reference_another_tenants_workflow(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    theirs = bob.insert_owned("workflows", {"name": "Bob's protocol"})

    with pytest.raises(NotFound):
        alice.insert_owned(
            "call_logs", {"status": "pending", "workflow_id": theirs["id"]}
        )


def test_a_reference_cannot_be_smuggled_in_by_update(fake_db):
    """The insert path is not the only way in — an update carries the same
    foreign keys."""
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    theirs = bob.insert_owned("workflows", {"name": "Bob's protocol"})
    log = alice.insert_owned("call_logs", {"status": "pending"})

    with pytest.raises(NotFound):
        alice.update_owned("call_logs", log["id"], {"workflow_id": theirs["id"]})


def test_an_appointment_cannot_reference_another_tenants_call_log(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    theirs = bob.insert_owned("call_logs", {"status": "done"})
    mine = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    with pytest.raises(NotFound):
        alice.insert_owned(
            "appointments",
            {"patient_id": mine["id"], "starts_at": "2030-01-01T09:00:00Z",
             "call_log_id": theirs["id"]},
        )


# -- the allowlist ----------------------------------------------------------


def test_webhook_correlation_keys_are_not_client_writable(scope, fake_db):
    """conversation_id resolves an inbound provider webhook to one call log,
    under a unique index. A caller who could set it could squat the id of a
    call they do not own and receive its transcript."""
    scope.insert_owned(
        "call_logs",
        {"status": "pending", "conversation_id": "conv_someone_else",
         "transcript": "forged"},
    )
    stored = fake_db.store["call_logs"][0]
    assert "conversation_id" not in stored
    assert "transcript" not in stored


def test_upload_provenance_comes_from_the_token(scope, fake_db):
    patient = scope.insert_owned("patients", {"name": "Jane", "phone": "+1555"})
    scope.insert_for_patient(
        "pdf_documents",
        patient["id"],
        {"filename": "labs.pdf", "uploaded_by": BOB},
    )
    assert fake_db.store["pdf_documents"][0]["uploaded_by"] == ALICE


def test_cross_tenant_mutations_raise_not_found(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    patient = alice.insert_owned("patients", {"name": "Jane", "phone": "+1555"})

    with pytest.raises(NotFound):
        bob.get_owned("patients", patient["id"])
    with pytest.raises(NotFound):
        bob.update_owned("patients", patient["id"], {"name": "Hijacked"})
    with pytest.raises(NotFound):
        bob.delete_owned("patients", patient["id"])

    assert alice.get_owned("patients", patient["id"])["name"] == "Jane"
