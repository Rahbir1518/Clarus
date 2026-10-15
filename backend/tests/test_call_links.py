"""Call links: a waiting call answered by the patient from an emailed link.

The properties worth holding are about the link as a credential — it names one
call, cannot be edited into another, expires, and is spent once a conversation
binds — and about CALL_TRANSPORT=email contacting nobody the gates would not
let a phone call reach.

ElevenLabs and SMTP are stubbed. Nothing here sends mail or spends credits.
"""
import datetime as dt
import json
import time

import pytest

from app.api.routes import calls as calls_route
from app.core.config import MissingConfiguration, get_settings
from app.db.tenancy import TenantScope
from app.engine import nodes as engine_nodes
from app.integrations import call_links
from app.integrations.call_links import (
    ExpiredCallLink,
    InvalidCallLink,
    build_invitation,
    issue_call_link,
    read_call_link,
)
from app.integrations.elevenlabs.webhook import AWAITING_BROWSER, AWAITING_PATIENT, sign_payload
from tests.conftest import TEST_WEBHOOK_SECRET, FakeSupabase

ALICE = "user_2alice"
BOB = "user_2bob"
PATIENT_EMAIL = "rahim@example.com"
APP_URL = "https://clarus.test"


# ---------------------------------------------------------------------------
# Fixtures and builders
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.emails: list = []
        self.agent_ids: list = []


@pytest.fixture
def email_calls(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """CALL_TRANSPORT=email with every gate open, through real Settings parsing."""
    for name, value in {
        "CALL_TRANSPORT": "email",
        "CALLS_ENABLED": "true",
        "CALL_ALLOWED_EMAILS": PATIENT_EMAIL,
        "CALLING_HOURS_START": "0",
        "CALLING_HOURS_END": "24",
        "PRACTICE_CALLBACK_NUMBER": "+8802000000000",
        "CALL_LINK_SECRET": "link-secret-for-tests",
        "PUBLIC_APP_URL": APP_URL,
        "SMTP_USERNAME": "info.cl4rus@gmail.com",
        "SMTP_PASSWORD": "app-password",
        "ELEVENLABS_AGENT_ID": "agent_bn",
        "ELEVENLABS_AGENT_ID_EN": "agent_en",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    recorder = _Recorder()

    class _StubElevenLabs:
        def __init__(self, *_a, **_k) -> None:
            pass

        def conversation_token(self, agent_id=None) -> str:
            recorder.agent_ids.append(agent_id)
            return "tok_stub"

        def place_call(self, **_kw):  # pragma: no cover - must never happen
            raise AssertionError("an email call must not dial anything")

    monkeypatch.setattr(calls_route, "ElevenLabsClient", _StubElevenLabs)
    monkeypatch.setattr(engine_nodes, "ElevenLabsClient", _StubElevenLabs)
    monkeypatch.setattr(call_links, "send_email", lambda msg, _settings: recorder.emails.append(msg))
    calls_route.link_limiter.reset()
    yield recorder
    get_settings.cache_clear()


def _patient(db: FakeSupabase, doctor_id: str = ALICE, **fields) -> dict:
    values = {"name": "রহিম", "phone": "+8801700000000", "email": PATIENT_EMAIL}
    values.update(fields)
    return TenantScope(db, doctor_id).insert_owned("patients", values)


def _node(node_id: str, node_type: str, **params: str) -> dict:
    return {
        "id": node_id,
        "type": "action",
        "position": {"x": 0, "y": 0},
        "data": {"label": node_id, "nodeType": node_type, "params": params},
    }


def _workflow(db: FakeSupabase, doctor_id: str = ALICE) -> dict:
    nodes = [
        _node("t1", "lab_results_received"),
        _node("c1", "call_patient"),
        _node("a1", "schedule_appointment", duration_minutes="20"),
    ]
    edges = [
        {"id": "t1->c1", "source": "t1", "target": "c1"},
        {"id": "c1->a1", "source": "c1", "target": "a1"},
    ]
    return TenantScope(db, doctor_id).insert_owned(
        "workflows", {"name": "Follow up", "status": "ENABLED", "nodes": nodes, "edges": edges}
    )


def _run(client, auth_header, db: FakeSupabase, patient: dict, doctor_id: str = ALICE):
    workflow = _workflow(db, doctor_id)
    return client.post(
        f"/api/workflows/{workflow['id']}/execute",
        json={"patient_id": patient["id"]},
        headers=auth_header(doctor_id),
    )


def _call_step(response) -> dict:
    return next(s for s in response.json()["execution_log"] if s["node_type"] == "call_patient")


def _row(db: FakeSupabase, call_log_id: str) -> dict:
    return next(r for r in db.store["call_logs"] if r["id"] == call_log_id)


def _link_token(email) -> str:
    """The token in an invitation, read back the way a patient's click would."""
    text = email.get_body(preferencelist=("plain",)).get_content()
    url = next(word for word in text.split() if word.startswith(f"{APP_URL}/call/"))
    return url.rsplit("/", 1)[1]


def _webhook(client, conversation_id: str):
    """A signed post-call webhook in which the patient confirmed."""
    collected = {
        "patient_confirmed": True,
        "confirmed_date": "2026-08-14",
        "confirmed_time": "14:30",
        "call_outcome": "confirmed",
        "reached_patient": True,
        "callback_requested": False,
        "patient_availability_notes": None,
    }
    body = json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": int(time.time()),
            "data": {
                "conversation_id": conversation_id,
                "status": "done",
                "transcript": [{"role": "user", "message": "হ্যাঁ, ঠিক আছে।"}],
                "conversation_initiation_client_data": {"dynamic_variables": {}},
                "analysis": {
                    "data_collection_results": {k: {"value": v} for k, v in collected.items()}
                },
            },
        }
    ).encode()
    return client.post(
        "/api/elevenlabs/webhook",
        content=body,
        headers={
            "elevenlabs-signature": sign_payload(body, TEST_WEBHOOK_SECRET, int(time.time())),
            "content-type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# The link is the credential
# ---------------------------------------------------------------------------


def test_a_link_names_its_call_and_points_at_the_app(email_calls):
    link = issue_call_link("call-123", get_settings())

    assert link.url == f"{APP_URL}/call/{link.token}"
    assert read_call_link(link.token, get_settings()) == "call-123"


@pytest.mark.parametrize(
    "tamper",
    [
        lambda t: t.replace("call-123", "call-456", 1),  # another call
        lambda t: f"{t.split('.')[0]}.{int(t.split('.')[1]) + 3600}.{t.split('.')[2]}",  # longer life
        lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),  # forged signature
    ],
    ids=["call", "expiry", "signature"],
)
def test_an_edited_link_is_refused(email_calls, tamper):
    token = issue_call_link("call-123", get_settings()).token
    with pytest.raises(InvalidCallLink):
        read_call_link(tamper(token), get_settings())


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "call-123..sig", "call-123.12.", ".12.sig"])
def test_a_malformed_link_is_refused(email_calls, token):
    with pytest.raises(InvalidCallLink):
        read_call_link(token, get_settings())


def test_a_link_expires(email_calls):
    issued_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
    token = issue_call_link("call-123", get_settings(), now=issued_at).token
    with pytest.raises(ExpiredCallLink):
        read_call_link(token, get_settings())


def test_a_forged_link_is_invalid_whatever_date_it_claims(email_calls):
    """Only a genuine link may learn that it has expired."""
    issued_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
    token = issue_call_link("call-123", get_settings(), now=issued_at).token
    with pytest.raises(InvalidCallLink):
        read_call_link(token[:-2] + ("AA" if not token.endswith("AA") else "BB"), get_settings())


def test_rotating_the_secret_revokes_every_link(email_calls, monkeypatch):
    token = issue_call_link("call-123", get_settings()).token
    monkeypatch.setenv("CALL_LINK_SECRET", "a-new-secret")
    get_settings.cache_clear()
    with pytest.raises(InvalidCallLink):
        read_call_link(token, get_settings())


def test_no_link_is_issued_without_a_secret(email_calls, monkeypatch):
    monkeypatch.setenv("CALL_LINK_SECRET", "")
    get_settings.cache_clear()
    with pytest.raises(MissingConfiguration, match="CALL_LINK_SECRET"):
        issue_call_link("call-123", get_settings())


# ---------------------------------------------------------------------------
# The invitation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "phrase"), [("en", "Answer the call"), ("bn", "কলটি ধরুন")]
)
def test_the_invitation_is_in_the_patients_language(email_calls, language, phrase):
    link = issue_call_link("call-123", get_settings())
    msg = build_invitation(
        to=PATIENT_EMAIL, link=link, practice_name="Clarus Clinic", language=language,
        settings=get_settings(),
    )

    text = msg.get_body(preferencelist=("plain",)).get_content()
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert phrase in text and phrase in html
    assert link.url in text and link.url in html
    assert msg["To"] == PATIENT_EMAIL
    assert "Clarus Clinic" in msg["Subject"]


def test_the_invitation_escapes_the_practice_name(email_calls):
    msg = build_invitation(
        to=PATIENT_EMAIL, link=issue_call_link("call-123", get_settings()),
        practice_name="<script>x</script>", language="en", settings=get_settings(),
    )
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# CALL_TRANSPORT=email in a workflow run
# ---------------------------------------------------------------------------


def test_a_run_parks_and_emails_the_patient_a_link_to_its_call(
    client, fake_db, auth_header, email_calls
):
    started = _run(client, auth_header, fake_db, _patient(fake_db))
    call_log_id = started.json()["call_log_id"]

    assert started.json()["status"] == "parked"
    assert PATIENT_EMAIL in _call_step(started)["message"]
    row = _row(fake_db, call_log_id)
    assert row["outcome"] == AWAITING_PATIENT
    assert row["call_variables"]["patient_name"] == "রহিম"

    (email,) = email_calls.emails
    assert email["To"] == PATIENT_EMAIL
    assert read_call_link(_link_token(email), get_settings()) == call_log_id
    # +880, so the email is in Bangla, like the agent.
    assert "কলটি ধরুন" in email.get_body(preferencelist=("plain",)).get_content()


def test_no_phone_gate_applies_when_nothing_is_dialled(
    client, fake_db, auth_header, email_calls
):
    """A local-format number would be refused for dialling; here the email is
    what gets checked."""
    patient = _patient(fake_db, phone="01700000000")
    assert _run(client, auth_header, fake_db, patient).json()["status"] == "parked"
    assert len(email_calls.emails) == 1


@pytest.mark.parametrize("email", [None, "", "not-an-address"])
def test_a_patient_without_a_usable_address_is_not_contacted(
    client, fake_db, auth_header, email_calls, email
):
    patient = _patient(fake_db)
    fake_db.store["patients"][-1]["email"] = email  # as stored before validation existed

    started = _run(client, auth_header, fake_db, patient)

    assert _call_step(started)["status"] == "blocked"
    assert email_calls.emails == []


def test_an_address_off_the_allowlist_is_not_emailed(
    client, fake_db, auth_header, email_calls
):
    started = _run(client, auth_header, fake_db, _patient(fake_db, email="someone@else.com"))

    assert _call_step(started)["status"] == "blocked"
    assert "CALL_ALLOWED_EMAILS" in _call_step(started)["message"]
    assert email_calls.emails == []


def test_the_kill_switch_stops_an_email_call(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    monkeypatch.setenv("CALLS_ENABLED", "false")
    get_settings.cache_clear()

    assert _call_step(_run(client, auth_header, fake_db, _patient(fake_db)))["status"] == "blocked"
    assert email_calls.emails == []


def test_without_a_mail_account_nothing_is_parked(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    monkeypatch.setenv("SMTP_PASSWORD", "")
    get_settings.cache_clear()

    started = _run(client, auth_header, fake_db, _patient(fake_db))

    assert _call_step(started)["status"] == "blocked"
    assert "SMTP_PASSWORD" in _call_step(started)["message"]
    assert _row(fake_db, started.json()["call_log_id"]).get("outcome") != AWAITING_PATIENT


def test_a_failed_email_leaves_the_call_answerable_and_flagged(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    def _down(_msg, _settings):
        raise OSError("smtp unreachable")

    monkeypatch.setattr(call_links, "send_email", _down)

    started = _run(client, auth_header, fake_db, _patient(fake_db))
    row = _row(fake_db, started.json()["call_log_id"])

    assert started.json()["status"] == "parked"
    assert "Copy its link" in _call_step(started)["message"]
    assert row["outcome"] == AWAITING_PATIENT
    assert row["needs_review"] is True


def test_an_emailed_link_counts_as_an_attempt(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    """Otherwise every re-run emails the patient again."""
    monkeypatch.setenv("MAX_CALL_ATTEMPTS_PER_PATIENT", "1")
    get_settings.cache_clear()
    patient = _patient(fake_db)

    _run(client, auth_header, fake_db, patient)
    second = _run(client, auth_header, fake_db, patient)

    assert _call_step(second)["status"] == "blocked"
    assert len(email_calls.emails) == 1


# ---------------------------------------------------------------------------
# The patient answers through the link
# ---------------------------------------------------------------------------


def _emailed_call(client, auth_header, fake_db, email_calls, **patient_fields) -> tuple[str, str]:
    started = _run(client, auth_header, fake_db, _patient(fake_db, **patient_fields))
    return started.json()["call_log_id"], _link_token(email_calls.emails[-1])


def test_the_patient_answers_and_the_workflow_resumes(
    client, fake_db, auth_header, email_calls
):
    """The whole chain, with no session: open, answer, bind, webhook, booked."""
    call_log_id, token = _emailed_call(client, auth_header, fake_db, email_calls)

    info = client.get(f"/api/call-links/{token}")
    assert info.status_code == 200
    assert info.json() == {"status": "ready", "practice_name": "Clarus", "language": "bn"}

    answered = client.post(f"/api/call-links/{token}/answer")
    assert answered.status_code == 200
    assert answered.json()["token"] == "tok_stub"
    assert answered.json()["dynamic_variables"]["patient_name"] == "রহিম"

    bound = client.post(f"/api/call-links/{token}/bind", json={"conversation_id": "conv_link"})
    assert bound.status_code == 204
    assert _webhook(client, "conv_link").status_code == 200

    row = _row(fake_db, call_log_id)
    assert row["status"] == "completed"
    assert row["outcome"] == "confirmed"
    assert fake_db.store["appointments"][0]["call_log_id"] == call_log_id
    assert client.get(f"/api/call-links/{token}").json()["status"] == "answered"


def test_a_link_is_spent_once_its_call_is_answered(client, fake_db, auth_header, email_calls):
    _, token = _emailed_call(client, auth_header, fake_db, email_calls)
    client.post(f"/api/call-links/{token}/answer")
    client.post(f"/api/call-links/{token}/bind", json={"conversation_id": "conv_link"})

    assert client.post(f"/api/call-links/{token}/answer").status_code == 409
    repointed = client.post(f"/api/call-links/{token}/bind", json={"conversation_id": "conv_other"})
    assert repointed.status_code == 409


def test_the_agent_speaks_the_patients_language(client, fake_db, auth_header, email_calls):
    _, token = _emailed_call(client, auth_header, fake_db, email_calls, phone="+14165550134")

    assert client.get(f"/api/call-links/{token}").json()["language"] == "en"
    client.post(f"/api/call-links/{token}/answer")
    assert email_calls.agent_ids == ["agent_en"]


def test_a_forged_link_reaches_nothing(client, fake_db, auth_header, email_calls):
    call_log_id, token = _emailed_call(client, auth_header, fake_db, email_calls)
    forged = token[:-2] + ("AA" if not token.endswith("AA") else "BB")

    assert client.get(f"/api/call-links/{forged}").status_code == 404
    assert client.post(f"/api/call-links/{forged}/answer").status_code == 404
    assert _row(fake_db, call_log_id).get("conversation_id") is None


def test_an_expired_link_says_so(client, fake_db, auth_header, email_calls):
    call_log_id, _ = _emailed_call(client, auth_header, fake_db, email_calls)
    issued_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)
    token = issue_call_link(call_log_id, get_settings(), now=issued_at).token

    response = client.get(f"/api/call-links/{token}")
    assert response.status_code == 410
    assert "expired" in response.json()["error"]["message"]


def test_a_deleted_call_cannot_be_answered(client, fake_db, auth_header, email_calls):
    call_log_id, token = _emailed_call(client, auth_header, fake_db, email_calls)
    _row(fake_db, call_log_id)["deleted_at"] = "2026-10-15T00:00:00+00:00"

    assert client.post(f"/api/call-links/{token}/answer").status_code == 404


def test_link_requests_are_rate_limited(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    _, token = _emailed_call(client, auth_header, fake_db, email_calls)
    monkeypatch.setattr(calls_route, "LINK_REQUESTS_PER_IP", 2)

    assert client.get(f"/api/call-links/{token}").status_code == 200
    assert client.get(f"/api/call-links/{token}").status_code == 200
    limited = client.get(f"/api/call-links/{token}")
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


# ---------------------------------------------------------------------------
# Staff: copying and emailing a link
# ---------------------------------------------------------------------------


def _parked_for_staff(client, auth_header, fake_db, monkeypatch, **patient_fields) -> str:
    """A call parked on CALL_TRANSPORT=web, where no email is sent."""
    monkeypatch.setenv("CALL_TRANSPORT", "web")
    get_settings.cache_clear()
    started = _run(client, auth_header, fake_db, _patient(fake_db, **patient_fields))
    monkeypatch.setenv("CALL_TRANSPORT", "email")
    get_settings.cache_clear()
    return started.json()["call_log_id"]


def test_emailed_calls_are_listed_as_waiting(client, fake_db, auth_header, email_calls):
    call_log_id, _ = _emailed_call(client, auth_header, fake_db, email_calls)

    (pending,) = client.get("/api/calls/web/pending", headers=auth_header(ALICE)).json()
    assert pending["call_log_id"] == call_log_id
    assert pending["emailed"] is True


def test_staff_can_copy_a_link_to_a_waiting_call(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    call_log_id = _parked_for_staff(client, auth_header, fake_db, monkeypatch)

    response = client.post(f"/api/calls/web/{call_log_id}/link", headers=auth_header(ALICE))

    assert response.status_code == 200
    token = response.json()["url"].rsplit("/", 1)[1]
    assert read_call_link(token, get_settings()) == call_log_id
    assert email_calls.emails == []


def test_another_practice_cannot_get_a_link(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    call_log_id = _parked_for_staff(client, auth_header, fake_db, monkeypatch)
    response = client.post(f"/api/calls/web/{call_log_id}/link", headers=auth_header(BOB))
    assert response.status_code == 404


def test_staff_can_email_the_link_and_it_then_counts_as_contact(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    call_log_id = _parked_for_staff(client, auth_header, fake_db, monkeypatch)
    assert _row(fake_db, call_log_id)["outcome"] == AWAITING_BROWSER

    response = client.post(f"/api/calls/web/{call_log_id}/email", headers=auth_header(ALICE))

    assert response.status_code == 200
    (email,) = email_calls.emails
    assert read_call_link(_link_token(email), get_settings()) == call_log_id
    assert _row(fake_db, call_log_id)["outcome"] == AWAITING_PATIENT


def test_staff_cannot_email_a_patient_with_no_address(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    call_log_id = _parked_for_staff(client, auth_header, fake_db, monkeypatch, email=None)

    response = client.post(f"/api/calls/web/{call_log_id}/email", headers=auth_header(ALICE))

    assert response.status_code == 409
    assert email_calls.emails == []


def test_a_link_is_refused_for_a_call_that_is_not_waiting(
    client, fake_db, auth_header, email_calls
):
    call_log_id, token = _emailed_call(client, auth_header, fake_db, email_calls)
    client.post(f"/api/call-links/{token}/bind", json={"conversation_id": "conv_link"})

    response = client.post(f"/api/calls/web/{call_log_id}/link", headers=auth_header(ALICE))
    assert response.status_code == 409


def test_links_are_unavailable_until_configured(
    client, fake_db, auth_header, email_calls, monkeypatch
):
    call_log_id = _parked_for_staff(client, auth_header, fake_db, monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "")
    get_settings.cache_clear()

    response = client.post(f"/api/calls/web/{call_log_id}/link", headers=auth_header(ALICE))

    assert response.status_code == 503
    assert "PUBLIC_APP_URL" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Where the address comes from
# ---------------------------------------------------------------------------


def test_a_patient_email_must_be_a_real_address(client, auth_header):
    response = client.post(
        "/api/patients",
        json={"name": "Rahim", "phone": "+8801700000000", "email": "rahim at example"},
        headers=auth_header(ALICE),
    )
    assert response.status_code == 422
