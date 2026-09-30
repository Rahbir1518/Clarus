"""The names the agent says: the practice's and the doctor's, as they set them."""
import pytest

from app.api.routes import calls as calls_route
from app.core.config import get_settings
from app.db.tenancy import TenantScope

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture(autouse=True)
def _stub_token(monkeypatch):
    class _Stub:
        def __init__(self, *_a, **_k):
            pass

        def conversation_token(self, agent_id=None):
            return "tok_stub"

    monkeypatch.setattr(calls_route, "ElevenLabsClient", _Stub)


def _profile(client, auth_header, doctor_id=ALICE, **body):
    body = {"doctor_name": "Dr. Rahbir Mahdi", "practice_name": "Green Life Clinic", **body}
    return client.put("/api/practice/profile", json=body, headers=auth_header(doctor_id))


def _spoken(client, auth_header, fake_db, doctor_id=ALICE, **patient):
    row = TenantScope(fake_db, doctor_id).insert_owned(
        "patients", {"name": "রহিম", "phone": "+8801700000000", **patient}
    )
    started = client.post(
        "/api/calls/web", json={"patient_id": row["id"]}, headers=auth_header(doctor_id)
    )
    assert started.status_code == 201
    return started.json()["dynamic_variables"]


def test_the_agent_says_the_names_the_practice_set(client, fake_db, auth_header):
    assert _profile(client, auth_header).status_code == 200

    spoken = _spoken(client, auth_header, fake_db)

    assert spoken["practice_name"] == "Green Life Clinic"
    assert spoken["doctor_name"] == "Dr. Rahbir Mahdi"


def test_before_a_profile_the_configured_fallbacks_are_used(client, fake_db, auth_header):
    """And never the Clerk id the doctors row is provisioned with."""
    spoken = _spoken(client, auth_header, fake_db, primary_physician="Dr. Anwar")

    assert spoken["practice_name"] == get_settings().practice_name
    assert spoken["doctor_name"] == "Dr. Anwar"
    assert ALICE not in spoken.values()


def test_the_profile_is_read_back_and_is_per_practice(client, fake_db, auth_header):
    _profile(client, auth_header)

    alice = client.get("/api/practice/settings", headers=auth_header(ALICE)).json()
    bob = client.get("/api/practice/settings", headers=auth_header(BOB)).json()

    assert (alice["doctor_name"], alice["practice_name"]) == ("Dr. Rahbir Mahdi", "Green Life Clinic")
    assert (bob["doctor_name"], bob["practice_name"]) == (None, None)


def test_whitespace_is_collapsed(client, auth_header):
    saved = _profile(client, auth_header, practice_name="  Green\n Life   Clinic ").json()
    assert saved["practice_name"] == "Green Life Clinic"


@pytest.mark.parametrize(
    "field,value",
    [
        ("practice_name", "{{patient_name}} Clinic"),
        ("doctor_name", "Dr. <b>X</b>"),
        ("doctor_name", "   "),
        ("practice_name", "x" * 101),
    ],
)
def test_names_that_could_write_into_the_prompt_are_refused(client, auth_header, field, value):
    assert _profile(client, auth_header, **{field: value}).status_code == 422
