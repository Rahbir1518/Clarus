"""Placing a call — request/response models.

Separate from schemas/call_log.py, which models the stored record. This module
is about starting a conversation and reporting back what the provider called
it.

The asymmetry worth noticing: the client says *who* to call (a patient id it
owns) and never *what to say*. Every dynamic variable the agent substitutes is
assembled server-side from the patient row, because those values are spoken
aloud to a patient — a client that could set patient_name could make the agent
address someone by a name of its choosing.
"""
from pydantic import BaseModel, ConfigDict, Field


class StartWebCall(BaseModel):
    """Begin a browser-based (WebRTC) conversation."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(..., description="A patient belonging to the caller.")
    workflow_id: str | None = None

    # Context for the conversation, not identity. Safe for the client to send:
    # it describes the appointment, not who is being called.
    appointment_reason: str = Field(default="your appointment", max_length=200)
    callback_number: str = Field(default="", max_length=32)


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
