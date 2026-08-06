"""Post-call webhook: signature verification and outcome mapping.

The old backend accepted these posts unverified, so anyone who found the URL
could inject a confirmed appointment. Most of what follows is about proving
forged and replayed requests are refused.
"""
import json
import time

import pytest

from app.integrations.elevenlabs.webhook import (
    CallResult,
    WebhookVerificationError,
    parse_post_call_payload,
    sign_payload,
    verify_signature,
)
from tests.conftest import TEST_WEBHOOK_SECRET

SECRET = TEST_WEBHOOK_SECRET


def _body(**overrides) -> bytes:
    payload = {
        "type": "post_call_transcription",
        "event_timestamp": int(time.time()),
        "data": {
            "conversation_id": "conv_test_1",
            "status": "done",
            "transcript": [
                {"role": "agent", "message": "Am I speaking with Alex Kim?"},
                {"role": "user", "message": "Yes, speaking."},
            ],
            "analysis": {
                "data_collection_results": {
                    "patient_confirmed": {"value": True},
                    "confirmed_date": {"value": "2026-08-14"},
                    "confirmed_time": {"value": "14:30"},
                    "call_outcome": {"value": "confirmed"},
                    "reached_patient": {"value": True},
                    "callback_requested": {"value": False},
                    "patient_availability_notes": {"value": None},
                }
            },
        },
    }
    payload["data"].update(overrides)
    return json.dumps(payload).encode()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_valid_signature_passes():
    body = _body()
    now = int(time.time())
    verify_signature(
        raw_body=body,
        signature_header=sign_payload(body, SECRET, now),
        secret=SECRET,
    )


def test_wrong_secret_is_rejected():
    body = _body()
    header = sign_payload(body, "attacker-secret", int(time.time()))
    with pytest.raises(WebhookVerificationError, match="mismatch"):
        verify_signature(raw_body=body, signature_header=header, secret=SECRET)


def test_tampered_body_is_rejected():
    """The exact attack the old system was open to."""
    original = _body()
    header = sign_payload(original, SECRET, int(time.time()))
    forged = original.replace(b'"conv_test_1"', b'"conv_victim"')
    with pytest.raises(WebhookVerificationError, match="mismatch"):
        verify_signature(raw_body=forged, signature_header=header, secret=SECRET)


def test_old_signature_is_rejected_as_replay():
    body = _body()
    stale = int(time.time()) - 3600
    with pytest.raises(WebhookVerificationError, match="too old"):
        verify_signature(
            raw_body=body,
            signature_header=sign_payload(body, SECRET, stale),
            secret=SECRET,
            tolerance_seconds=300,
        )


def test_future_signature_is_rejected():
    """A far-future timestamp would otherwise stay replayable indefinitely."""
    body = _body()
    ahead = int(time.time()) + 86_400
    with pytest.raises(WebhookVerificationError, match="future"):
        verify_signature(
            raw_body=body,
            signature_header=sign_payload(body, SECRET, ahead),
            secret=SECRET,
            tolerance_seconds=300,
        )


def test_missing_secret_fails_closed():
    """An unset secret must never be read as "skip verification"."""
    body = _body()
    with pytest.raises(WebhookVerificationError, match="not configured"):
        verify_signature(
            raw_body=body,
            signature_header=sign_payload(body, SECRET, int(time.time())),
            secret="",
        )


@pytest.mark.parametrize(
    "header",
    ["", "garbage", "t=abc,v0=deadbeef", "v0=deadbeef", "t=123", "t=123,v1=deadbeef"],
)
def test_malformed_headers_are_rejected(header):
    with pytest.raises(WebhookVerificationError):
        verify_signature(raw_body=_body(), signature_header=header, secret=SECRET)


def test_missing_header_is_rejected():
    with pytest.raises(WebhookVerificationError, match="Missing signature"):
        verify_signature(raw_body=_body(), signature_header=None, secret=SECRET)


# ---------------------------------------------------------------------------
# Payload mapping
# ---------------------------------------------------------------------------


def test_confirmed_call_is_bookable():
    result = parse_post_call_payload(json.loads(_body()))
    assert result.conversation_id == "conv_test_1"
    assert result.patient_confirmed is True
    assert result.confirmed_date == "2026-08-14"
    assert result.confirmed_time == "14:30"
    assert result.is_bookable
    assert not result.needs_human_review


def test_transcript_is_flattened_for_storage():
    result = parse_post_call_payload(json.loads(_body()))
    assert result.transcript == (
        "agent: Am I speaking with Alex Kim?\nuser: Yes, speaking."
    )


def test_confirmed_without_a_time_is_not_bookable():
    """The failure the old PM-guess heuristic papered over.

    A patient who agreed but never made the hour unambiguous must go to a human,
    not get booked at a guessed time.
    """
    body = json.loads(
        _body(
            analysis={
                "data_collection_results": {
                    "patient_confirmed": {"value": True},
                    "confirmed_date": {"value": "2026-08-14"},
                    "confirmed_time": {"value": None},
                    "call_outcome": {"value": "confirmed"},
                }
            }
        )
    )
    result = parse_post_call_payload(body)
    assert result.patient_confirmed is True
    assert result.needs_human_review
    assert not result.is_bookable


def test_voicemail_is_not_a_refusal():
    """Null confirmation means "never established", not "said no"."""
    body = json.loads(
        _body(
            analysis={
                "data_collection_results": {
                    "call_outcome": {"value": "voicemail"},
                    "reached_patient": {"value": False},
                }
            }
        )
    )
    result = parse_post_call_payload(body)
    assert result.patient_confirmed is None
    assert result.reached_patient is False
    assert not result.is_bookable


def test_literal_null_strings_become_none():
    """LLMs return the text "null" often enough that it must not reach a record."""
    body = json.loads(
        _body(
            analysis={
                "data_collection_results": {
                    "confirmed_date": {"value": "null"},
                    "patient_availability_notes": {"value": "N/A"},
                }
            }
        )
    )
    result = parse_post_call_payload(body)
    assert result.confirmed_date is None
    assert result.patient_availability_notes is None


def test_unrecognised_outcome_goes_to_review():
    body = json.loads(
        _body(analysis={"data_collection_results": {"call_outcome": {"value": "??"}}})
    )
    assert parse_post_call_payload(body).needs_human_review


@pytest.mark.parametrize(
    "outcome", ["reschedule_requested", "emergency", "opted_out"]
)
def test_outcomes_requiring_a_human(outcome):
    body = json.loads(
        _body(
            analysis={"data_collection_results": {"call_outcome": {"value": outcome}}}
        )
    )
    assert parse_post_call_payload(body).needs_human_review


def test_empty_analysis_does_not_crash():
    result = parse_post_call_payload({"data": {"conversation_id": "conv_x"}})
    assert result == CallResult(conversation_id="conv_x")
    assert result.needs_human_review


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def _post(client, body: bytes, *, header: str | None = None):
    if header is None:
        header = sign_payload(body, SECRET, int(time.time()))
    return client.post(
        "/api/elevenlabs/webhook",
        content=body,
        headers={"elevenlabs-signature": header, "Content-Type": "application/json"},
    )


def test_route_rejects_unsigned_request(unauthenticated_client, fake_db):
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2d1", "conversation_id": "conv_test_1"}
    ]
    response = unauthenticated_client.post(
        "/api/elevenlabs/webhook", content=_body()
    )
    assert response.status_code == 401
    # Crucially, nothing was written.
    assert "patient_confirmed" not in fake_db.store["call_logs"][0]


def test_route_rejects_forged_signature(unauthenticated_client, fake_db):
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2d1", "conversation_id": "conv_test_1"}
    ]
    body = _body()
    response = _post(
        unauthenticated_client,
        body,
        header=sign_payload(body, "attacker-secret", int(time.time())),
    )
    assert response.status_code == 401
    assert "patient_confirmed" not in fake_db.store["call_logs"][0]


def test_route_records_outcome_on_valid_signature(unauthenticated_client, fake_db):
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2d1", "conversation_id": "conv_test_1"}
    ]
    assert _post(unauthenticated_client, _body()).status_code == 204

    row = fake_db.store["call_logs"][0]
    assert row["patient_confirmed"] is True
    assert row["confirmed_date"] == "2026-08-14"
    assert row["confirmed_time"] == "14:30"
    assert row["outcome"] == "confirmed"
    assert row["needs_review"] is False
    assert row["status"] == "completed"
    assert row["webhook_received_at"]


def test_route_cannot_reassign_a_call_to_another_tenant(unauthenticated_client, fake_db):
    """A signed payload still must not be able to move rows between doctors."""
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2victim", "conversation_id": "conv_test_1"}
    ]
    body = _body(doctor_id="user_2attacker", patient_id="patient-of-attacker")
    assert _post(unauthenticated_client, body).status_code == 204

    row = fake_db.store["call_logs"][0]
    assert row["doctor_id"] == "user_2victim"
    assert row.get("patient_id") != "patient-of-attacker"


def test_route_acknowledges_unknown_conversation(unauthenticated_client, fake_db):
    """204, not 404 — otherwise the endpoint is an existence oracle."""
    fake_db.store["call_logs"] = []
    assert _post(unauthenticated_client, _body()).status_code == 204


def test_route_ignores_other_event_types(unauthenticated_client, fake_db):
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2d1", "conversation_id": "conv_test_1"}
    ]
    body = json.dumps({"type": "post_call_audio", "data": {}}).encode()
    assert _post(unauthenticated_client, body).status_code == 204
    assert "patient_confirmed" not in fake_db.store["call_logs"][0]


def test_route_rejects_replayed_request(unauthenticated_client, fake_db):
    fake_db.store["call_logs"] = [
        {"id": "log-1", "doctor_id": "user_2d1", "conversation_id": "conv_test_1"}
    ]
    body = _body()
    stale = sign_payload(body, SECRET, int(time.time()) - 3600)
    assert _post(unauthenticated_client, body, header=stale).status_code == 401
