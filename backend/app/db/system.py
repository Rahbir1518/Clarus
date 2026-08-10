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

Neither call-log function filters `deleted_at IS NULL`, unlike every read in
TenantScope. That is deliberate: the call really was placed, and its outcome
belongs on the record even if the row was deleted while the phone was ringing.
Nothing here returns the row to the webhook caller, and the soft-deleted log
stays invisible to the API, so completing it leaks nothing.
"""
from __future__ import annotations

from typing import Any

from app.core.errors import NotFound
from app.db.tenancy import TenantScope


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


def get_workflow_by_id(client: Any, workflow_id: str) -> dict:
    """Read one workflow by id, with no tenant to scope to.

    Narrower than it looks, and it has to stay that way. The only caller is the
    webhook resume path, and the id it passes is read off a `call_logs` row this
    module already resolved by `conversation_id` — never off the request. So the
    capability is still the provider-issued conversation id: holding one gets you
    the workflow that call was running, and nothing else.

    Adding a caller that takes `workflow_id` from a request body would make this
    an unscoped read of any tenant's workflow. Don't. Authenticated callers have
    `TenantScope.get_owned`, which answers 404 for a workflow that is not theirs.
    """
    if not workflow_id:
        raise NotFound("Workflow")
    rows = _rows(
        client.table("workflows").select("*").eq("id", workflow_id).execute()
    )
    if not rows:
        raise NotFound("Workflow")
    return rows[0]


def tenant_scope_for_row(client: Any, row: dict) -> TenantScope:
    """A TenantScope for the tenant that owns an already-stored row.

    The exception that proves the rule in `app/api/deps.py`: there, the tenant
    key comes from a verified token, and `get_tenant_scope` being the only
    constructor is what stops a handler addressing someone else's data. A
    webhook has no token, so it needs another way to say which tenant it is
    acting for — and the resume path genuinely does need to act as one, because
    it books appointments and writes notifications that must be checked exactly
    as an authenticated request's would be.

    The safety argument is provenance. `doctor_id` is read from a row this
    process stored, never from the webhook body, and the row was reached through
    `get_call_log_by_conversation` — keyed on an unguessable id the provider
    issued for a call this system placed. Nothing an attacker sends chooses the
    tenant; the most a forged payload can do is name a conversation that does not
    exist, which is a 404 before this is ever called.

    Every write after this point goes through the ordinary `TenantScope` checks,
    which is the reason to build one rather than write through the raw client.
    """
    doctor_id = str(row.get("doctor_id") or "")
    if not doctor_id:
        # TenantScope refuses a falsy key anyway; this names the reason.
        raise NotFound("Doctor")
    return TenantScope(client, doctor_id)
