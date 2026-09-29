"""Call log request/response models.

Two read models rather than one, and the difference is the transcript.

A call transcript is the most sensitive thing in this database — an unedited
recording of a conversation with a patient. The calls page renders a table of
status and outcome; it has no use for the transcript until someone opens a
specific call. Returning it in the list would ship every transcript the
practice has ever recorded on each page load, to be dropped on the floor by the
renderer.

So the list returns metadata and the detail route returns the content. That
also gives the audit trail something meaningful to record: an entry against a
call someone actually opened, rather than one entry per page load that says
nothing about what was looked at.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

_READ_CONFIG = ConfigDict(extra="ignore")


class CallLogSummary(BaseModel):
    """A row in the calls table. No transcript, no extracted data."""

    model_config = _READ_CONFIG

    id: str
    doctor_id: str
    workflow_id: str | None = None
    patient_id: str | None = None
    trigger_node: str | None = None
    status: str = "pending"
    outcome: str | None = None
    keypress: str | None = None
    execution_log: list[Any] = []

    # The structured result. Cheap, and it is what the table renders badges
    # from — unlike the transcript, which is the conversation itself.
    patient_confirmed: bool | None = None
    reached_patient: bool | None = None
    confirmed_date: str | None = None
    confirmed_time: str | None = None
    callback_requested: bool | None = None
    needs_review: bool = True

    created_at: datetime | None = None
    updated_at: datetime | None = None


class CallLogRead(CallLogSummary):
    """One call, opened deliberately. Everything the provider gave us."""

    conversation_id: str | None = None
    transcript: str | None = None
    data_collection: dict[str, Any] = {}
    timezone: str | None = None
    availability_notes: str | None = None
    reviewed_at: datetime | None = None
    webhook_received_at: datetime | None = None
