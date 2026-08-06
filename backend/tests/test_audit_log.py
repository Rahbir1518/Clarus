"""The audit trail primitive.

audit_log is reachable only through record_audit and list_audit_events. The
generic CRUD methods must not accept it, because the table has a trigger
forbidding UPDATE and DELETE — offering those operations here would mean
offering calls that can only ever fail in the database.
"""
import pytest

from app.db.tenancy import PATIENT_CHILD_TABLES, TENANT_TABLES, TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture
def scope(fake_db: FakeSupabase) -> TenantScope:
    return TenantScope(fake_db, ALICE)


def test_audit_log_is_not_reachable_through_generic_crud():
    assert "audit_log" not in TENANT_TABLES
    assert "audit_log" not in PATIENT_CHILD_TABLES


def test_generic_crud_refuses_the_table(scope):
    with pytest.raises(ValueError, match="not a tenant-owned table"):
        scope.list_owned("audit_log")
    with pytest.raises(ValueError, match="not a tenant-owned table"):
        scope.delete_owned("audit_log", "some-id")


def test_recorded_event_carries_the_tenant_and_the_actor(scope):
    event = scope.record_audit(action="patient.read", entity_type="patient")

    assert event["doctor_id"] == ALICE
    assert event["actor"] == ALICE
    assert event["action"] == "patient.read"
    assert event["metadata"] == {}


def test_events_are_scoped_to_the_tenant(fake_db):
    alice = TenantScope(fake_db, ALICE)
    bob = TenantScope(fake_db, BOB)

    alice.record_audit(action="patient.read", entity_type="patient")
    bob.record_audit(action="patient.delete", entity_type="patient")

    assert [e["action"] for e in alice.list_audit_events()] == ["patient.read"]
    assert [e["action"] for e in bob.list_audit_events()] == ["patient.delete"]


def test_an_event_outlives_the_record_it_describes(scope):
    """patient_id is intentionally not a foreign key: the trail must survive
    the deletion of what it describes."""
    patient = scope.insert_owned("patients", {"name": "Jane", "phone": "+1555"})
    scope.record_audit(
        action="patient.read", entity_type="patient", patient_id=patient["id"]
    )
    scope.delete_owned("patients", patient["id"])

    events = scope.list_audit_events()
    assert len(events) == 1
    assert events[0]["patient_id"] == patient["id"]


def test_listing_respects_the_limit(scope):
    for i in range(5):
        scope.record_audit(action=f"a{i}", entity_type="patient")

    assert len(scope.list_audit_events(limit=2)) == 2
