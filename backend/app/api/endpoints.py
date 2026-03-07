"""
FastAPI route endpoints for MedTrigger.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File, Form
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
# Transcript-based fallback helpers
# ---------------------------------------------------------------------------

def _detect_confirmation_from_transcript(transcript: str) -> bool:
    """
    Scan the transcript for phrases indicating the patient agreed to an
    appointment.  Only looks at patient/user lines (not the agent).
    """
    import re
    text = transcript.lower()

    # Positive confirmation phrases spoken by the patient
    confirm_phrases = [
        r"\byes\b.*\b(works?|good|great|perfect|fine|sure|sounds? good|that works)\b",
        r"\b(sounds? good|sounds? great|that works|works for me|i can do that)\b",
        r"\b(yes|yeah|yep|yup|sure|absolutely|definitely|of course)\b",
        r"\b(i('?d| would) like to (schedule|book|confirm|make))\b",
        r"\b(please (schedule|book|go ahead))\b",
        r"\b(let'?s do it|go ahead|book it|confirm)\b",
        r"\b(i('?m| am) available)\b",
    ]

    # Negative phrases — if these dominate, don't confirm
    deny_phrases = [
        r"\b(no|nope|not interested|can'?t make it|don'?t want)\b",
        r"\b(i('?m| am) not available|cancel|decline)\b",
    ]

    confirm_count = sum(1 for p in confirm_phrases if re.search(p, text))
    deny_count = sum(1 for p in deny_phrases if re.search(p, text))

    return confirm_count > 0 and confirm_count > deny_count


def _extract_datetime_from_transcript(transcript: str, existing_time: str) -> tuple[str, str]:
    """
    Try to extract a date and time from the transcript text.
    Returns (date_str, time_str) — may be relative like "Thursday" or
    "March 12" which _resolve_date() will convert later.
    """
    import re

    text = transcript.lower()
    found_date = ""
    found_time = existing_time or ""

    # Look for day names
    day_pattern = r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    day_match = re.search(day_pattern, text)
    if day_match:
        found_date = day_match.group(1)

    # Look for "tomorrow" / "today"
    if re.search(r"\btomorrow\b", text):
        found_date = "tomorrow"
    elif re.search(r"\btoday\b", text) and not found_date:
        found_date = "today"

    # Look for "Month Day" like "March 12", "march 12th"
    month_day = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        text,
    )
    if month_day:
        found_date = f"{month_day.group(1)} {month_day.group(2)}"

    # Look for time patterns like "2:30", "2:30 PM", "14:30", "2 PM", "1:45 PM"
    if not found_time:
        time_match = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", text)
        if time_match:
            found_time = f"{time_match.group(1)}:{time_match.group(2)}"
            if time_match.group(3):
                found_time += f" {time_match.group(3).replace('.', '')}"
        else:
            # "2 PM", "3 am"
            time_match2 = re.search(r"\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)\b", text)
            if time_match2:
                found_time = f"{time_match2.group(1)}:00 {time_match2.group(2).replace('.', '')}"

    # ---- Word-based time parsing (e.g. "one forty-five", "three thirty") ----
    if not found_time:
        word_nums = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12,
        }
        word_mins = {
            "oh five": 5, "o five": 5, "ten": 10, "fifteen": 15,
            "twenty": 20, "twenty-five": 25, "thirty": 30,
            "thirty-five": 35, "forty": 40, "forty-five": 45,
            "fifty": 50, "fifty-five": 55,
        }
        for hour_word, hour_val in word_nums.items():
            for min_word, min_val in word_mins.items():
                if f"{hour_word} {min_word}" in text:
                    # Assume PM for typical appointment hours (1-6)
                    display_hour = hour_val
                    if display_hour <= 6:
                        display_hour += 12
                    found_time = f"{display_hour}:{min_val:02d}"
                    break
            if found_time:
                break

    return found_date, found_time


# ---------------------------------------------------------------------------
# Date/time helpers for ElevenLabs DCR values
# ---------------------------------------------------------------------------

def _resolve_date(raw: str) -> str:
    """
    Convert a raw date string from ElevenLabs into YYYY-MM-DD format.

    Handles:
      - Already formatted: "2026-03-12" → "2026-03-12"
      - Day names: "Thursday", "thursday" → next Thursday's date
      - Relative: "tomorrow" → tomorrow's date
      - Month + day: "March 12" → "2026-03-12"
      - Empty/unknown → "" (unchanged)
    """
    from datetime import date, timedelta
    import re

    if not raw or not raw.strip():
        return ""

    raw = raw.strip()

    # Already in YYYY-MM-DD format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    today = date.today()

    # "tomorrow"
    if raw.lower() == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    # "today"
    if raw.lower() == "today":
        return today.isoformat()

    # Day name like "Thursday", "thursday"
    day_names = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    if raw.lower() in day_names:
        target_day = day_names[raw.lower()]
        days_ahead = (target_day - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7  # Next week if today is that day
        return (today + timedelta(days=days_ahead)).isoformat()

    # "March 12", "march 12th", "Mar 12"
    month_names = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    match = re.match(r"([a-zA-Z]+)\s+(\d{1,2})", raw)
    if match:
        month_str = match.group(1).lower()
        day_num = int(match.group(2))
        month_num = month_names.get(month_str)
        if month_num:
            year = today.year
            candidate = date(year, month_num, day_num)
            if candidate < today:
                candidate = date(year + 1, month_num, day_num)
            return candidate.isoformat()

    # Return as-is if we can't parse it (better than empty)
    return raw


def _resolve_time(raw: str) -> str:
    """
    Convert a raw time string into HH:MM format.

    Handles:
      - Already formatted: "14:00" → "14:00"
      - 12-hour: "2:15 PM", "2:15pm" → "14:15"
      - Partial: "2:15" → "14:15" (assumes PM for appointment times)
      - Words: "two fifteen" → best effort
      - Empty → "09:00" (default)
    """
    import re

    if not raw or not raw.strip():
        return "09:00"

    raw = raw.strip()

    # Already in HH:MM format (24-hour)
    if re.match(r"^\d{1,2}:\d{2}$", raw):
        parts = raw.split(":")
        hour = int(parts[0])
        minute = parts[1]
        # If hour < 8, assume PM for medical appointments
        if hour < 8:
            hour += 12
        return f"{hour:02d}:{minute}"

    # 12-hour format: "2:15 PM", "2:15pm", "10:30 AM"
    match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)", raw)
    if match:
        hour = int(match.group(1))
        minute = match.group(2)
        ampm = match.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute}"

    # Just a number like "14" or "2"
    match = re.match(r"^(\d{1,2})$", raw)
    if match:
        hour = int(match.group(1))
        if hour < 8:
            hour += 12
        return f"{hour:02d}:00"

    return "09:00"


# ---------------------------------------------------------------------------
# Background auto-polling for ElevenLabs call results
# ---------------------------------------------------------------------------

async def _auto_poll_call_result(log_id: str, max_attempts: int = 40, interval: int = 30):
    """
    Background task that polls ElevenLabs every *interval* seconds until the
    call finishes, then processes the result (updates call_log, creates
    Google Calendar event if the patient confirmed).

    This replaces the need to manually call POST /api/call-logs/{id}/check.
    """
    from app.services.elevenlabs_service import get_conversation
    from app.services.google_calendar_service import create_calendar_event

    logger.info("Auto-poll started for call_log %s (max %d attempts, %ds interval)", log_id, max_attempts, interval)

    # Wait a bit before the first poll — the call takes time to connect
    await asyncio.sleep(15)

    for attempt in range(1, max_attempts + 1):
        try:
            call_log = db.get_call_log(log_id)
            if not call_log:
                logger.warning("Auto-poll: call_log %s not found, stopping.", log_id)
                return
            if call_log.get("status") == "completed":
                logger.info("Auto-poll: call_log %s already completed.", log_id)
                return

            # Find conversation_id from execution_log
            conversation_id = None
            exec_log = call_log.get("execution_log") or []
            for step in exec_log:
                if step.get("conversation_id"):
                    conversation_id = step["conversation_id"]
                    break

            if not conversation_id:
                logger.info("Auto-poll attempt %d: no conversation_id yet, waiting...", attempt)
                await asyncio.sleep(interval)
                continue

            # Poll ElevenLabs
            conversation = await get_conversation(conversation_id)
            conv_status = conversation.get("status", "unknown")
            logger.info("Auto-poll attempt %d: conversation status = %s", attempt, conv_status)

            # Dump full response keys for debugging
            logger.info("Auto-poll: conversation top-level keys = %s", list(conversation.keys()))
            analysis = conversation.get("analysis", {})
            logger.info("Auto-poll: analysis keys = %s", list(analysis.keys()) if isinstance(analysis, dict) else type(analysis))
            logger.info("Auto-poll: full analysis = %s", str(analysis)[:2000])

            if conv_status in ("in_progress", "processing", "initiated"):
                await asyncio.sleep(interval)
                continue

            # ---- Conversation is done — extract results ----
            dcr = analysis.get("data_collection_results", {})
            logger.info("Auto-poll: DCR raw = %s", str(dcr)[:1000])

            def _dcr_val(key: str) -> str:
                entry = dcr.get(key, {})
                if isinstance(entry, dict):
                    val = entry.get("value", "")
                else:
                    val = entry
                # Ensure we never return the string "None"
                if val is None:
                    return ""
                result = str(val).strip()
                return "" if result.lower() == "none" else result

            call_outcome = _dcr_val("call_outcome")
            patient_confirmed_raw = _dcr_val("patient_confirmed")
            confirmed_date = _dcr_val("confirmed_date")
            confirmed_time = _dcr_val("confirmed_time")
            doctor_name = _dcr_val("doctor_name")
            availability_notes = _dcr_val("patient_availability_notes")

            # Transcript may be a string or a list of message dicts
            raw_transcript = conversation.get("transcript", "")
            if isinstance(raw_transcript, list):
                transcript = "\n".join(
                    f"{msg.get('role','')}: {msg.get('message','')}"
                    for msg in raw_transcript
                    if isinstance(msg, dict)
                )
            else:
                transcript = raw_transcript or ""

            logger.info(
                "Auto-poll DCR values — outcome=%s, confirmed=%s, date='%s', time='%s'",
                call_outcome, patient_confirmed_raw, confirmed_date, confirmed_time,
            )
            logger.info("Auto-poll transcript (first 500 chars): %s", transcript[:500])

            # Also grab the AI-generated summary — most reliable source
            transcript_summary = analysis.get("transcript_summary", "") or ""
            call_successful = analysis.get("call_successful", "")
            logger.info("Auto-poll: transcript_summary = %s", transcript_summary)
            logger.info("Auto-poll: call_successful = %s", call_successful)

            patient_confirmed = patient_confirmed_raw.lower() in ("true", "yes", "1")

            # ---- Fallback 1: check transcript_summary from ElevenLabs ----
            if not patient_confirmed and transcript_summary:
                summary_lower = transcript_summary.lower()
                summary_confirm_phrases = [
                    "confirmed", "chose", "selected", "booked",
                    "scheduled", "agreed", "appointment for",
                ]
                if any(phrase in summary_lower for phrase in summary_confirm_phrases):
                    patient_confirmed = True
                    logger.info("Auto-poll: patient confirmation detected via transcript_summary")

            # ---- Fallback 2: detect confirmation from raw transcript ----
            if not patient_confirmed and transcript:
                patient_confirmed = _detect_confirmation_from_transcript(transcript)
                if patient_confirmed:
                    logger.info("Auto-poll: patient confirmation detected via transcript fallback")

            # ---- Extract date/time: try summary first, then raw transcript ----
            if patient_confirmed and not confirmed_date:
                # Try transcript_summary first (e.g., "Monday at 1:45 PM")
                if transcript_summary:
                    confirmed_date, confirmed_time = _extract_datetime_from_transcript(
                        transcript_summary, confirmed_time
                    )
                    if confirmed_date:
                        logger.info("Auto-poll: date from summary: %s %s", confirmed_date, confirmed_time)
                # Fall back to raw transcript
                if not confirmed_date and transcript:
                    confirmed_date, confirmed_time = _extract_datetime_from_transcript(
                        transcript, confirmed_time
                    )
                    if confirmed_date:
                        logger.info("Auto-poll: date from transcript: %s %s", confirmed_date, confirmed_time)

            # Parse relative dates like "Thursday", "tomorrow", "March 12" into YYYY-MM-DD
            confirmed_date = _resolve_date(confirmed_date)
            confirmed_time = _resolve_time(confirmed_time)

            # Default call_outcome if DCR didn't provide one
            if not call_outcome:
                call_outcome = "confirmed" if patient_confirmed else "completed"

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
                "node_id": "elevenlabs_auto_poll",
                "node_type": "poll_result",
                "label": "ElevenLabs Call Completed (auto-polled)",
                "status": "ok",
                "message": f"Call outcome: {call_outcome}. Patient confirmed: {patient_confirmed}.",
                **elevenlabs_data,
            })

            db.update_call_log(log_id, {
                "outcome": call_outcome or "call_completed",
                "status": "completed",
                "execution_log": exec_log,
            })

            # ---- If patient confirmed → create Google Calendar event ----
            if patient_confirmed and confirmed_date and confirmed_date.lower() != "none":
                doctor_id = _get_doctor_id_from_workflow(call_log.get("workflow_id"))
                if not doctor_id:
                    logger.warning("Auto-poll: No doctor_id found — cannot create calendar event")
                    exec_log.append({
                        "node_id": "calendar_auto_poll",
                        "node_type": "schedule_appointment",
                        "label": "Google Calendar Event Skipped",
                        "status": "error",
                        "message": "No doctor_id (Auth0 sub) found on workflow — cannot access Google Calendar.",
                    })
                    db.update_call_log(log_id, {"execution_log": exec_log})
                else:
                    patient_id = call_log.get("patient_id")
                    patient = db.get_patient(patient_id) if patient_id else None
                    patient_name = patient.get("name", "Patient") if patient else "Patient"

                    start_iso = f"{confirmed_date}T{confirmed_time or '09:00'}:00"
                    logger.info("Auto-poll: Creating calendar event — start=%s, doctor=%s", start_iso, doctor_id)
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
                        logger.info("Auto-poll: Calendar event created — %s", calendar_event.get("id"))
                        exec_log.append({
                            "node_id": "calendar_auto_poll",
                            "node_type": "schedule_appointment",
                            "label": "Google Calendar Event Created",
                            "status": "ok",
                            "message": f"Event: {calendar_event.get('htmlLink', '')}",
                            "calendar_event_id": calendar_event.get("id"),
                        })
                        db.update_call_log(log_id, {"execution_log": exec_log})
                    except Exception as exc:
                        logger.exception("Auto-poll: Calendar event creation failed")
                        exec_log.append({
                            "node_id": "calendar_auto_poll",
                            "node_type": "schedule_appointment",
                            "label": "Google Calendar Event Failed",
                            "status": "error",
                            "message": str(exc),
                        })
                        db.update_call_log(log_id, {"execution_log": exec_log})
            elif patient_confirmed and not confirmed_date:
                logger.warning("Auto-poll: Patient confirmed but no date collected from call")
                exec_log.append({
                    "node_id": "calendar_auto_poll",
                    "node_type": "schedule_appointment",
                    "label": "Google Calendar Event Skipped",
                    "status": "error",
                    "message": "Patient confirmed but ElevenLabs did not capture a date. Check your agent's data collection fields.",
                })
                db.update_call_log(log_id, {"execution_log": exec_log})

            logger.info("Auto-poll finished for call_log %s", log_id)
            return

        except Exception as exc:
            logger.warning("Auto-poll attempt %d error: %s", attempt, exc)
            await asyncio.sleep(interval)

    logger.warning("Auto-poll: max attempts reached for call_log %s", log_id)


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

    execution_log = await execute_workflow(
        workflow=wf,
        patient=patient,
        trigger_node_type=body.trigger_node_type,
        call_log_id=log_id,
        doctor_id=wf.get("doctor_id"),
    )

    # Check if a call was initiated (look for conversation_id in the log)
    call_initiated = any(step.get("conversation_id") for step in execution_log)

    # Determine final status
    has_error = any(s.get("status") == "error" for s in execution_log)
    if has_error:
        final_status = "failed"
    elif call_initiated:
        # Call is in progress — keep status as "running" so the
        # background poller knows it still needs processing
        final_status = "running"
    else:
        final_status = "completed"

    db.update_call_log(log_id, {
        "status": final_status,
        "execution_log": execution_log,
    })

    # If a call was initiated, start background polling automatically
    if call_initiated:
        asyncio.create_task(_auto_poll_call_result(log_id))
        logger.info("Background auto-poller started for call_log %s", log_id)

    return {
        "call_log_id": log_id,
        "status": final_status,
        "execution_log": execution_log,
        "message": (
            "Call initiated — the system will automatically check for results "
            "and create a calendar event when the patient confirms."
            if call_initiated
            else "Workflow executed."
        ),
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
            metadata=body.metadata,
            lab_results=body.metadata.get("lab_results", []),
        )

        call_initiated = any(step.get("conversation_id") for step in execution_log)
        has_error = any(s.get("status") == "error" for s in execution_log)
        if has_error:
            final_status = "failed"
        elif call_initiated:
            final_status = "running"
        else:
            final_status = "completed"

        db.update_call_log(log_id, {"status": final_status, "execution_log": execution_log})

        if call_initiated:
            asyncio.create_task(_auto_poll_call_result(log_id))

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

@router.get("/elevenlabs/debug/{conversation_id}")
async def elevenlabs_debug(conversation_id: str):
    """Debug endpoint: fetch raw ElevenLabs conversation data."""
    from app.services.elevenlabs_service import get_conversation
    conversation = await get_conversation(conversation_id)
    return conversation


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


# ---------------------------------------------------------------------------
# PDF upload & extraction
# ---------------------------------------------------------------------------

@router.post("/pdf/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    patient_id: str = Form(None),
    uploaded_by: str = Form(None),
):
    """
    Upload a medical PDF, extract structured data (patient info, lab results,
    tables), and optionally link it to a patient.
    """
    from app.services.pdf_service import parse_pdf_document

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF must be under 20 MB")

    try:
        parsed = parse_pdf_document(contents)
    except Exception as exc:
        logger.exception("PDF parsing failed")
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    doc_payload = {
        "filename": file.filename,
        "page_count": parsed.get("page_count"),
        "raw_text": parsed.get("raw_text", "")[:50000],
        "patient_info": parsed.get("patient_info", {}),
        "lab_results": parsed.get("lab_results", []),
        "tables_data": parsed.get("tables", []),
    }
    if patient_id:
        doc_payload["patient_id"] = patient_id
    if uploaded_by:
        doc_payload["uploaded_by"] = uploaded_by

    try:
        record = db.create_pdf_document(doc_payload)
    except Exception as exc:
        logger.exception("Failed to save PDF document")
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    return {
        "id": record.get("id"),
        "filename": file.filename,
        "page_count": parsed.get("page_count"),
        "patient_info": parsed.get("patient_info", {}),
        "lab_results": parsed.get("lab_results", []),
        "extracted_at": parsed.get("extracted_at"),
    }


@router.post("/pdf/intake")
async def pdf_intake(
    file: UploadFile = File(...),
    doctor_id: str = Form(...),
):
    """
    Upload a medical PDF to create a new patient profile.
    Extracts patient demographics, medications, and lab results from the PDF
    and creates the patient record + medication records automatically.
    """
    from app.services.pdf_service import parse_pdf_document

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF must be under 20 MB")

    try:
        parsed = parse_pdf_document(contents)
    except Exception as exc:
        logger.exception("PDF parsing failed")
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    patient_info = parsed.get("patient_info", {})
    medications = parsed.get("medications", [])
    lab_results = parsed.get("lab_results", [])

    patient_name = patient_info.get("name", "").strip()
    if not patient_name:
        patient_name = f"Patient from {file.filename}"

    dob_raw = patient_info.get("dob", "")
    dob_iso = None
    if dob_raw:
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
                     "%m/%d/%y", "%m-%d-%y", "%d/%m/%y", "%d-%m-%y"):
            try:
                from datetime import datetime as _dt
                dob_iso = _dt.strptime(dob_raw, fmt).date().isoformat()
                break
            except ValueError:
                continue

    patient_payload: dict[str, Any] = {
        "name": patient_name,
        "phone": patient_info.get("phone", ""),
        "doctor_id": doctor_id,
    }
    if dob_iso:
        patient_payload["dob"] = dob_iso
    if patient_info.get("mrn"):
        patient_payload["mrn"] = patient_info["mrn"]
    if patient_info.get("insurance"):
        patient_payload["insurance"] = patient_info["insurance"]

    sb = db.get_supabase()
    try:
        patient_row = sb.table("patients").insert(patient_payload).execute().data[0]
    except Exception as exc:
        logger.exception("Failed to create patient from PDF")
        raise HTTPException(status_code=500, detail=f"Failed to create patient: {exc}")

    patient_id = patient_row["id"]

    created_medications: list[dict] = []
    for med in medications:
        try:
            med_payload: dict[str, Any] = {
                "patient_id": patient_id,
                "name": med.get("name", ""),
                "status": med.get("status", "active"),
            }
            if med.get("dosage"):
                med_payload["dosage"] = med["dosage"]
            row = db.create_medication(med_payload)
            created_medications.append(row)
        except Exception as exc:
            logger.warning("Failed to create medication %s: %s", med.get("name"), exc)

    try:
        db.create_pdf_document({
            "patient_id": patient_id,
            "filename": file.filename,
            "page_count": parsed.get("page_count"),
            "raw_text": parsed.get("raw_text", "")[:50000],
            "patient_info": patient_info,
            "lab_results": lab_results,
            "tables_data": parsed.get("tables", []),
            "uploaded_by": doctor_id,
        })
    except Exception:
        pass

    return {
        "patient": patient_row,
        "extracted": {
            "patient_info": patient_info,
            "medications": medications,
            "lab_results": lab_results,
            "page_count": parsed.get("page_count"),
        },
        "created_medications": len(created_medications),
    }


@router.post("/patients/{patient_id}/import-pdf")
async def import_pdf_to_patient(patient_id: str, file: UploadFile = File(...)):
    """
    Upload a medical PDF for an existing patient.
    Parses the PDF and updates the patient record with any extracted fields
    that are currently empty (does not overwrite existing data).
    Also creates medication records for any medications found in the PDF.
    """
    from app.services.pdf_service import parse_pdf_document

    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF must be under 20 MB")

    try:
        parsed = parse_pdf_document(contents)
    except Exception as exc:
        logger.exception("PDF parsing failed")
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    patient_info = parsed.get("patient_info", {})
    medications = parsed.get("medications", [])
    lab_results = parsed.get("lab_results", [])

    # --- Update patient fields that are currently empty ---
    dob_raw = patient_info.get("dob", "")
    dob_iso = None
    if dob_raw:
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
                     "%m/%d/%y", "%m-%d-%y", "%d/%m/%y", "%d-%m-%y"):
            try:
                from datetime import datetime as _dt
                dob_iso = _dt.strptime(dob_raw, fmt).date().isoformat()
                break
            except ValueError:
                continue

    FIELD_MAP = {
        "name": patient_info.get("name", "").strip(),
        "phone": patient_info.get("phone", "").strip(),
        "dob": dob_iso,
        "mrn": patient_info.get("mrn", "").strip(),
        "insurance": patient_info.get("insurance", "").strip(),
    }

    update_payload: dict[str, Any] = {}
    updated_fields: list[str] = []
    for field, extracted_value in FIELD_MAP.items():
        if extracted_value and not patient.get(field):
            update_payload[field] = extracted_value
            updated_fields.append(field)

    updated_patient = patient
    if update_payload:
        try:
            updated_patient = db.update_patient(patient_id, update_payload)
        except Exception as exc:
            logger.warning("Failed to update patient from PDF: %s", exc)

    # --- Add medications (skip duplicates) ---
    existing_meds = db.list_medications(patient_id)
    existing_med_names = {
        (m.get("name") or "").lower() for m in existing_meds
    }

    added_medications: list[dict] = []
    for med in medications:
        med_name = med.get("name", "").strip()
        if not med_name or med_name.lower() in existing_med_names:
            continue
        try:
            med_payload: dict[str, Any] = {
                "patient_id": patient_id,
                "name": med_name,
                "status": med.get("status", "active"),
            }
            if med.get("dosage"):
                med_payload["dosage"] = med["dosage"]
            row = db.create_medication(med_payload)
            added_medications.append(row)
            existing_med_names.add(med_name.lower())
        except Exception as exc:
            logger.warning("Failed to create medication %s: %s", med_name, exc)

    # --- Store PDF document record ---
    try:
        db.create_pdf_document({
            "patient_id": patient_id,
            "filename": file.filename,
            "page_count": parsed.get("page_count"),
            "raw_text": parsed.get("raw_text", "")[:50000],
            "patient_info": patient_info,
            "lab_results": lab_results,
            "tables_data": parsed.get("tables", []),
        })
    except Exception:
        pass

    return {
        "patient": updated_patient,
        "updated_fields": updated_fields,
        "extracted": {
            "patient_info": patient_info,
            "medications": medications,
            "lab_results": lab_results,
            "page_count": parsed.get("page_count"),
        },
        "added_medications": len(added_medications),
        "skipped_medications": len(medications) - len(added_medications),
    }


@router.get("/pdf/documents")
async def list_pdf_documents(patient_id: str | None = None):
    return db.list_pdf_documents(patient_id=patient_id)


@router.get("/pdf/documents/{doc_id}")
async def get_pdf_document(doc_id: str):
    doc = db.get_pdf_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="PDF document not found")
    return doc


@router.delete("/pdf/documents/{doc_id}", status_code=204)
async def delete_pdf_document(doc_id: str):
    db.delete_pdf_document(doc_id)


@router.post("/pdf/extract-and-execute")
async def extract_pdf_and_execute(
    file: UploadFile = File(...),
    patient_id: str = Form(...),
    workflow_id: str = Form(...),
):
    """
    Upload a PDF (e.g. lab report), extract data, then execute a workflow
    with the extracted lab results injected into the execution context.
    """
    from app.services.pdf_service import parse_pdf_document

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()

    try:
        parsed = parse_pdf_document(contents)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}")

    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    patient = db.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    doc_record = db.create_pdf_document({
        "patient_id": patient_id,
        "filename": file.filename,
        "page_count": parsed.get("page_count"),
        "raw_text": parsed.get("raw_text", "")[:50000],
        "patient_info": parsed.get("patient_info", {}),
        "lab_results": parsed.get("lab_results", []),
        "tables_data": parsed.get("tables", []),
    })

    log_row = db.create_call_log({
        "workflow_id": workflow_id,
        "patient_id": patient_id,
        "trigger_node": "pdf_upload",
        "status": "running",
    })
    log_id = log_row["id"]

    execution_log = await execute_workflow(
        workflow=wf,
        patient=patient,
        call_log_id=log_id,
        doctor_id=wf.get("doctor_id"),
        lab_results=parsed.get("lab_results", []),
        metadata={
            "pdf_document_id": doc_record.get("id"),
            "patient_info": parsed.get("patient_info", {}),
            "lab_results": parsed.get("lab_results", []),
        },
    )

    has_error = any(s.get("status") == "error" for s in execution_log)
    final_status = "failed" if has_error else "completed"

    db.update_call_log(log_id, {
        "status": final_status,
        "execution_log": execution_log,
    })

    return {
        "call_log_id": log_id,
        "pdf_document_id": doc_record.get("id"),
        "status": final_status,
        "lab_results_found": len(parsed.get("lab_results", [])),
        "patient_info_extracted": parsed.get("patient_info", {}),
        "execution_log": execution_log,
    }


# ---------------------------------------------------------------------------
# Notifications CRUD
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def list_notifications(patient_id: str | None = None):
    return db.list_notifications(patient_id=patient_id)


# ---------------------------------------------------------------------------
# Lab orders CRUD
# ---------------------------------------------------------------------------

@router.get("/lab-orders")
async def list_lab_orders(patient_id: str | None = None):
    return db.list_lab_orders(patient_id=patient_id)


# ---------------------------------------------------------------------------
# Referrals CRUD
# ---------------------------------------------------------------------------

@router.get("/referrals")
async def list_referrals(patient_id: str | None = None):
    return db.list_referrals(patient_id=patient_id)


# ---------------------------------------------------------------------------
# Staff assignments CRUD
# ---------------------------------------------------------------------------

@router.get("/staff-assignments")
async def list_staff_assignments(
    patient_id: str | None = None,
    staff_id: str | None = None,
):
    return db.list_staff_assignments(patient_id=patient_id, staff_id=staff_id)


# ---------------------------------------------------------------------------
# Reports CRUD
# ---------------------------------------------------------------------------

@router.get("/reports")
async def list_reports(
    patient_id: str | None = None,
    workflow_id: str | None = None,
):
    return db.list_reports(patient_id=patient_id, workflow_id=workflow_id)


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
