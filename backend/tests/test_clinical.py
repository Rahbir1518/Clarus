"""Conditions and medications.

These tables carry no doctor_id, so every route below is only as safe as the
parent lookup in front of it. That is what most of these tests are about.
"""
ALICE = "user_2alice"
BOB = "user_2bob"


def _patient(client, headers, name: str = "Jane") -> dict:
    return client.post(
        "/api/patients", json={"name": name, "phone": "+15551234567"}, headers=headers
    ).json()


# -- conditions -------------------------------------------------------------


def test_a_condition_is_filed_against_its_patient(client, auth_header):
    headers = auth_header(ALICE)
    patient = _patient(client, headers)

    created = client.post(
        f"/api/patients/{patient['id']}/conditions",
        json={"icd10_code": "E11.9", "description": "Type 2 diabetes"},
        headers=headers,
    ).json()

    assert created["patient_id"] == patient["id"]
    assert created["status"] == "documented"


def test_conditions_round_trip(client, auth_header):
    headers = auth_header(ALICE)
    patient = _patient(client, headers)
    url = f"/api/patients/{patient['id']}/conditions"

    created = client.post(
        url,
        json={"icd10_code": "I10", "description": "Hypertension", "raf_impact": 0.104},
        headers=headers,
    ).json()

    assert [c["id"] for c in client.get(url, headers=headers).json()] == [created["id"]]

    updated = client.put(
        f"{url}/{created['id']}", json={"status": "review_needed"}, headers=headers
    ).json()
    assert updated["status"] == "review_needed"
    assert updated["icd10_code"] == "I10"

    assert client.delete(f"{url}/{created['id']}", headers=headers).status_code == 204
    assert client.get(url, headers=headers).json() == []


def test_a_condition_cannot_be_filed_on_another_practices_patient(client, auth_header):
    """The whole point of the nesting: this table has no doctor_id, so the
    parent lookup is the only thing standing here."""
    theirs = _patient(client, auth_header(BOB))
    headers = auth_header(ALICE)
    url = f"/api/patients/{theirs['id']}/conditions"

    assert client.get(url, headers=headers).status_code == 404
    assert client.post(
        url, json={"icd10_code": "I10", "description": "HTN"}, headers=headers
    ).status_code == 404


def test_an_out_of_range_raf_impact_is_a_422(client, auth_header):
    """NUMERIC(6,3) overflows as a database error. Bounding it here names the
    field instead of returning a 500."""
    headers = auth_header(ALICE)
    patient = _patient(client, headers)

    response = client.post(
        f"/api/patients/{patient['id']}/conditions",
        json={"icd10_code": "I10", "description": "HTN", "raf_impact": 12345.6},
        headers=headers,
    )

    assert response.status_code == 422


def test_an_unknown_condition_status_is_refused(client, auth_header):
    headers = auth_header(ALICE)
    patient = _patient(client, headers)

    response = client.post(
        f"/api/patients/{patient['id']}/conditions",
        json={"icd10_code": "I10", "description": "HTN", "status": "resolved"},
        headers=headers,
    )

    assert response.status_code == 422


# -- medications ------------------------------------------------------------


def test_medications_round_trip(client, auth_header):
    headers = auth_header(ALICE)
    patient = _patient(client, headers)
    url = f"/api/patients/{patient['id']}/medications"

    created = client.post(
        url,
        json={"name": "Metformin", "dosage": "500mg", "frequency": "BID"},
        headers=headers,
    ).json()

    assert created["name"] == "Metformin"
    assert created["status"] == "active"

    updated = client.put(
        f"{url}/{created['id']}", json={"status": "discontinued"}, headers=headers
    ).json()
    assert updated["status"] == "discontinued"
    assert updated["dosage"] == "500mg"

    assert client.delete(f"{url}/{created['id']}", headers=headers).status_code == 204


def test_a_medication_cannot_be_attributed_to_another_doctor(client, auth_header):
    """prescriber_doctor_id is not on the request model, so `extra="ignore"`
    drops it before TenantScope ever sees it. Belt and braces: the scope would
    refuse it too."""
    headers = auth_header(ALICE)
    patient = _patient(client, headers)

    created = client.post(
        f"/api/patients/{patient['id']}/medications",
        json={"name": "Warfarin", "prescriber_doctor_id": BOB},
        headers=headers,
    ).json()

    assert "prescriber_doctor_id" not in created


def test_blank_dates_are_accepted_as_absent(client, auth_header):
    """An untouched date input submits "". Without normalisation that is a 422
    on a field the user never filled in."""
    headers = auth_header(ALICE)
    patient = _patient(client, headers)

    response = client.post(
        f"/api/patients/{patient['id']}/medications",
        json={"name": "Aspirin", "start_date": "", "end_date": ""},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["start_date"] is None


def test_clinical_routes_require_a_token(unauthenticated_client):
    assert (
        unauthenticated_client.get("/api/patients/anything/conditions").status_code
        == 401
    )
    assert (
        unauthenticated_client.get("/api/patients/anything/medications").status_code
        == 401
    )
