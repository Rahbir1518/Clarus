"""The doctors row has to exist before anything references it.

Every doctor_id column is a foreign key to doctors now, and nothing asks a
clinician to fill in a profile before using the product. If the authenticated
request path does not create the row, the first patient a new doctor adds fails
on a foreign key violation.
"""
import pytest

from app.core.security import CurrentUser
from app.db.doctors import ensure_doctor, reset_cache
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


def _user(subject: str = ALICE, **claims) -> CurrentUser:
    return CurrentUser(subject=subject, scopes=frozenset(), claims={"sub": subject, **claims})


def _doctors(fake_db: FakeSupabase) -> list[dict]:
    return fake_db.store.get("doctors", [])


# --- through the HTTP layer -------------------------------------------------


def test_first_authenticated_request_creates_the_row(client, auth_header, fake_db):
    client.get("/api/patients", headers=auth_header(ALICE))

    assert [d["id"] for d in _doctors(fake_db)] == [ALICE]


def test_a_write_has_its_foreign_key_parent(client, auth_header, fake_db):
    response = client.post(
        "/api/patients",
        json={"name": "Jane Doe", "phone": "+15551234567"},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 201
    assert response.json()["doctor_id"] in {d["id"] for d in _doctors(fake_db)}


def test_each_tenant_gets_its_own_row(client, auth_header, fake_db):
    client.get("/api/patients", headers=auth_header(ALICE))
    client.get("/api/patients", headers=auth_header(BOB))

    assert {d["id"] for d in _doctors(fake_db)} == {ALICE, BOB}


def test_repeated_requests_create_one_row(client, auth_header, fake_db):
    for _ in range(5):
        client.get("/api/patients", headers=auth_header(ALICE))

    assert len(_doctors(fake_db)) == 1


def test_an_unauthenticated_request_provisions_nothing(client, fake_db):
    assert client.get("/api/patients").status_code == 401
    assert _doctors(fake_db) == []


# --- naming -----------------------------------------------------------------


def test_name_is_taken_from_the_token_when_it_carries_one(client, auth_header, fake_db):
    client.get("/api/patients", headers=auth_header(ALICE, name="Dr. Alice Chen"))

    assert _doctors(fake_db)[0]["name"] == "Dr. Alice Chen"


def test_name_falls_back_to_a_placeholder(fake_db):
    """The common case: an API access token carries `sub` and nothing else.
    doctors.name is NOT NULL, so there has to be something."""
    ensure_doctor(fake_db, _user())

    assert _doctors(fake_db)[0]["name"] == "Unknown"


def test_given_and_family_names_are_combined(fake_db):
    ensure_doctor(fake_db, _user(given_name="Alice", family_name="Chen"))

    assert _doctors(fake_db)[0]["name"] == "Alice Chen"


def test_email_is_the_last_resort_for_a_name(fake_db):
    ensure_doctor(fake_db, _user(email="alice@clinic.example"))

    row = _doctors(fake_db)[0]
    assert row["name"] == "alice@clinic.example"
    assert row["email"] == "alice@clinic.example"


def test_an_edited_profile_is_not_overwritten(fake_db):
    """Once a doctor sets their own name, NPI or practice, the identity provider
    is no longer the authority on it. This is why the write is insert-if-missing
    rather than an upsert that updates."""
    ensure_doctor(fake_db, _user(name="Alice Chen"))
    _doctors(fake_db)[0].update({"name": "Alice Chen, MD", "npi": "1234567893"})

    reset_cache()
    ensure_doctor(fake_db, _user(name="Alice Chen"))

    row = _doctors(fake_db)[0]
    assert row["name"] == "Alice Chen, MD"
    assert row["npi"] == "1234567893"


# --- failure handling -------------------------------------------------------


class _UpsertFails(FakeSupabase):
    def table(self, name: str):
        query = super().table(name)
        if name == "doctors":
            def _raise(*_args, **_kwargs):
                raise RuntimeError("connection reset by peer")

            query.upsert = _raise  # type: ignore[method-assign]
        return query


def test_a_failed_upsert_does_not_raise(fake_db):
    """A read that never needed the row should not 500 because provisioning had
    a bad moment. Writes still fail on the foreign key, which is where that
    error belongs."""
    ensure_doctor(_UpsertFails(), _user())  # must not raise


def test_a_failed_upsert_is_retried_rather_than_cached(fake_db):
    """If the failure were memoised, the tenant would stay unprovisioned for the
    whole cache window and every write in it would fail."""
    ensure_doctor(_UpsertFails(), _user())

    ensure_doctor(fake_db, _user())

    assert [d["id"] for d in _doctors(fake_db)] == [ALICE]


def test_a_successful_upsert_is_not_repeated(fake_db):
    ensure_doctor(fake_db, _user())
    fake_db.store["doctors"].clear()

    ensure_doctor(fake_db, _user())

    assert _doctors(fake_db) == [], "the second call should have been memoised away"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_claims_are_ignored(fake_db, blank):
    ensure_doctor(fake_db, _user(name=blank, email=blank))

    row = _doctors(fake_db)[0]
    assert row["name"] == "Unknown"
    assert "email" not in row
