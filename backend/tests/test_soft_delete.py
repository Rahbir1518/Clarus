"""Soft deletion.

The schema gives most clinical tables a `deleted_at` column instead of relying
on DELETE. The property worth protecting is that a deleted row is invisible to
*every* read path, not just the one whose handler remembered to filter — which
is why these tests go through TenantScope rather than the HTTP layer for the
child tables.
"""
import pytest

from app.core.errors import NotFound
from app.db.tenancy import SOFT_DELETE_TABLES, TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"


@pytest.fixture
def scope(fake_db: FakeSupabase) -> TenantScope:
    return TenantScope(fake_db, ALICE)


def _patient(scope: TenantScope, name: str = "Jane") -> dict:
    return scope.insert_owned("patients", {"name": name, "phone": "+15551234567"})


# -- tenant-owned tables ----------------------------------------------------


def test_delete_sets_deleted_at_rather_than_removing_the_row(scope, fake_db):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    stored = fake_db.store["patients"]
    assert len(stored) == 1, "the row should still be in the table"
    assert stored[0]["deleted_at"] is not None


def test_deleted_row_is_absent_from_reads(scope):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    assert scope.list_owned("patients") == []
    with pytest.raises(NotFound):
        scope.get_owned("patients", patient["id"])


def test_deleted_row_cannot_be_updated(scope):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.update_owned("patients", patient["id"], {"name": "Resurrected"})


def test_deleting_twice_is_404(scope):
    """Not idempotent on purpose: a second delete must not overwrite the
    timestamp recording when the first one happened."""
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.delete_owned("patients", patient["id"])


def test_a_request_body_cannot_delete_or_undelete(scope, fake_db):
    """deleted_at is a system field. Neither setting nor clearing it is
    something a client payload gets to do."""
    patient = _patient(scope)
    scope.update_owned("patients", patient["id"], {"deleted_at": "2020-01-01T00:00:00Z"})
    assert fake_db.store["patients"][0].get("deleted_at") is None

    scope.delete_owned("patients", patient["id"])
    with pytest.raises(NotFound):
        # The row is gone from every read, so there is nothing to update.
        scope.update_owned("patients", patient["id"], {"deleted_at": None})
    assert fake_db.store["patients"][0]["deleted_at"] is not None


def test_workflows_are_hard_deleted(scope, fake_db):
    """workflows has no deleted_at — it is retired via status='ARCHIVED' so
    the call logs referencing it keep a live foreign key."""
    assert "workflows" not in SOFT_DELETE_TABLES

    workflow = scope.insert_owned("workflows", {"name": "Lab follow-up"})
    scope.delete_owned("workflows", workflow["id"])

    assert fake_db.store["workflows"] == []


# -- patient-owned child tables ---------------------------------------------


def test_child_rows_soft_delete_and_disappear(scope, fake_db):
    patient = _patient(scope)
    condition = scope.insert_for_patient(
        "patient_conditions", patient["id"], {"icd10_code": "E11.9", "description": "T2DM"}
    )

    scope.delete_for_patient("patient_conditions", patient["id"], condition["id"])

    assert fake_db.store["patient_conditions"][0]["deleted_at"] is not None
    assert scope.list_for_patient("patient_conditions", patient["id"]) == []
    with pytest.raises(NotFound):
        scope.get_for_patient("patient_conditions", patient["id"], condition["id"])


def test_operational_child_rows_are_hard_deleted(scope, fake_db):
    """staff_assignments carries no deleted_at: it is reconstructible from the
    run that created it and is not a clinical record in its own right."""
    assert "staff_assignments" not in SOFT_DELETE_TABLES

    patient = _patient(scope)
    assignment = scope.insert_for_patient(
        "staff_assignments", patient["id"], {"staff_id": "s1", "task_type": "follow_up"}
    )
    scope.delete_for_patient("staff_assignments", patient["id"], assignment["id"])

    assert fake_db.store["staff_assignments"] == []


def test_child_rows_of_a_deleted_patient_are_unreachable(scope):
    """Ownership resolves through the parent, and the parent is gone."""
    patient = _patient(scope)
    scope.insert_for_patient(
        "patient_conditions", patient["id"], {"icd10_code": "I10", "description": "HTN"}
    )
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.list_for_patient("patient_conditions", patient["id"])
    with pytest.raises(NotFound):
        scope.insert_for_patient(
            "patient_conditions", patient["id"], {"icd10_code": "E78.5", "description": "HLD"}
        )


def test_a_call_log_cannot_reference_a_deleted_patient(scope):
    patient = _patient(scope)
    scope.delete_owned("patients", patient["id"])

    with pytest.raises(NotFound):
        scope.insert_owned("call_logs", {"patient_id": patient["id"], "status": "pending"})


# -- through the API --------------------------------------------------------


def test_deleted_patient_is_gone_from_the_http_api(client, auth_header):
    headers = auth_header(ALICE)
    created = client.post(
        "/api/patients", json={"name": "Jane Doe", "phone": "+15551234567"}, headers=headers
    ).json()

    assert client.delete(f"/api/patients/{created['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/patients/{created['id']}", headers=headers).status_code == 404
    assert client.get("/api/patients", headers=headers).json() == []
