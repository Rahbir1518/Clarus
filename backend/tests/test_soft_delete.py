"""Deleting PHI marks it; deleting everything else removes it.

The distinction is the point of these tests. A soft delete that is only half
applied — stamped on the way in but not filtered on the way out — looks exactly
like a working delete until someone lists the table.
"""
import pytest

from app.core.errors import NotFound
from app.db.tenancy import TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture
def scope(fake_db: FakeSupabase) -> TenantScope:
    return TenantScope(fake_db, ALICE)


def _patient(scope: TenantScope) -> dict:
    return scope.insert_owned("patients", {"name": "Jane", "phone": "+15551234567"})


def test_deleted_patient_is_stamped_not_removed(scope, fake_db):
    patient = _patient(scope)

    scope.delete_owned("patients", patient["id"])

    stored = fake_db.store["patients"]
    assert len(stored) == 1, "the row must survive the delete"
    assert stored[0]["deleted_at"] is not None


def test_deleted_patient_is_invisible_to_every_read(scope):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    assert scope.list_owned("patients") == []
    with pytest.raises(NotFound):
        scope.get_owned("patients", patient["id"])


def test_deleted_patient_cannot_be_updated(scope):
    """Otherwise a delete is undone by any subsequent write to the same id."""
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.update_owned("patients", patient["id"], {"name": "Resurrected"})


def test_deleting_twice_is_not_found(scope):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.delete_owned("patients", patient["id"])


def test_deleted_at_cannot_be_supplied_by_a_client(scope):
    """A create or update carrying deleted_at would let a caller delete a record
    through an endpoint that only claims to modify it."""
    patient = scope.insert_owned(
        "patients", {"name": "Jane", "phone": "+1555", "deleted_at": "2020-01-01"}
    )
    assert patient.get("deleted_at") is None
    assert len(scope.list_owned("patients")) == 1

    scope.update_owned("patients", patient["id"], {"deleted_at": "2020-01-01"})
    assert len(scope.list_owned("patients")) == 1


def test_clinical_children_are_soft_deleted_too(scope, fake_db):
    patient = _patient(scope)
    condition = scope.insert_for_patient(
        "patient_conditions", patient["id"], {"icd10_code": "E11.9", "description": "T2DM"}
    )

    scope.delete_for_patient("patient_conditions", patient["id"], condition["id"])

    assert len(fake_db.store["patient_conditions"]) == 1
    assert fake_db.store["patient_conditions"][0]["deleted_at"] is not None
    assert scope.list_for_patient("patient_conditions", patient["id"]) == []


def test_deleting_a_patient_hides_their_clinical_records(scope):
    """The cascade is still declared in the schema, so a hard delete would have
    destroyed these. Nothing about them is reachable now, but they are all still
    there to be retrieved by someone with database access."""
    patient = _patient(scope)
    scope.insert_for_patient(
        "patient_medications", patient["id"], {"name": "Metformin"}
    )

    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.list_for_patient("patient_medications", patient["id"])


def test_operational_records_are_still_hard_deleted(scope, fake_db):
    """notifications holds no clinical history, so there is nothing to retain."""
    patient = _patient(scope)
    note = scope.insert_for_patient(
        "notifications", patient["id"], {"recipient": "front-desk", "message": "Call back"}
    )

    scope.delete_for_patient("notifications", patient["id"], note["id"])

    assert fake_db.store["notifications"] == []


def test_workflows_are_still_hard_deleted(scope, fake_db):
    """A workflow is automation configuration, not a medical record."""
    workflow = scope.insert_owned("workflows", {"name": "Post-discharge follow-up"})

    scope.delete_owned("workflows", workflow["id"])

    assert fake_db.store["workflows"] == []


def test_one_tenants_delete_does_not_touch_another(fake_db):
    alice, bob = TenantScope(fake_db, ALICE), TenantScope(fake_db, BOB)
    theirs = _patient(bob)

    with pytest.raises(NotFound):
        alice.delete_owned("patients", theirs["id"])

    assert bob.get_owned("patients", theirs["id"])["id"] == theirs["id"]
    # .get(): Postgres returns deleted_at as None, the in-memory store simply
    # has no such key until something writes one.
    assert fake_db.store["patients"][0].get("deleted_at") is None
