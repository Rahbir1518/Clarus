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
POST   /api/elevenlabs/webhook          ElevenLabs post-call webhook
POST   /api/twilio/voice                TwiML webhook (Say + Gather)
POST   /api/twilio/gather               Handle keypress response
GET    /api/call-logs                   List execution logs
POST   /api/call-logs/{id}/check        Poll ElevenLabs for call result (local dev alternative to webhook)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import app.services.supabase_service as db
from app.services.workflow_engine import execute_workflow

logger = logging.getLogger(__name__)

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


class PatientCreate(BaseModel):
    name: str
    phone: str
    doctor_id: str
    dob: str | None = None
    mrn: str | None = None
    insurance: str | None = None
    primary_physician: str | None = None
    last_visit: str | None = None
    risk_level: str = "low"
    notes: str | None = None


class PatientUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    dob: str | None = None
    mrn: str | None = None
    insurance: str | None = None
    primary_physician: str | None = None
    last_visit: str | None = None
    risk_level: str | None = None
    notes: str | None = None


class ConditionCreate(BaseModel):
    icd10_code: str
    description: str
    hcc_category: str | None = None
    raf_impact: float = 0
    status: str = "documented"


class ConditionUpdate(BaseModel):
    icd10_code: str | None = None
    description: str | None = None
    hcc_category: str | None = None
    raf_impact: float | None = None
    status: str | None = None


class MedicationCreate(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    prescriber: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str = "active"
    notes: str | None = None


class MedicationUpdate(BaseModel):
    name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    prescriber: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None
    notes: str | None = None


class ExecuteRequest(BaseModel):
    patient_id: str
    trigger_node_type: str | None = None


class LabEventRequest(BaseModel):
    trigger_type: str           # e.g. "lab_results_received"
    patient_id: str
    doctor_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Patient endpoints
# ---------------------------------------------------------------------------

@router.get("/patients")
async def list_patients(doctor_id: str | None = None):
    return db.list_patients(doctor_id=doctor_id)


@router.post("/patients", status_code=201)
async def create_patient(body: PatientCreate):
    payload = body.model_dump()
    sb = db.get_supabase()
    return sb.table("patients").insert(payload).execute().data[0]


@router.get("/patients/{patient_id}")
async def get_patient(patient_id: str):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.put("/patients/{patient_id}")
async def update_patient(patient_id: str, body: PatientUpdate):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        return patient
    return db.update_patient(patient_id, payload)


@router.delete("/patients/{patient_id}", status_code=204)
async def delete_patient(patient_id: str):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    sb = db.get_supabase()
    sb.table("patients").delete().eq("id", patient_id).execute()


# ---------------------------------------------------------------------------
# Patient conditions
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/conditions")
async def list_conditions(patient_id: str):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.list_conditions(patient_id)


@router.post("/patients/{patient_id}/conditions", status_code=201)
async def create_condition(patient_id: str, body: ConditionCreate):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    payload = body.model_dump()
    payload["patient_id"] = patient_id
    return db.create_condition(payload)


@router.put("/patients/{patient_id}/conditions/{condition_id}")
async def update_condition(patient_id: str, condition_id: str, body: ConditionUpdate):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    return db.update_condition(condition_id, payload)


@router.delete("/patients/{patient_id}/conditions/{condition_id}", status_code=204)
async def delete_condition(patient_id: str, condition_id: str):
    db.delete_condition(condition_id)


# ---------------------------------------------------------------------------
# Patient medications
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/medications")
async def list_medications(patient_id: str):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.list_medications(patient_id)


@router.post("/patients/{patient_id}/medications", status_code=201)
async def create_medication(patient_id: str, body: MedicationCreate):
    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    payload = body.model_dump()
    payload["patient_id"] = patient_id
    return db.create_medication(payload)


@router.put("/patients/{patient_id}/medications/{medication_id}")
async def update_medication(patient_id: str, medication_id: str, body: MedicationUpdate):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    return db.update_medication(medication_id, payload)


@router.delete("/patients/{patient_id}/medications/{medication_id}", status_code=204)
async def delete_medication(patient_id: str, medication_id: str):
    db.delete_medication(medication_id)


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

    # Run the engine (async)
    execution_log = await execute_workflow(
        workflow=wf,
        patient=patient,
        trigger_node_type=body.trigger_node_type,
        call_log_id=log_id,
        doctor_id=wf.get("doctor_id"),
    )

    # Determine final status
    has_error = any(s.get("status") == "error" for s in execution_log)
    final_status = "failed" if has_error else "completed"

    db.update_call_log(log_id, {
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

        execution_log = await execute_workflow(
            workflow=wf,
            patient=patient,
            trigger_node_type=body.trigger_type,
            call_log_id=log_id,
            doctor_id=wf.get("doctor_id") or body.doctor_id,
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
# ElevenLabs post-call webhook
# ---------------------------------------------------------------------------

@router.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: Request):
    """
    Receives the post-call payload from ElevenLabs after a conversation ends.

    Expected shape (ElevenLabs Conversational AI webhook):
    {
      "type": "conversation_ended" | ...,
      "conversation_id": "...",
      "data": {
        "analysis": {
          "data_collection_results": {
            "call_outcome":              {"value": "appointment_booked", ...},
            "patient_confirmed":         {"value": "true", ...},
            "confirmed_date":            {"value": "2026-03-10", ...},
            "confirmed_time":            {"value": "14:00", ...},
            "doctor_name":               {"value": "Dr. Smith", ...},
            "patient_availability_notes": {"value": "...", ...},
          }
        },
        "transcript": "..."
      }
    }

    If ``patient_confirmed`` is true, creates a Google Calendar event for the
    doctor and updates the call_log.
    """
    from app.services.google_calendar_service import create_calendar_event

    payload = await request.json()
    logger.info("ElevenLabs webhook received: type=%s", payload.get("type"))

    # ---- extract conversation_id ----
    conversation_id = payload.get("conversation_id") or payload.get("data", {}).get("conversation_id")
    if not conversation_id:
        logger.warning("ElevenLabs webhook missing conversation_id")
        return {"success": False, "error": "missing conversation_id"}

    # ---- extract data collection results ----
    data_section = payload.get("data", {})
    analysis = data_section.get("analysis", {})
    dcr = analysis.get("data_collection_results", {})

    def _dcr_val(key: str) -> str:
        """Unwrap ElevenLabs DCR format: {"value": X, "rationale": "..."} → X."""
        entry = dcr.get(key, {})
        if isinstance(entry, dict):
            return str(entry.get("value", ""))
        return str(entry)

    call_outcome = _dcr_val("call_outcome")
    patient_confirmed_raw = _dcr_val("patient_confirmed")
    confirmed_date = _dcr_val("confirmed_date")
    confirmed_time = _dcr_val("confirmed_time")
    doctor_name = _dcr_val("doctor_name")
    availability_notes = _dcr_val("patient_availability_notes")
    transcript = data_section.get("transcript", "")

    patient_confirmed = patient_confirmed_raw.lower() in ("true", "yes", "1")

    # ---- find the call_log row that matches this conversation ----
    # The workflow engine stored conversation_id in the execution_log.
    # We search call_logs for a running entry whose execution_log contains
    # this conversation_id.
    call_log = _find_call_log_by_conversation_id(conversation_id)

    if not call_log:
        logger.warning("No call_log found for conversation_id=%s", conversation_id)
        return {"success": False, "error": "no matching call_log"}

    log_id = call_log["id"]

    # ---- update call_log with outcome ----
    update_payload: dict[str, Any] = {
        "outcome": call_outcome or "call_completed",
        "status": "completed",
    }

    # Store ElevenLabs data in a separate column or merge into execution_log
    elevenlabs_data = {
        "conversation_id": conversation_id,
        "call_outcome": call_outcome,
        "patient_confirmed": patient_confirmed,
        "confirmed_date": confirmed_date,
        "confirmed_time": confirmed_time,
        "doctor_name": doctor_name,
        "patient_availability_notes": availability_notes,
        "transcript": transcript[:5000] if transcript else "",
    }

    # Merge ElevenLabs data into the existing execution_log
    existing_log = call_log.get("execution_log") or []
    existing_log.append({
        "node_id": "elevenlabs_webhook",
        "node_type": "webhook",
        "label": "ElevenLabs Call Completed",
        "status": "ok",
        "message": f"Call outcome: {call_outcome}. Patient confirmed: {patient_confirmed}.",
        **elevenlabs_data,
    })
    update_payload["execution_log"] = existing_log

    db.update_call_log(log_id, update_payload)

    # ---- if patient confirmed, create Google Calendar event ----
    calendar_event = None
    if patient_confirmed and confirmed_date:
        doctor_id = call_log.get("doctor_id") or _get_doctor_id_from_workflow(call_log.get("workflow_id"))
        patient_id = call_log.get("patient_id")
        patient = db.get_patient(patient_id) if patient_id else None
        patient_name = patient.get("name", "Patient") if patient else "Patient"

        start_iso = f"{confirmed_date}T{confirmed_time or '09:00'}:00"
        try:
            calendar_event = await create_calendar_event(
                auth0_user_id=doctor_id,
                summary=f"Patient Appointment: {patient_name}",
                start_iso=start_iso,
                description=(
                    f"Follow-up appointment for {patient_name}.\n"
                    f"Scheduled via MedTrigger workflow.\n"
                    f"Call outcome: {call_outcome}"
                ),
                attendee_email=patient.get("email") if patient else None,
            )
            logger.info("Calendar event created: %s", calendar_event.get("id"))

            # Append calendar step to execution log
            existing_log.append({
                "node_id": "calendar_auto",
                "node_type": "schedule_appointment",
                "label": "Google Calendar Event Created",
                "status": "ok",
                "message": f"Event: {calendar_event.get('htmlLink', '')}",
                "calendar_event_id": calendar_event.get("id"),
            })
            db.update_call_log(log_id, {"execution_log": existing_log})
        except Exception as exc:
            logger.exception("Failed to create calendar event after ElevenLabs call")
            existing_log.append({
                "node_id": "calendar_auto",
                "node_type": "schedule_appointment",
                "label": "Google Calendar Event Failed",
                "status": "error",
                "message": str(exc),
            })
            db.update_call_log(log_id, {"execution_log": existing_log})

    return {
        "success": True,
        "call_log_id": log_id,
        "patient_confirmed": patient_confirmed,
        "calendar_event_id": calendar_event.get("id") if calendar_event else None,
    }


def _find_call_log_by_conversation_id(conversation_id: str) -> dict | None:
    """
    Search recent call_logs for one whose execution_log contains the given
    conversation_id.
    """
    logs = db.list_call_logs()
    for log in logs:
        exec_log = log.get("execution_log") or []
        for step in exec_log:
            if step.get("conversation_id") == conversation_id:
                return log
    return None


def _get_doctor_id_from_workflow(workflow_id: str | None) -> str | None:
    """Look up the doctor_id from the workflow record."""
    if not workflow_id:
        return None
    wf = db.get_workflow(workflow_id)
    return wf.get("doctor_id") if wf else None


# ---------------------------------------------------------------------------
# Twilio webhooks (fallback for non-ElevenLabs calls)
# ---------------------------------------------------------------------------

@router.post("/twilio/voice")
async def twilio_voice(request: Request, log_id: str | None = None):
    """
    TwiML webhook — Twilio calls this when the patient picks up.
    Returns a <Say> + <Gather> response.
    """
    call_log: dict = {}
    if log_id:
        call_log = db.get_call_log(log_id) or {}

    patient_message = call_log.get("outcome") or (
        "Hello, this is a message from your healthcare provider. "
        "Press 1 to confirm you received this message. "
        "Press 2 to request a callback."
    )

    gather_url = "/api/twilio/gather"
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
async def list_call_logs(
    workflow_id: str | None = None,
    doctor_id: str | None = None,
):
    return db.list_call_logs(workflow_id=workflow_id, doctor_id=doctor_id)


# ---------------------------------------------------------------------------
# Poll ElevenLabs for call result (local dev — no webhook needed)
# ---------------------------------------------------------------------------

@router.post("/call-logs/{log_id}/check")
async def check_call_status(log_id: str):
    """
    Polls ElevenLabs for the conversation result and processes it.

    Use this instead of the webhook during local development (no ngrok needed).
    The frontend can call this endpoint periodically or on-demand after a call
    is initiated.

    Flow:
      1. Find the call_log row → extract conversation_id from its execution_log
      2. Call ElevenLabs GET /v1/convai/conversations/{id}
      3. If the conversation is done, extract data collection results
      4. Update call_log with outcome
      5. If patient confirmed an appointment → create Google Calendar event
    """
    from app.services.elevenlabs_service import get_conversation
    from app.services.google_calendar_service import create_calendar_event

    call_log = db.get_call_log(log_id)
    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found")

    # Already completed? Return current state.
    if call_log.get("status") == "completed":
        return {
            "status": "completed",
            "call_log": call_log,
            "message": "Call already processed.",
        }

    # Find conversation_id from execution_log
    conversation_id = None
    exec_log = call_log.get("execution_log") or []
    for step in exec_log:
        if step.get("conversation_id"):
            conversation_id = step["conversation_id"]
            break

    if not conversation_id:
        return {
            "status": "waiting",
            "message": "No conversation_id found — call may not have been initiated yet.",
        }

    # Poll ElevenLabs
    try:
        conversation = await get_conversation(conversation_id)
    except Exception as exc:
        logger.warning("Failed to poll ElevenLabs: %s", exc)
        return {
            "status": "polling_error",
            "message": str(exc),
        }

    conv_status = conversation.get("status", "unknown")

    # If conversation is still in progress, return early
    if conv_status in ("in_progress", "processing"):
        return {
            "status": "in_progress",
            "message": "Call is still in progress.",
            "conversation_status": conv_status,
        }

    # Conversation is done — extract data collection results
    analysis = conversation.get("analysis", {})
    dcr = analysis.get("data_collection_results", {})

    def _dcr_val(key: str) -> str:
        entry = dcr.get(key, {})
        if isinstance(entry, dict):
            return str(entry.get("value", ""))
        return str(entry)

    call_outcome = _dcr_val("call_outcome")
    patient_confirmed_raw = _dcr_val("patient_confirmed")
    confirmed_date = _dcr_val("confirmed_date")
    confirmed_time = _dcr_val("confirmed_time")
    doctor_name = _dcr_val("doctor_name")
    availability_notes = _dcr_val("patient_availability_notes")
    transcript = conversation.get("transcript", "")

    patient_confirmed = patient_confirmed_raw.lower() in ("true", "yes", "1")

    # Update call_log
    elevenlabs_data = {
        "conversation_id": conversation_id,
        "call_outcome": call_outcome,
        "patient_confirmed": patient_confirmed,
        "confirmed_date": confirmed_date,
        "confirmed_time": confirmed_time,
        "doctor_name": doctor_name,
        "patient_availability_notes": availability_notes,
        "transcript": transcript[:5000] if isinstance(transcript, str) else "",
    }

    exec_log.append({
        "node_id": "elevenlabs_poll",
        "node_type": "poll_result",
        "label": "ElevenLabs Call Completed (polled)",
        "status": "ok",
        "message": f"Call outcome: {call_outcome}. Patient confirmed: {patient_confirmed}.",
        **elevenlabs_data,
    })

    update_payload: dict[str, Any] = {
        "outcome": call_outcome or "call_completed",
        "status": "completed",
        "execution_log": exec_log,
    }
    db.update_call_log(log_id, update_payload)

    # If patient confirmed → create Google Calendar event
    calendar_event = None
    if patient_confirmed and confirmed_date:
        doctor_id = _get_doctor_id_from_workflow(call_log.get("workflow_id"))
        patient_id = call_log.get("patient_id")
        patient = db.get_patient(patient_id) if patient_id else None
        patient_name = patient.get("name", "Patient") if patient else "Patient"

        start_iso = f"{confirmed_date}T{confirmed_time or '09:00'}:00"
        try:
            calendar_event = await create_calendar_event(
                auth0_user_id=doctor_id,
                summary=f"Patient Appointment: {patient_name}",
                start_iso=start_iso,
                description=(
                    f"Follow-up appointment for {patient_name}.\n"
                    f"Scheduled via MedTrigger workflow.\n"
                    f"Call outcome: {call_outcome}"
                ),
                attendee_email=patient.get("email") if patient else None,
            )
            logger.info("Calendar event created via polling: %s", calendar_event.get("id"))

            exec_log.append({
                "node_id": "calendar_poll",
                "node_type": "schedule_appointment",
                "label": "Google Calendar Event Created",
                "status": "ok",
                "message": f"Event: {calendar_event.get('htmlLink', '')}",
                "calendar_event_id": calendar_event.get("id"),
            })
            db.update_call_log(log_id, {"execution_log": exec_log})
        except Exception as exc:
            logger.exception("Calendar event creation failed during polling")
            exec_log.append({
                "node_id": "calendar_poll",
                "node_type": "schedule_appointment",
                "label": "Google Calendar Event Failed",
                "status": "error",
                "message": str(exc),
            })
            db.update_call_log(log_id, {"execution_log": exec_log})

    return {
        "status": "completed",
        "call_outcome": call_outcome,
        "patient_confirmed": patient_confirmed,
        "confirmed_date": confirmed_date,
        "confirmed_time": confirmed_time,
        "calendar_event_id": calendar_event.get("id") if calendar_event else None,
        "call_log_id": log_id,
    }
