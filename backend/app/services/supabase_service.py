"""
Supabase service — thin wrapper around the supabase-py client.
Provides typed helpers for workflows, patients, and call_logs tables.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from supabase import Client, create_client

from app.core.config import settings

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

def _make_client() -> Client:
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(url, key)


_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


# ---------------------------------------------------------------------------
# Workflow helpers
# ---------------------------------------------------------------------------

def list_workflows(doctor_id: str | None = None, status: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("workflows").select("*")
    if doctor_id:
        q = q.eq("doctor_id", doctor_id)
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).execute().data


def get_workflow(workflow_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("workflows").select("*").eq("id", workflow_id).execute().data
    return rows[0] if rows else None


def create_workflow(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("workflows").insert(payload).execute().data[0]


def update_workflow(workflow_id: str, payload: dict) -> dict:
    sb = get_supabase()
    return (
        sb.table("workflows")
        .update(payload)
        .eq("id", workflow_id)
        .execute()
        .data[0]
    )


def delete_workflow(workflow_id: str) -> None:
    sb = get_supabase()
    sb.table("workflows").delete().eq("id", workflow_id).execute()


# ---------------------------------------------------------------------------
# Patient helpers
# ---------------------------------------------------------------------------

def get_patient(patient_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("patients").select("*").eq("id", patient_id).execute().data
    return rows[0] if rows else None


def list_patients(doctor_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("patients").select("*")
    if doctor_id:
        q = q.eq("doctor_id", doctor_id)
    return q.execute().data


# ---------------------------------------------------------------------------
# Call-log helpers
# ---------------------------------------------------------------------------

def create_call_log(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("call_logs").insert(payload).execute().data[0]


def get_call_log(log_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("call_logs").select("*").eq("id", log_id).execute().data
    return rows[0] if rows else None


def update_call_log(log_id: str, payload: dict) -> dict:
    sb = get_supabase()
    return (
        sb.table("call_logs")
        .update(payload)
        .eq("id", log_id)
        .execute()
        .data[0]
    )


def list_call_logs(workflow_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("call_logs").select("*")
    if workflow_id:
        q = q.eq("workflow_id", workflow_id)
    return q.order("created_at", desc=True).execute().data