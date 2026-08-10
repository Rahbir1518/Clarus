"""Placing a call — request/response models.

Separate from schemas/call_log.py, which models the stored record. This module
is about starting a conversation and reporting back what the provider called
it.

The asymmetry worth noticing: the client says *who* to call (a patient id it
owns) and never *what to say*. Every dynamic variable the agent substitutes is
assembled server-side from the patient row, because those values are spoken
aloud to a patient — a client that could set patient_name could make the agent
address someone by a name of its choosing.

That principle used to have a hole in it. `appointment_reason` was a 200-character
free-text field, and `callback_number` another, both sent by the browser and both
read aloud. The reasoning at the time was that they describe the appointment
rather than the person, which is true and is not the point: any free-text field
spoken to a patient is a channel for saying anything at all, including a lab
result. See AI_CALL_SAFETY_POLICY.md.

So the reason is now a code resolved against a fixed vocabulary, and the callback
number comes from configuration. The client picks from a list; it does not write
a script.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine.policy import ALLOWED_CALL_REASONS, DEFAULT_REASON_CODE


class StartWebCall(BaseModel):
    """Begin a browser-based (WebRTC) conversation."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(..., description="A patient belonging to the caller.")
    workflow_id: str | None = None

    # Which of the permitted reasons the patient is given for the call. Not the
    # words — the words live in ALLOWED_CALL_REASONS and are not client-settable.
    reason_code: str = Field(
        default=DEFAULT_REASON_CODE,
        description="One of " + ", ".join(sorted(ALLOWED_CALL_REASONS)),
    )

    @field_validator("reason_code")
    @classmethod
    def _known_reason(cls, value: str) -> str:
        if value not in ALLOWED_CALL_REASONS:
            # A 422 naming the field, rather than a call in which the agent reads
            # out a code nobody recognised.
            raise ValueError(
                f"unknown reason_code {value!r}; expected one of "
                + ", ".join(sorted(ALLOWED_CALL_REASONS))
            )
        return value


class WebCallStarted(BaseModel):
    """Everything the browser needs to open the session."""

    model_config = ConfigDict(extra="ignore")

    call_log_id: str
    token: str
    dynamic_variables: dict[str, str]


class BindConversation(BaseModel):
    """Report the conversation id the browser received from ElevenLabs."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., min_length=1, max_length=128)
