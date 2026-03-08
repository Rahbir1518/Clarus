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


def update_patient(patient_id: str, payload: dict) -> dict:
    sb = get_supabase()
    return (
        sb.table("patients")
        .update(payload)
        .eq("id", patient_id)
        .execute()
        .data[0]
    )


# ---------------------------------------------------------------------------
# Patient-condition helpers
# ---------------------------------------------------------------------------

def list_conditions(patient_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("patient_conditions")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def create_condition(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("patient_conditions").insert(payload).execute().data[0]


def update_condition(condition_id: str, payload: dict) -> dict:
    sb = get_supabase()
    return (
        sb.table("patient_conditions")
        .update(payload)
        .eq("id", condition_id)
        .execute()
        .data[0]
    )


def delete_condition(condition_id: str) -> None:
    sb = get_supabase()
    sb.table("patient_conditions").delete().eq("id", condition_id).execute()


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


def list_call_logs(
    workflow_id: str | None = None,
    doctor_id: str | None = None,
) -> list[dict]:
    sb = get_supabase()
    q = sb.table("call_logs").select("*")
    if workflow_id:
        q = q.eq("workflow_id", workflow_id)
    if doctor_id:
        patient_ids = [
            p["id"]
            for p in sb.table("patients")
            .select("id")
            .eq("doctor_id", doctor_id)
            .execute()
            .data
        ]
        if not patient_ids:
            return []
        q = q.in_("patient_id", patient_ids)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# Patient-medication helpers
# ---------------------------------------------------------------------------

def list_medications(patient_id: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("patient_medications")
        .select("*")
        .eq("patient_id", patient_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def create_medication(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("patient_medications").insert(payload).execute().data[0]


def update_medication(medication_id: str, payload: dict) -> dict:
    sb = get_supabase()
    return (
        sb.table("patient_medications")
        .update(payload)
        .eq("id", medication_id)
        .execute()
        .data[0]
    )


def delete_medication(medication_id: str) -> None:
    sb = get_supabase()
    sb.table("patient_medications").delete().eq("id", medication_id).execute()


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def create_notification(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("notifications").insert(payload).execute().data[0]


def list_notifications(patient_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("notifications").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# Lab order helpers
# ---------------------------------------------------------------------------

def create_lab_order(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("lab_orders").insert(payload).execute().data[0]


def list_lab_orders(patient_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("lab_orders").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# Referral helpers
# ---------------------------------------------------------------------------

def create_referral(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("referrals").insert(payload).execute().data[0]


def list_referrals(patient_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("referrals").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# Staff assignment helpers
# ---------------------------------------------------------------------------

def create_staff_assignment(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("staff_assignments").insert(payload).execute().data[0]


def list_staff_assignments(patient_id: str | None = None, staff_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("staff_assignments").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    if staff_id:
        q = q.eq("staff_id", staff_id)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def create_report(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("reports").insert(payload).execute().data[0]


def get_report(report_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("reports").select("*").eq("id", report_id).execute().data
    return rows[0] if rows else None


def list_reports(patient_id: str | None = None, workflow_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("reports").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    if workflow_id:
        q = q.eq("workflow_id", workflow_id)
    return q.order("created_at", desc=True).execute().data


# ---------------------------------------------------------------------------
# PDF document helpers
# ---------------------------------------------------------------------------

def create_pdf_document(payload: dict) -> dict:
    sb = get_supabase()
    return sb.table("pdf_documents").insert(payload).execute().data[0]


def get_pdf_document(doc_id: str) -> dict | None:
    sb = get_supabase()
    rows = sb.table("pdf_documents").select("*").eq("id", doc_id).execute().data
    return rows[0] if rows else None


def list_pdf_documents(patient_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    q = sb.table("pdf_documents").select("*")
    if patient_id:
        q = q.eq("patient_id", patient_id)
    return q.order("created_at", desc=True).execute().data


def delete_pdf_document(doc_id: str) -> None:
    sb = get_supabase()
    sb.table("pdf_documents").delete().eq("id", doc_id).execute()