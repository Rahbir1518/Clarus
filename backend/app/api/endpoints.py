"""
FastAPI route endpoints for MedTrigger.

Routes
------
GET    /api/workflows                   List workflows
POST   /api/workflows                   Create workflow
GET    /api/workflows/{id}              Get single workflow
PUT    /api/workflows/{id}              Update workflow
DELETE /api/workflows/{id}              Delete workflow
POST   /api/workflows/{id}/execute      Execute workflow for a patient
POST   /api/lab-event                   Simulate lab event → auto-execute matching workflows
POST   /api/twilio/voice                TwiML webhook (Say + Gather)
POST   /api/twilio/gather               Handle keypress response
GET    /api/call-logs                   List execution logs
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import app.services.supabase_service as db
from app.services.workflow_engine import execute_workflow

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class WorkflowCreate(BaseModel):
    doctor_id: str
    name: str
    description: str | None = None
    category: str = "Ungrouped"
    status: str = "DRAFT"
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None


class ExecuteRequest(BaseModel):
    patient_id: str
    trigger_node_type: str | None = None


class LabEventRequest(BaseModel):
    trigger_type: str           # e.g. "lab_results_received"
    patient_id: str
    doctor_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Workflow CRUD
# ---------------------------------------------------------------------------

@router.get("/workflows")
async def list_workflows(
    doctor_id: str | None = None,
    status: str | None = None,
):
    return db.list_workflows(doctor_id=doctor_id, status=status)


@router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowCreate):
    payload = body.model_dump()
    return db.create_workflow(payload)


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowUpdate):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        return wf
    return db.update_workflow(workflow_id, payload)


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete_workflow(workflow_id)


# ---------------------------------------------------------------------------
# Execute a single workflow manually
# ---------------------------------------------------------------------------

@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow_endpoint(workflow_id: str, body: ExecuteRequest):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    patient = db.get_patient(body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Create a call_log row (status = "running")
    log_row = db.create_call_log({
        "workflow_id": workflow_id,
        "patient_id": body.patient_id,
        "trigger_node": body.trigger_node_type,
        "status": "running",
    })
    log_id = log_row["id"]

    # Run the engine
    execution_log = execute_workflow(
        workflow=wf,
        patient=patient,
        trigger_node_type=body.trigger_node_type,
        call_log_id=log_id,
    )

    # Determine final status
    has_error = any(s.get("status") == "error" for s in execution_log)
    final_status = "failed" if has_error else "completed"

    updated_log = db.update_call_log(log_id, {
        "status": final_status,
        "execution_log": execution_log,
    })

    return {
        "call_log_id": log_id,
        "status": final_status,
        "execution_log": execution_log,
    }


# ---------------------------------------------------------------------------
# Lab event → find matching ENABLED workflows → execute
# ---------------------------------------------------------------------------

@router.post("/lab-event")
async def lab_event(body: LabEventRequest):
    """
    Simulates an external lab event arriving.
    Finds all ENABLED workflows whose first trigger node matches the event type,
    then executes each one for the given patient.
    """
    patient = db.get_patient(body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get all ENABLED workflows (optionally filter by doctor)
    workflows = db.list_workflows(doctor_id=body.doctor_id, status="ENABLED")

    matched_results = []
    for wf in workflows:
        nodes: list[dict] = wf.get("nodes") or []
        # Check if any trigger node matches the incoming event type
        has_matching_trigger = any(
            (n.get("data", {}).get("nodeType", "") or n.get("type", "")).lower() == body.trigger_type.lower()
            for n in nodes
        )
        if not has_matching_trigger:
            continue

        log_row = db.create_call_log({
            "workflow_id": wf["id"],
            "patient_id": body.patient_id,
            "trigger_node": body.trigger_type,
            "status": "running",
        })
        log_id = log_row["id"]

        execution_log = execute_workflow(
            workflow=wf,
            patient=patient,
            trigger_node_type=body.trigger_type,
            call_log_id=log_id,
        )

        has_error = any(s.get("status") == "error" for s in execution_log)
        final_status = "failed" if has_error else "completed"

        db.update_call_log(log_id, {"status": final_status, "execution_log": execution_log})

        matched_results.append({
            "workflow_id": wf["id"],
            "workflow_name": wf.get("name"),
            "call_log_id": log_id,
            "status": final_status,
        })

    return {
        "trigger_type": body.trigger_type,
        "patient_id": body.patient_id,
        "workflows_executed": len(matched_results),
        "results": matched_results,
    }


# ---------------------------------------------------------------------------
# Twilio webhooks
# ---------------------------------------------------------------------------

@router.post("/twilio/voice")
async def twilio_voice(request: Request, log_id: str | None = None):
    """
    TwiML webhook — Twilio calls this when the patient picks up.
    Returns a <Say> + <Gather> response.
    """
    # We read the call log to get any custom message
    call_log: dict = {}
    if log_id:
        call_log = db.get_call_log(log_id) or {}

    patient_message = call_log.get("outcome") or (
        "Hello, this is a message from your healthcare provider. "
        "Press 1 to confirm you received this message. "
        "Press 2 to request a callback."
    )

    gather_url = f"/api/twilio/gather"
    if log_id:
        gather_url += f"?log_id={log_id}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" action="{gather_url}" method="POST">
    <Say voice="Polly.Joanna">{patient_message}</Say>
  </Gather>
  <Say voice="Polly.Joanna">We did not receive your input. Goodbye.</Say>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/gather")
async def twilio_gather(request: Request, log_id: str | None = None):
    """
    Handles the patient's keypress from the Gather.
    Updates the call_log with the keypress value.
    """
    form = await request.form()
    digit = form.get("Digits", "")

    outcome_map = {
        "1": "confirmed",
        "2": "callback_requested",
    }
    outcome = outcome_map.get(str(digit), f"unknown_keypress_{digit}")

    if log_id:
        try:
            db.update_call_log(log_id, {"keypress": digit, "outcome": outcome, "status": "completed"})
        except Exception:
            pass  # Don't fail the TwiML response

    if digit == "1":
        reply = "Thank you for confirming. Goodbye."
    elif digit == "2":
        reply = "A member of our team will call you back shortly. Goodbye."
    else:
        reply = "We did not recognise that input. Goodbye."

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">{reply}</Say>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Call logs
# ---------------------------------------------------------------------------

@router.get("/call-logs")
async def list_call_logs(workflow_id: str | None = None):
    return db.list_call_logs(workflow_id=workflow_id)