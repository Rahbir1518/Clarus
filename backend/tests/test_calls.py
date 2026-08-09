"""Starting a call, and binding its conversation id.

These two routes close the gap that made the webhook path unreachable: nothing
created the call_logs row a post-call webhook resolves against. The properties
worth holding are all about who may create and claim one.

ElevenLabs is stubbed. Nothing here places a call or spends credits — what is
under test is the tenancy and the write-once binding, not the provider.
"""
import pytest

from app.api.routes import calls as calls_route
from app.db.tenancy import TenantScope
from tests.conftest import FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture(autouse=True)
def _stub_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """No API key, no network, no spend."""

    class _StubClient:
        def __init__(self, *_a, **_k) -> None:
            pass

        def conversation_token(self, agent_id=None) -> str:
            return "tok_stub"

    monkeypatch.setattr(calls_route, "ElevenLabsClient", _StubClient)


def _patient(db: FakeSupabase, doctor_id: str, name: str = "রহিম") -> dict:
    return TenantScope(db, doctor_id).insert_owned(
        "patients", {"name": name, "phone": "+8801700000000"}
    )


def _start(client, auth_header, db, doctor_id: str, **body):
    patient = _patient(db, doctor_id)
    payload = {"patient_id": patient["id"], **body}
    return client.post(
        "/api/calls/web", json=payload, headers=auth_header(doctor_id)
    )


# -- starting ---------------------------------------------------------------


def test_starting_a_call_creates_the_row_the_webhook_will_complete(
    client, fake_db, auth_header
):
    response = _start(client, auth_header, fake_db, ALICE)

    assert response.status_code == 201
    body = response.json()
    assert body["token"] == "tok_stub"

    row = next(r for r in fake_db.store["call_logs"] if r["id"] == body["call_log_id"])
    assert row["doctor_id"] == ALICE
    assert row["status"] == "in_progress"
    # Unbound until the browser reports back, which is the whole reason the
    # second route exists.
    assert row.get("conversation_id") is None


def test_dynamic_variables_come_from_the_patient_row_not_the_request(
    client, fake_db, auth_header
):
    """The agent speaks these aloud. A client that could set patient_name could
    make the call address someone by a name of its choosing."""
    patient = _patient(fake_db, ALICE, name="করিম উদ্দিন")

    response = client.post(
        "/api/calls/web",
        json={
            "patient_id": patient["id"],
            "appointment_reason": "your check-up",
            "callback_number": "+8801711111111",
        },
        headers=auth_header(ALICE),
    )

    variables = response.json()["dynamic_variables"]
    assert variables["patient_name"] == "করিম উদ্দিন"
    assert variables["appointment_reason"] == "your check-up"
    assert variables["timezone"] == "Asia/Dhaka"
    # Every placeholder the agent spec references, or the patient hears the
    # literal "{{...}}" spoken to them.
    assert set(variables) == {
        "patient_name",
        "doctor_name",
        "practice_name",
        "appointment_reason",
        "callback_number",
        "timezone",
        "today_date",
    }


def test_a_name_the_client_supplies_is_refused_outright(client, fake_db, auth_header):
    patient = _patient(fake_db, ALICE)

    response = client.post(
        "/api/calls/web",
        json={"patient_id": patient["id"], "patient_name": "Someone Else"},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 422


def test_calling_another_practices_patient_is_a_404(client, fake_db, auth_header):
    patient = _patient(fake_db, BOB)

    response = client.post(
        "/api/calls/web",
        json={"patient_id": patient["id"]},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 404
    # And nothing was created for the attempt.
    assert fake_db.store.get("call_logs", []) == []


def test_starting_a_call_requires_authentication(client, fake_db):
    patient = _patient(fake_db, ALICE)

    response = client.post("/api/calls/web", json={"patient_id": patient["id"]})

    assert response.status_code == 401
    assert fake_db.store.get("call_logs", []) == []


# -- binding ----------------------------------------------------------------


def test_binding_lets_the_webhook_resolve_the_row(client, fake_db, auth_header):
    call_log_id = _start(client, auth_header, fake_db, ALICE).json()["call_log_id"]

    response = client.post(
        f"/api/calls/web/{call_log_id}/bind",
        json={"conversation_id": "conv_abc123"},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 204
    row = next(r for r in fake_db.store["call_logs"] if r["id"] == call_log_id)
    assert row["conversation_id"] == "conv_abc123"


def test_rebinding_the_same_id_is_idempotent(client, fake_db, auth_header):
    """The browser may retry the report. That must not 409."""
    call_log_id = _start(client, auth_header, fake_db, ALICE).json()["call_log_id"]
    args = dict(
        json={"conversation_id": "conv_abc123"}, headers=auth_header(ALICE)
    )

    client.post(f"/api/calls/web/{call_log_id}/bind", **args)
    second = client.post(f"/api/calls/web/{call_log_id}/bind", **args)

    assert second.status_code == 204


def test_a_bound_call_cannot_be_repointed_at_another_conversation(
    client, fake_db, auth_header
):
    """conversation_id is the capability the unauthenticated webhook resolves
    against. Re-pointing a call log at someone else's conversation would
    harvest that call's outcome into this tenant's records."""
    call_log_id = _start(client, auth_header, fake_db, ALICE).json()["call_log_id"]
    client.post(
        f"/api/calls/web/{call_log_id}/bind",
        json={"conversation_id": "conv_mine"},
        headers=auth_header(ALICE),
    )

    response = client.post(
        f"/api/calls/web/{call_log_id}/bind",
        json={"conversation_id": "conv_someone_elses"},
        headers=auth_header(ALICE),
    )

    assert response.status_code == 409
    row = next(r for r in fake_db.store["call_logs"] if r["id"] == call_log_id)
    assert row["conversation_id"] == "conv_mine"


def test_binding_another_practices_call_log_is_a_404(client, fake_db, auth_header):
    call_log_id = _start(client, auth_header, fake_db, ALICE).json()["call_log_id"]

    response = client.post(
        f"/api/calls/web/{call_log_id}/bind",
        json={"conversation_id": "conv_stolen"},
        headers=auth_header(BOB),
    )

    assert response.status_code == 404
    row = next(r for r in fake_db.store["call_logs"] if r["id"] == call_log_id)
    assert row.get("conversation_id") is None


def test_conversation_id_is_not_writable_through_the_generic_update_path(fake_db):
    """The narrow bind method exists precisely so this stays impossible."""
    scope = TenantScope(fake_db, ALICE)
    patient = _patient(fake_db, ALICE)
    row = scope.insert_owned("call_logs", {"patient_id": patient["id"]})

    scope.update_owned(
        "call_logs", row["id"], {"conversation_id": "conv_injected", "status": "done"}
    )

    stored = next(r for r in fake_db.store["call_logs"] if r["id"] == row["id"])
    assert stored.get("conversation_id") is None
    assert stored["status"] == "done"
