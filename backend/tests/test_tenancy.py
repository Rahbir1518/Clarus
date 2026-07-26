"""Tenant isolation, end to end through the HTTP layer."""
import pytest

ALICE = "auth0|dr-alice"
BOB = "auth0|dr-bob"


def _create_patient(client, headers, name="Jane Doe", phone="+15551234567", **extra):
    response = client.post(
        "/api/patients", json={"name": name, "phone": phone, **extra}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_patient_is_owned_by_the_token_subject(client, auth_header):
    created = _create_patient(client, auth_header(ALICE))
    assert created["doctor_id"] == ALICE


def test_client_supplied_doctor_id_is_ignored(client, auth_header):
    """The old API took doctor_id from the request. The frontend still sends it."""
    created = _create_patient(
        client, auth_header(ALICE), doctor_id=BOB, name="Impersonation Attempt"
    )
    assert created["doctor_id"] == ALICE


def test_list_returns_only_the_callers_patients(client, auth_header):
    _create_patient(client, auth_header(ALICE), name="Alice Patient")
    _create_patient(client, auth_header(BOB), name="Bob Patient")

    alice_names = [
        p["name"] for p in client.get("/api/patients", headers=auth_header(ALICE)).json()
    ]
    bob_names = [
        p["name"] for p in client.get("/api/patients", headers=auth_header(BOB)).json()
    ]

    assert alice_names == ["Alice Patient"]
    assert bob_names == ["Bob Patient"]


def test_doctor_id_query_param_cannot_widen_scope(client, auth_header):
    """The frontend still sends ?doctor_id=. It must not be honoured."""
    _create_patient(client, auth_header(BOB), name="Bob Patient")

    response = client.get(
        "/api/patients", params={"doctor_id": BOB}, headers=auth_header(ALICE)
    )
    assert response.status_code == 200
    assert response.json() == []


def test_reading_another_tenants_patient_is_404(client, auth_header):
    theirs = _create_patient(client, auth_header(BOB))

    response = client.get(f"/api/patients/{theirs['id']}", headers=auth_header(ALICE))
    # 404 rather than 403: a 403 would confirm the record exists.
    assert response.status_code == 404


def test_updating_another_tenants_patient_is_404(client, auth_header):
    theirs = _create_patient(client, auth_header(BOB))

    response = client.put(
        f"/api/patients/{theirs['id']}",
        json={"name": "Overwritten"},
        headers=auth_header(ALICE),
    )
    assert response.status_code == 404

    # And the record is untouched.
    still_there = client.get(
        f"/api/patients/{theirs['id']}", headers=auth_header(BOB)
    ).json()
    assert still_there["name"] == "Jane Doe"


def test_deleting_another_tenants_patient_is_404(client, auth_header):
    theirs = _create_patient(client, auth_header(BOB))

    response = client.delete(f"/api/patients/{theirs['id']}", headers=auth_header(ALICE))
    assert response.status_code == 404

    assert (
        client.get(f"/api/patients/{theirs['id']}", headers=auth_header(BOB)).status_code
        == 200
    )


def test_owner_can_read_update_and_delete(client, auth_header):
    headers = auth_header(ALICE)
    created = _create_patient(client, headers)

    assert client.get(f"/api/patients/{created['id']}", headers=headers).status_code == 200

    updated = client.put(
        f"/api/patients/{created['id']}", json={"name": "Jane Roe"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Jane Roe"
    # Untouched fields survive a partial update.
    assert updated.json()["phone"] == "+15551234567"

    assert client.delete(f"/api/patients/{created['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/patients/{created['id']}", headers=headers).status_code == 404


def test_doctor_id_cannot_be_reassigned_by_update(client, auth_header):
    created = _create_patient(client, auth_header(ALICE))

    response = client.put(
        f"/api/patients/{created['id']}",
        json={"doctor_id": BOB, "name": "Still Alice's"},
        headers=auth_header(ALICE),
    )
    assert response.status_code == 200
    assert response.json()["doctor_id"] == ALICE

    # Bob still cannot reach it.
    assert (
        client.get(f"/api/patients/{created['id']}", headers=auth_header(BOB)).status_code
        == 404
    )


def test_missing_patient_is_404_not_500(client, auth_header):
    response = client.get(
        "/api/patients/00000000-0000-0000-0000-000000000000", headers=auth_header(ALICE)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {"phone": "+15551234567"},          # no name
        {"name": "No Phone"},                # no phone
        {"name": "", "phone": "+1555"},     # empty name
        {"name": "X", "phone": "+1555", "risk_level": "catastrophic"},
    ],
)
def test_invalid_payloads_are_422(client, auth_header, payload):
    response = client.post("/api/patients", json=payload, headers=auth_header(ALICE))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
