"""Tenant provisioning.

Every tenant-owned table has a foreign key to `doctors(id)`. The fake store
enforces no constraints, so these tests assert the row is written rather than
waiting for a real Postgres to reject the insert — the FK violation would
otherwise only appear in production, on a doctor's first ever request.
"""
import pytest

from app.db import doctors as doctors_db
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


def _doctors(fake_db: FakeSupabase) -> list[dict]:
    return fake_db.store.get("doctors", [])


def test_first_request_creates_the_doctors_row(client, auth_header, fake_db):
    client.get("/api/patients", headers=auth_header(ALICE))

    assert [d["id"] for d in _doctors(fake_db)] == [ALICE]


def test_profile_claims_populate_the_row_when_present(client, auth_header, fake_db):
    client.get(
        "/api/patients",
        headers=auth_header(ALICE, name="Dr Alice Ng", email="alice@clinic.test"),
    )

    row = _doctors(fake_db)[0]
    assert row["name"] == "Dr Alice Ng"
    assert row["email"] == "alice@clinic.test"


def test_subject_stands_in_for_a_missing_name(client, auth_header, fake_db):
    """`name` is NOT NULL, and an access token need not carry profile claims."""
    client.get("/api/patients", headers=auth_header(ALICE))

    row = _doctors(fake_db)[0]
    assert row["name"] == ALICE
    assert row["email"] is None


def test_provisioning_happens_once_per_subject(client, auth_header, fake_db):
    for _ in range(3):
        client.get("/api/patients", headers=auth_header(ALICE))

    assert len(_doctors(fake_db)) == 1


def test_each_subject_gets_its_own_row(client, auth_header, fake_db):
    client.get("/api/patients", headers=auth_header(ALICE))
    client.get("/api/patients", headers=auth_header(BOB))

    assert sorted(d["id"] for d in _doctors(fake_db)) == sorted([ALICE, BOB])


def test_an_unauthenticated_request_provisions_nothing(unauthenticated_client, fake_db):
    assert unauthenticated_client.get("/api/patients").status_code == 401
    assert _doctors(fake_db) == []


def test_an_existing_row_is_not_overwritten(client, auth_header, fake_db):
    """A doctor who has edited their profile must not have it reset by the
    next request that happens to carry a stale claim."""
    fake_db.store["doctors"] = [
        {"id": ALICE, "name": "Dr A. Ng, MD", "email": "alice@clinic.test"}
    ]

    client.get("/api/patients", headers=auth_header(ALICE, name="Alice"))

    assert _doctors(fake_db) == [
        {"id": ALICE, "name": "Dr A. Ng, MD", "email": "alice@clinic.test"}
    ]


def test_a_concurrent_insert_does_not_fail_the_request(fake_db, monkeypatch):
    """Two first requests race; one loses on the primary key. The loser must
    confirm the row landed rather than propagating the collision."""
    calls: list[str] = []
    real_table = fake_db.table

    def racing_table(name: str):
        query = real_table(name)
        if name == "doctors":

            def insert(payload):
                calls.append("insert")
                # The winner commits first, then our insert collides.
                fake_db.store.setdefault("doctors", []).append(dict(payload))
                raise RuntimeError("duplicate key value violates unique constraint")

            query.insert = insert  # type: ignore[method-assign]
        return query

    monkeypatch.setattr(fake_db, "table", racing_table)

    doctors_db.ensure_doctor(fake_db, doctor_id=ALICE, name="Alice")

    assert calls == ["insert"]
    assert [d["id"] for d in _doctors(fake_db)] == [ALICE]


def test_a_genuine_insert_failure_still_raises(fake_db, monkeypatch):
    """Swallowing the collision must not swallow a real database error."""

    def failing_table(name: str):
        class _Q:
            def select(self, *_a, **_k):
                return self

            def eq(self, *_a, **_k):
                return self

            def execute(self):
                return type("R", (), {"data": []})()

            def insert(self, _payload):
                raise RuntimeError("connection refused")

        return _Q()

    monkeypatch.setattr(fake_db, "table", failing_table)

    with pytest.raises(RuntimeError, match="connection refused"):
        doctors_db.ensure_doctor(fake_db, doctor_id=ALICE)


def test_empty_subject_is_refused(fake_db):
    with pytest.raises(ValueError):
        doctors_db.ensure_doctor(fake_db, doctor_id="")
