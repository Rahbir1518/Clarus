"""Database access for callers that have no tenant.

Read this before adding anything to it.

Everything else goes through TenantScope, which makes an unscoped query
impossible to express. This module is the deliberate exception, and it exists
for exactly one reason: a provider webhook arrives with no user, no token and
no doctor_id, so there is no tenant to scope to.

The safety property is not "the caller is trusted" — it is that each function
here can only reach a single row identified by an opaque value the provider
issued and we already stored. None of them accept a table name, none return
lists, and none can be steered into reading a row of the caller's choosing.

Adding a function that takes a table name, or that returns more than one row,
removes that property. Don't.

Neither function filters `deleted_at IS NULL`, unlike every read in
TenantScope. That is deliberate: the call really was placed, and its outcome
belongs on the record even if the row was deleted while the phone was ringing.
Nothing here returns the row to the webhook caller, and the soft-deleted log
stays invisible to the API, so completing it leaks nothing.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import NotFound


def _rows(response: Any) -> list[dict]:
    return list(getattr(response, "data", None) or [])


def get_call_log_by_conversation(client: Any, conversation_id: str) -> dict:
    """Resolve the call log a provider conversation belongs to.

    conversation_id is unguessable and issued by ElevenLabs, so it acts as the
    capability: holding one grants access to that call log and nothing else.
    """
    if not conversation_id:
        raise NotFound("Call log")
    rows = _rows(
        client.table("call_logs")
        .select("*")
        .eq("conversation_id", conversation_id)
        .execute()
    )
    if not rows:
        raise NotFound("Call log")
    return rows[0]


def update_call_log_by_conversation(
    client: Any, conversation_id: str, values: dict[str, Any]
) -> dict:
    """Write a call outcome back to the row that conversation belongs to.

    Deliberately keyed on conversation_id rather than a row id: it means the
    webhook can only ever complete a call the system itself initiated.
    """
    if not conversation_id:
        raise NotFound("Call log")

    # doctor_id is immutable here. A webhook must never be able to move a call
    # log to a different tenant, whatever the payload says.
    payload = {
        k: v
        for k, v in values.items()
        if k not in {"id", "doctor_id", "created_at", "conversation_id", "patient_id"}
    }
    if not payload:
        return get_call_log_by_conversation(client, conversation_id)

    rows = _rows(
        client.table("call_logs")
        .update(payload)
        .eq("conversation_id", conversation_id)
        .execute()
    )
    if not rows:
        raise NotFound("Call log")
    return rows[0]
