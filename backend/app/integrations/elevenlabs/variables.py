"""The dynamic variables an agent prompt substitutes.

One function, because there are now three callers — the web call route, the
workflow engine's `call_patient` node, and `scripts/test_call.py` — and the
previous arrangement had each assembling the dict itself. That is a worse
problem than ordinary duplication: a placeholder missing from one copy is not an
error anywhere. It reaches the patient as the literal text "{{patient_name}}",
spoken aloud, and only on the path that forgot it.

**Keep this in step with `agents/*.yaml`.** The YAML is the source of truth for
which placeholders exist; this is the source of truth for what fills them.

Nothing here takes a value from a request body. Every one of these is said to a
patient, so `appointment_reason` arrives already resolved through
`app.engine.policy.resolve_call_reason` — a phrase from a fixed vocabulary,
never free text. See AI_CALL_SAFETY_POLICY.md.
"""
from __future__ import annotations

from datetime import date

from app.core.config import Settings, get_settings


def build_dynamic_variables(
    *,
    patient: dict,
    appointment_reason: str,
    callback_number: str = "",
    doctor_name: str | None = None,
    settings: Settings | None = None,
    today: date | None = None,
) -> dict[str, str]:
    """Every {{placeholder}} the agent prompt references.

    `appointment_reason` must already be a phrase from
    ALLOWED_CALL_REASONS — this function does not validate it, because a
    validator here would be a second place for the policy to live and the
    callers are the ones holding the node parameters.

    Fallbacks are all bland on purpose. "your doctor" is a worse call than the
    doctor's actual name and a much better one than saying "None".
    """
    settings = settings or get_settings()
    return {
        "patient_name": str(patient.get("name") or "there"),
        "doctor_name": str(
            doctor_name or patient.get("primary_physician") or "your doctor"
        ),
        "practice_name": settings.practice_name,
        "appointment_reason": appointment_reason,
        "callback_number": callback_number or settings.practice_callback_number,
        "timezone": settings.default_timezone,
        # The agent resolves "next Tuesday" against this. Without it every
        # relative date in the conversation is anchored to whenever the model
        # believes today is.
        "today_date": (today or date.today()).isoformat(),
    }
