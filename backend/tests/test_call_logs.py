"""Call log reads through the HTTP API.

The property under test is the one the schema split exists for: a transcript is
the conversation with a patient, so it leaves the building only when someone
opens that specific call, and only with an audit row to say so.
"""
from app.db.tenancy import TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


def _call_log(db: FakeSupabase, doctor_id: str, **overrides) -> dict:
    scope = TenantScope(db, doctor_id)
    patient = scope.insert_owned("patients", {"name": "Jane", "phone": "+1555"})
    row = scope.insert_owned(
        "call_logs",
        {"patient_id": patient["id"], "status": "completed", **overrides},
    )
    # Provider-written columns: the webhook path, not a client payload.
    stored = next(r for r in db.store["call_logs"] if r["id"] == row["id"])
    stored["transcript"] = "Agent: are you free Tuesday? Patient: yes."
    stored["conversation_id"] = f"conv_{doctor_id}"
    return stored


# -- listing ----------------------------------------------------------------


def test_the_list_is_scoped_to_the_caller(client, fake_db, auth_header):
    _call_log(fake_db, ALICE)
    _call_log(fake_db, BOB)

    body = client.get("/api/call-logs", headers=auth_header(ALICE)).json()

    assert len(body) == 1
    assert body[0]["doctor_id"] == ALICE


def test_a_supplied_doctor_id_has_no_effect(client, fake_db, auth_header):
    """The frontend still sends ?doctor_id=. Scoping comes from the token."""
    _call_log(fake_db, BOB)

    body = client.get(
        f"/api/call-logs?doctor_id={BOB}", headers=auth_header(ALICE)
    ).json()

    assert body == []


def test_the_list_withholds_transcripts(client, fake_db, auth_header):
    """Rendering a table of statuses does not require shipping every
    conversation the practice has recorded."""
    _call_log(fake_db, ALICE)

    body = client.get("/api/call-logs", headers=auth_header(ALICE)).json()

    assert body[0]["status"] == "completed"
    assert "transcript" not in body[0]
    assert "conversation_id" not in body[0]


def test_the_list_can_be_filtered_by_status(client, fake_db, auth_header):
    _call_log(fake_db, ALICE, status="completed")
    _call_log(fake_db, ALICE, status="pending")

    body = client.get(
        "/api/call-logs?status=pending", headers=auth_header(ALICE)
    ).json()

    assert [row["status"] for row in body] == ["pending"]


# -- detail -----------------------------------------------------------------


def test_opening_a_call_returns_the_transcript(client, fake_db, auth_header):
    row = _call_log(fake_db, ALICE)

    body = client.get(
        f"/api/call-logs/{row['id']}", headers=auth_header(ALICE)
    ).json()

    assert body["transcript"].startswith("Agent:")


def test_opening_a_call_is_audited(client, fake_db, auth_header):
    row = _call_log(fake_db, ALICE)

    client.get(f"/api/call-logs/{row['id']}", headers=auth_header(ALICE))

    events = fake_db.store["audit_log"]
    assert len(events) == 1
    assert events[0]["doctor_id"] == ALICE
    assert events[0]["action"] == "read"
    assert events[0]["entity_type"] == "call_log"
    assert events[0]["entity_id"] == row["id"]


def test_the_audit_row_does_not_copy_the_transcript(client, fake_db, auth_header):
    """The trail records that an access happened. Duplicating the PHI into it
    just puts the conversation somewhere else as well."""
    row = _call_log(fake_db, ALICE)

    client.get(f"/api/call-logs/{row['id']}", headers=auth_header(ALICE))

    metadata = fake_db.store["audit_log"][0]["metadata"]
    assert metadata == {"has_transcript": True}


def test_another_tenants_call_is_a_404(client, fake_db, auth_header):
    row = _call_log(fake_db, BOB)

    response = client.get(f"/api/call-logs/{row['id']}", headers=auth_header(ALICE))

    assert response.status_code == 404


def test_a_refused_read_is_not_audited(client, fake_db, auth_header):
    """Recording it would file calls the caller never saw, and does not own,
    into their own trail."""
    row = _call_log(fake_db, BOB)

    client.get(f"/api/call-logs/{row['id']}", headers=auth_header(ALICE))

    assert fake_db.store.get("audit_log", []) == []


def test_call_logs_require_a_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/call-logs").status_code == 401
