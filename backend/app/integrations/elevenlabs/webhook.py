"""Post-call webhook signature verification and payload parsing.

The previous backend accepted webhook posts with no verification at all, which
meant anyone who found the URL could POST a conversation_id with
patient_confirmed=true and have the system book a calendar appointment off it.
Nothing here trusts a request until the signature checks out.

Header format:  elevenlabs-signature: t=<unix_seconds>,v0=<hex_hmac_sha256>
Signed payload: "<timestamp>.<raw_request_body>"

https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

SIGNATURE_HEADER = "elevenlabs-signature"


class WebhookVerificationError(Exception):
    """The request did not come from ElevenLabs, or is too old to trust."""


def _parse_signature_header(header: str) -> tuple[int, str]:
    """Pull the timestamp and v0 digest out of `t=...,v0=...`."""
    timestamp: int | None = None
    digest: str | None = None

    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise WebhookVerificationError("Malformed timestamp") from exc
        elif key == "v0":
            # ElevenLabs has historically sent the digest both bare and with a
            # "v0=" prefix already stripped; accept either shape.
            digest = value.removeprefix("v0=")

    if timestamp is None or not digest:
        raise WebhookVerificationError("Signature header missing t or v0")
    return timestamp, digest


def verify_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> None:
    """Raise WebhookVerificationError unless the request is authentic and fresh.

    `raw_body` must be the exact bytes received. Re-serialising the parsed JSON
    changes key order and whitespace, and the digest will never match.
    """
    if not secret:
        # Fail closed. An unset secret must never mean "skip verification" —
        # that turns a missing environment variable into an open endpoint.
        raise WebhookVerificationError("Webhook secret is not configured")

    if not signature_header:
        raise WebhookVerificationError("Missing signature header")

    timestamp, provided = _parse_signature_header(signature_header)

    current = time.time() if now is None else now
    age = current - timestamp
    if age > tolerance_seconds:
        raise WebhookVerificationError("Signature timestamp is too old")
    # Guard the other direction too: a far-future timestamp would otherwise let
    # a captured request stay replayable indefinitely.
    if age < -tolerance_seconds:
        raise WebhookVerificationError("Signature timestamp is in the future")

    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(
        secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, provided):
        raise WebhookVerificationError("Signature mismatch")


def sign_payload(raw_body: bytes, secret: str, timestamp: int) -> str:
    """Build a signature header. Used by the tests, and for local replay."""
    signed_payload = f"{timestamp}.".encode() + raw_body
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------

# The outcomes the agent is instructed to return. Anything else is treated as
# unknown and routed to a human rather than silently accepted.
KNOWN_OUTCOMES = frozenset(
    {
        "confirmed",
        "reschedule_requested",
        "declined",
        "voicemail",
        "wrong_number",
        "no_answer",
        "patient_unavailable",
        "opted_out",
        "emergency",
    }
)


@dataclass(frozen=True)
class CallResult:
    """The structured outcome of a call, as extracted by the agent.

    Every field is optional. A call that did not reach the patient legitimately
    has almost nothing set, and the point of `needs_human_review` is to make
    that state explicit instead of letting downstream code read a missing value
    as a negative.
    """

    conversation_id: str
    status: str | None = None
    patient_confirmed: bool | None = None
    confirmed_date: str | None = None
    confirmed_time: str | None = None
    call_outcome: str | None = None
    patient_availability_notes: str | None = None
    callback_requested: bool | None = None
    reached_patient: bool | None = None
    transcript: str | None = None
    raw_data_collection: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_human_review(self) -> bool:
        if self.callback_requested:
            return True
        if self.call_outcome in {"reschedule_requested", "emergency", "opted_out"}:
            return True
        if self.call_outcome not in KNOWN_OUTCOMES:
            return True
        # Confirmed, but the agent could not pin down when. Booking this would
        # be guesswork — exactly the failure the old PM-guess heuristic caused.
        if self.patient_confirmed and not (self.confirmed_date and self.confirmed_time):
            return True
        return False

    @property
    def is_bookable(self) -> bool:
        """Whether this result alone justifies creating a calendar event."""
        return bool(
            self.patient_confirmed
            and self.confirmed_date
            and self.confirmed_time
            and not self.needs_human_review
        )


def _extract_value(item: Any) -> Any:
    """Data collection results arrive as {"value": ..., "rationale": ...}."""
    if isinstance(item, dict):
        return item.get("value")
    return item


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes"}:
            return True
        if lowered in {"false", "no"}:
            return False
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    # The LLM returns the string "null" often enough that treating it as a
    # value would put the literal text into a patient's appointment.
    if not text or text.lower() in {"null", "none", "n/a"}:
        return None
    return text


def parse_post_call_payload(payload: dict) -> CallResult:
    """Turn a post_call_transcription webhook body into a CallResult."""
    data = payload.get("data", {}) or {}
    analysis = data.get("analysis", {}) or {}
    collected = analysis.get("data_collection_results", {}) or {}

    values = {key: _extract_value(item) for key, item in collected.items()}

    return CallResult(
        conversation_id=data.get("conversation_id", ""),
        status=data.get("status"),
        patient_confirmed=_as_bool(values.get("patient_confirmed")),
        confirmed_date=_as_str(values.get("confirmed_date")),
        confirmed_time=_as_str(values.get("confirmed_time")),
        call_outcome=_as_str(values.get("call_outcome")),
        patient_availability_notes=_as_str(values.get("patient_availability_notes")),
        callback_requested=_as_bool(values.get("callback_requested")),
        reached_patient=_as_bool(values.get("reached_patient")),
        transcript=_flatten_transcript(data.get("transcript")),
        raw_data_collection=collected,
    )


def _flatten_transcript(transcript: Any) -> str | None:
    """Render the turn array as readable text for storage and display."""
    if not isinstance(transcript, list):
        return None
    lines = []
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role", "unknown")
        message = turn.get("message")
        if message:
            lines.append(f"{role}: {message}")
    return "\n".join(lines) or None


def loads_raw(raw_body: bytes) -> dict:
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise WebhookVerificationError("Body is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise WebhookVerificationError("Body is not a JSON object")
    return parsed
