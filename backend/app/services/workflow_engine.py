"""
Workflow Execution Engine
--------------------------
Takes a saved workflow's nodes[] and edges[] (React Flow format),
walks the graph in topological order starting from the trigger node,
and dispatches each node type to its handler.

Returns a list of step-log dicts that gets stored in call_logs.execution_log.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node type constants (must match frontend node catalogue nodeType values)
# ---------------------------------------------------------------------------

TRIGGER_TYPES = {
    "lab_results_received",
    "bloodwork_received",
    "imaging_results_ready",
    "appointment_missed",
    "patient_due_for_labs",
    "prescription_expiring",
    "new_patient_registered",
    "follow_up_due",
    "abnormal_result_detected",
}

CONDITION_TYPES = {
    "check_insurance",
    "check_patient_age",
    "check_result_values",
    "check_appointment_history",
    "check_medication_list",
}

ACTION_TYPES = {
    "call_patient",
    "send_sms",
    "schedule_appointment",
    "create_lab_order",
    "send_notification",
    "create_referral",
    "update_patient_record",
    "assign_to_staff",
}

OUTPUT_TYPES = {
    "log_completion",
    "generate_transcript",
    "create_report",
    "send_summary_to_doctor",
}


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _build_adjacency(edges: list[dict]) -> dict[str, list[str]]:
    """Return {source_node_id: [target_node_id, ...]} — used for non-condition nodes."""
    adj: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)
    return adj


def _build_adjacency_with_handles(edges: list[dict]) -> dict[str, list[tuple[str, str | None]]]:
    """
    Return {source_node_id: [(target_node_id, source_handle), ...]}.
    source_handle is "true", "false", or None for edges without a handle.
    """
    adj: dict[str, list[tuple[str, str | None]]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            handle = edge.get("sourceHandle")
            adj.setdefault(src, []).append((tgt, handle))
    return adj


def _find_trigger_node(nodes: list[dict]) -> dict | None:
    """Return the first node whose type is a trigger type."""
    for node in nodes:
        node_type = node.get("data", {}).get("nodeType", "") or node.get("type", "")
        if node_type in TRIGGER_TYPES:
            return node
    return None


def _get_successors(
    source_id: str,
    node_type: str,
    condition_passed: bool | None,
    adj_with_handles: dict[str, list[tuple[str, str | None]]],
    adj_simple: dict[str, list[str]],
) -> list[str]:
    """
    Get the next node IDs to visit after executing source_id.

    For condition nodes: only return targets from the matching handle
      (sourceHandle="true" when passed, sourceHandle="false" when failed).
    For other nodes: return all targets.
    """
    if node_type in CONDITION_TYPES and condition_passed is not None:
        # Condition node — only follow the branch that matches the result
        handle_to_follow = "true" if condition_passed else "false"
        targets: list[str] = []
        for tgt, h in adj_with_handles.get(source_id, []):
            if h == handle_to_follow:
                targets.append(tgt)
            elif h is None and handle_to_follow == "true":
                targets.append(tgt)
        return targets

    return adj_simple.get(source_id, [])


# ---------------------------------------------------------------------------
# Step log helper
# ---------------------------------------------------------------------------

def _step_log(node: dict, status: str, message: str, extra: dict | None = None) -> dict:
    data = node.get("data", {})
    return {
        "node_id": node.get("id"),
        "node_type": data.get("nodeType") or node.get("type"),
        "label": data.get("label", ""),
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }


def _get_node_params(node: dict) -> dict:
    """Extract the params dict from a node's data."""
    return node.get("data", {}).get("params", {})


# ---------------------------------------------------------------------------
# Trigger handler
# ---------------------------------------------------------------------------

async def _handle_trigger(node: dict, context: dict) -> tuple[bool, dict]:
    return True, _step_log(node, "ok", "Trigger fired")


# ---------------------------------------------------------------------------
# Condition handlers — real logic
# ---------------------------------------------------------------------------

async def _handle_check_patient_age(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Check patient age against a configured threshold.
    Params: operator (greater_than|less_than|equal_to|between), threshold, threshold_max
    """
    patient = context.get("patient", {})
    dob_str = patient.get("dob")

    if not dob_str:
        return False, _step_log(node, "error", "Patient date of birth is missing")

    try:
        if "T" in str(dob_str):
            dob = datetime.fromisoformat(str(dob_str).replace("Z", "+00:00")).date()
        else:
            dob = date.fromisoformat(str(dob_str))
    except (ValueError, TypeError):
        return False, _step_log(node, "error", f"Invalid DOB format: {dob_str}")

    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    params = _get_node_params(node)
    operator = params.get("operator", "greater_than")
    try:
        threshold = int(params.get("threshold", "0"))
    except (ValueError, TypeError):
        threshold = 0
    try:
        threshold_max = int(params.get("threshold_max", "120"))
    except (ValueError, TypeError):
        threshold_max = 120

    if operator == "greater_than":
        passed = age > threshold
    elif operator == "less_than":
        passed = age < threshold
    elif operator == "equal_to":
        passed = age == threshold
    elif operator == "between":
        passed = threshold <= age <= threshold_max
    else:
        passed = age > threshold

    status = "ok" if passed else "skipped"
    msg = f"Patient age {age} {'PASS' if passed else 'FAIL'} ({operator} {threshold})"
    return passed, _step_log(node, status, msg, extra={"patient_age": age})


async def _handle_check_insurance(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Verify patient insurance matches configured criteria.
    Params: insurance_type ("any" or a specific provider name)
    """
    patient = context.get("patient", {})
    insurance = (patient.get("insurance") or "").strip()

    params = _get_node_params(node)
    required_type = (params.get("insurance_type") or "any").strip()

    if required_type.lower() == "any":
        passed = bool(insurance)
        msg = f"Insurance {'present' if passed else 'missing'}: '{insurance}'"
    else:
        passed = required_type.lower() in insurance.lower()
        msg = f"Insurance '{insurance}' {'matches' if passed else 'does not match'} '{required_type}'"

    status = "ok" if passed else "skipped"
    return passed, _step_log(node, status, f"Condition: {msg}", extra={"insurance": insurance})


async def _handle_check_result_values(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Evaluate lab result values against thresholds.
    Params: test_name, operator (greater_than|less_than|in_range|out_of_range),
            threshold, threshold_max
    Context can carry lab_results from PDF extraction or the trigger event metadata.
    """
    params = _get_node_params(node)
    test_name = (params.get("test_name") or "").strip()
    operator = params.get("operator", "greater_than")

    lab_results = context.get("lab_results", [])
    if not lab_results:
        metadata = context.get("metadata", {})
        lab_results = metadata.get("lab_results", [])

    if not lab_results:
        return False, _step_log(node, "error", "No lab result data available in context")

    if not test_name:
        return False, _step_log(node, "error", "No test_name configured for check_result_values")

    match = None
    for r in lab_results:
        if test_name.lower() in str(r.get("test_name", "")).lower():
            match = r
            break

    if not match:
        return False, _step_log(node, "error", f"Lab test '{test_name}' not found in results")

    try:
        value = float(match.get("value", 0))
    except (ValueError, TypeError):
        return False, _step_log(node, "error", f"Non-numeric value for '{test_name}'")

    try:
        threshold = float(params.get("threshold", "0"))
    except (ValueError, TypeError):
        threshold = 0.0
    try:
        threshold_max = float(params.get("threshold_max", "999"))
    except (ValueError, TypeError):
        threshold_max = 999.0

    if operator == "greater_than":
        passed = value > threshold
    elif operator == "less_than":
        passed = value < threshold
    elif operator == "in_range":
        passed = threshold <= value <= threshold_max
    elif operator == "out_of_range":
        passed = value < threshold or value > threshold_max
    else:
        passed = value > threshold

    status = "ok" if passed else "skipped"
    msg = f"{test_name}={value} {'PASS' if passed else 'FAIL'} ({operator} {threshold})"
    return passed, _step_log(node, status, msg, extra={"test_name": test_name, "value": value})


async def _handle_check_appointment_history(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Check if patient is overdue for appointments.
    Params: days_since_last (default 90)
    """
    import app.services.supabase_service as db

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)
    try:
        days_threshold = int(params.get("days_since_last", "90"))
    except (ValueError, TypeError):
        days_threshold = 90

    try:
        call_logs = db.list_call_logs()
        patient_logs = [
            cl for cl in call_logs
            if cl.get("patient_id") == patient_id and cl.get("status") == "completed"
        ]
    except Exception as exc:
        logger.warning("Failed to query appointment history: %s", exc)
        patient_logs = []

    last_date = None
    if patient_logs:
        for cl in patient_logs:
            created = cl.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if last_date is None or dt > last_date:
                        last_date = dt
                except (ValueError, TypeError):
                    pass

    if last_date is None:
        passed = True
        msg = f"No appointment history found — treating as overdue (>{days_threshold} days)"
        extra = {"last_appointment": None, "days_since": None}
    else:
        now = datetime.now(timezone.utc)
        days_since = (now - last_date).days
        passed = days_since > days_threshold
        msg = (
            f"Last appointment {days_since} days ago — "
            f"{'PASS (overdue)' if passed else 'FAIL (recent)'} "
            f"(threshold: {days_threshold} days)"
        )
        extra = {"last_appointment": last_date.isoformat(), "days_since": days_since}

    status = "ok" if passed else "skipped"
    return passed, _step_log(node, status, msg, extra=extra)


async def _handle_check_medication_list(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Check if patient is on specific medications.
    Params: medication (name or partial match, comma-separated for multiple)
    """
    import app.services.supabase_service as db

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)
    search_terms = [
        t.strip().lower()
        for t in (params.get("medication") or "").split(",")
        if t.strip()
    ]

    if not search_terms:
        return False, _step_log(node, "error", "No medication name configured")

    try:
        medications = db.list_medications(patient_id)
    except Exception as exc:
        logger.warning("Failed to query medications: %s", exc)
        return False, _step_log(node, "error", f"DB error: {exc}")

    active_meds = [m for m in medications if (m.get("status") or "").lower() == "active"]

    matched = []
    for med in active_meds:
        med_name = (med.get("name") or "").lower()
        for term in search_terms:
            if term in med_name:
                matched.append(med.get("name", ""))
                break

    passed = len(matched) > 0
    status = "ok" if passed else "skipped"
    if passed:
        msg = f"Found matching medication(s): {', '.join(matched)}"
    else:
        msg = f"No active medications matching: {', '.join(search_terms)}"

    return passed, _step_log(node, status, msg, extra={"matched_medications": matched})


_CONDITION_HANDLERS: dict[str, Any] = {
    "check_patient_age": _handle_check_patient_age,
    "check_insurance": _handle_check_insurance,
    "check_result_values": _handle_check_result_values,
    "check_appointment_history": _handle_check_appointment_history,
    "check_medication_list": _handle_check_medication_list,
}


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def _handle_call_patient(node: dict, context: dict) -> tuple[bool, dict]:
    """Initiate an outbound call via ElevenLabs + Twilio."""
    from app.services.elevenlabs_service import initiate_outbound_call

    patient = context.get("patient", {})
    phone = patient.get("phone")
    patient_name = patient.get("name", "Patient")
    doctor_name = context.get("doctor_name", "your doctor")
    call_log_id = context.get("call_log_id")

    if not phone:
        return False, _step_log(node, "error", "No patient phone number available")

    params = _get_node_params(node)
    lab_summary = params.get("lab_result_summary", "Your recent lab results are ready.")

    try:
        result = await initiate_outbound_call(
            patient_phone=phone,
            patient_name=patient_name,
            doctor_name=doctor_name,
            lab_result_summary=lab_summary,
            extra_context={
                "call_log_id": call_log_id or "",
                "workflow_id": context.get("workflow_id", ""),
            },
        )
        conversation_id = result.get("conversation_id", "")
        context["conversation_id"] = conversation_id

        return True, _step_log(
            node, "ok",
            f"ElevenLabs call initiated — conversation_id={conversation_id}",
            extra={"conversation_id": conversation_id},
        )
    except Exception as exc:
        logger.exception("ElevenLabs call failed")
        return False, _step_log(node, "error", f"ElevenLabs call error: {exc}")


async def _handle_schedule_appointment(node: dict, context: dict) -> tuple[bool, dict]:
    """Create a Google Calendar event for the appointment."""
    from app.services.google_calendar_service import create_calendar_event

    patient = context.get("patient", {})
    patient_name = patient.get("name", "Patient")
    doctor_id = context.get("doctor_id")
    appointment = context.get("appointment", {})

    if not appointment.get("confirmed_date"):
        return True, _step_log(
            node, "ok",
            "Appointment will be scheduled when the patient confirms during the call. "
            "The ElevenLabs webhook will trigger calendar creation.",
            extra={"deferred": True},
        )

    if not doctor_id:
        return False, _step_log(
            node, "error",
            "No doctor_id in context — cannot access Google Calendar",
        )

    confirmed_date = appointment["confirmed_date"]
    confirmed_time = appointment.get("confirmed_time", "09:00")
    start_iso = f"{confirmed_date}T{confirmed_time}:00"

    try:
        event = await create_calendar_event(
            auth0_user_id=doctor_id,
            summary=f"Patient Appointment: {patient_name}",
            start_iso=start_iso,
            description=(
                f"Follow-up appointment for {patient_name}.\n"
                f"Scheduled via MedTrigger workflow."
            ),
            attendee_email=patient.get("email"),
        )
        return True, _step_log(
            node, "ok",
            f"Google Calendar event created — {event.get('htmlLink', '')}",
            extra={
                "calendar_event_id": event.get("id"),
                "calendar_link": event.get("htmlLink"),
            },
        )
    except Exception as exc:
        logger.exception("Google Calendar event creation failed")
        return False, _step_log(node, "error", f"Google Calendar error: {exc}")


async def _handle_send_sms(node: dict, context: dict) -> tuple[bool, dict]:
    patient = context.get("patient", {})
    phone = patient.get("phone")
    data = node.get("data", {})
    body = data.get("params", {}).get(
        "message",
        data.get("message", "You have a message from your healthcare provider."),
    )

    if not phone:
        return False, _step_log(node, "error", "No patient phone number available")

    try:
        from twilio.rest import Client as TwilioClient

        twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = twilio.messages.create(to=phone, from_=settings.twilio_phone_number, body=body)
        return True, _step_log(node, "ok", f"SMS sent: {msg.sid}", extra={"message_sid": msg.sid})
    except Exception as exc:
        logger.exception("Twilio SMS failed")
        return False, _step_log(node, "error", f"Twilio SMS error: {exc}")


async def _handle_send_notification(node: dict, context: dict) -> tuple[bool, dict]:
    """Create a notification record in the database."""
    import app.services.supabase_service as db_svc

    patient = context.get("patient", {})
    patient_id = patient.get("id")
    params = _get_node_params(node)

    message = params.get("message", "Workflow notification")
    recipient = params.get("recipient", "staff")
    priority = params.get("priority", "normal")

    try:
        record = db_svc.create_notification({
            "patient_id": patient_id,
            "recipient": recipient,
            "message": message,
            "priority": priority,
            "status": "unread",
        })
        notification_id = record.get("id", "")
        return True, _step_log(
            node, "ok",
            f"Notification created (priority={priority}): {message[:80]}",
            extra={"notification_id": notification_id},
        )
    except Exception as exc:
        logger.exception("Failed to create notification")
        return False, _step_log(node, "error", f"Notification error: {exc}")


async def _handle_create_lab_order(node: dict, context: dict) -> tuple[bool, dict]:
    """Create a lab order record in the database."""
    import app.services.supabase_service as db_svc

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)
    test_type = params.get("test_type", "General Panel")
    priority = params.get("priority", "routine")
    notes = params.get("notes", "")

    try:
        record = db_svc.create_lab_order({
            "patient_id": patient_id,
            "test_type": test_type,
            "priority": priority,
            "status": "pending",
            "notes": notes or None,
        })
        order_id = record.get("id", "")
        return True, _step_log(
            node, "ok",
            f"Lab order created: {test_type} (priority={priority})",
            extra={"lab_order_id": order_id},
        )
    except Exception as exc:
        logger.exception("Failed to create lab order")
        return False, _step_log(node, "error", f"Lab order error: {exc}")


async def _handle_create_referral(node: dict, context: dict) -> tuple[bool, dict]:
    """Create a specialist referral record in the database."""
    import app.services.supabase_service as db_svc

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)
    specialty = params.get("specialty", "General")
    reason = params.get("reason", "Workflow-generated referral")
    urgency = params.get("urgency", "routine")

    try:
        record = db_svc.create_referral({
            "patient_id": patient_id,
            "specialty": specialty,
            "reason": reason,
            "urgency": urgency,
            "status": "pending",
        })
        referral_id = record.get("id", "")
        return True, _step_log(
            node, "ok",
            f"Referral created: {specialty} (urgency={urgency})",
            extra={"referral_id": referral_id},
        )
    except Exception as exc:
        logger.exception("Failed to create referral")
        return False, _step_log(node, "error", f"Referral error: {exc}")


async def _handle_update_patient_record(node: dict, context: dict) -> tuple[bool, dict]:
    """Update patient record fields based on node params."""
    import app.services.supabase_service as db_svc

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)

    ALLOWED_FIELDS = {
        "name", "phone", "dob", "mrn", "insurance",
        "primary_physician", "last_visit", "risk_level", "notes",
    }

    update_payload = {}
    invalid_fields = []
    for key, value in params.items():
        if key in ALLOWED_FIELDS and value:
            update_payload[key] = value
        elif key not in ALLOWED_FIELDS and value:
            invalid_fields.append(key)

    if invalid_fields:
        return False, _step_log(
            node, "error",
            f"Invalid patient fields: {', '.join(invalid_fields)}",
        )

    if not update_payload:
        return True, _step_log(node, "ok", "No fields to update")

    try:
        db_svc.update_patient(patient_id, update_payload)
        updated_fields = list(update_payload.keys())
        context["patient"].update(update_payload)
        return True, _step_log(
            node, "ok",
            f"Patient record updated: {', '.join(updated_fields)}",
            extra={"updated_fields": updated_fields},
        )
    except Exception as exc:
        logger.exception("Failed to update patient record")
        return False, _step_log(node, "error", f"Patient update error: {exc}")


async def _handle_assign_to_staff(node: dict, context: dict) -> tuple[bool, dict]:
    """Create a staff assignment record."""
    import app.services.supabase_service as db_svc

    patient_id = context.get("patient", {}).get("id")
    if not patient_id:
        return False, _step_log(node, "error", "No patient_id in context")

    params = _get_node_params(node)
    staff_id = params.get("staff_id", "")
    task_type = params.get("task_type", "follow_up")
    due_date = params.get("due_date")

    if not staff_id:
        return False, _step_log(node, "error", "No staff_id configured")

    payload: dict[str, Any] = {
        "patient_id": patient_id,
        "staff_id": staff_id,
        "task_type": task_type,
        "status": "assigned",
    }
    if due_date:
        payload["due_date"] = due_date

    try:
        record = db_svc.create_staff_assignment(payload)
        assignment_id = record.get("id", "")
        return True, _step_log(
            node, "ok",
            f"Assigned to staff {staff_id}: {task_type}",
            extra={"assignment_id": assignment_id},
        )
    except Exception as exc:
        logger.exception("Failed to create staff assignment")
        return False, _step_log(node, "error", f"Staff assignment error: {exc}")


async def _handle_generic_action(node: dict, context: dict) -> tuple[bool, dict]:
    """Fallback handler for unrecognized action types."""
    data = node.get("data", {})
    label = data.get("label", node.get("type", "unknown"))
    return True, _step_log(node, "ok", f"Action '{label}' recorded (handler not found)")


# ---------------------------------------------------------------------------
# Output handlers
# ---------------------------------------------------------------------------

async def _handle_log_completion(node: dict, context: dict) -> tuple[bool, dict]:
    return True, _step_log(node, "ok", "Workflow completed successfully")


async def _handle_generate_transcript(node: dict, context: dict) -> tuple[bool, dict]:
    """Fetch and store conversation transcript from ElevenLabs."""
    from app.services.elevenlabs_service import get_conversation
    import app.services.supabase_service as db_svc

    conversation_id = context.get("conversation_id")
    if not conversation_id:
        return False, _step_log(node, "error", "No conversation_id — call may not have completed yet")

    try:
        conversation = await get_conversation(conversation_id)
    except Exception as exc:
        logger.exception("Failed to fetch transcript from ElevenLabs")
        return False, _step_log(node, "error", f"ElevenLabs API error: {exc}")

    transcript = conversation.get("transcript", "")
    if isinstance(transcript, list):
        formatted_lines = []
        for entry in transcript:
            role = entry.get("role", "unknown")
            text = entry.get("message", entry.get("text", ""))
            ts = entry.get("time_in_call_secs", "")
            prefix = f"[{ts}s] " if ts else ""
            formatted_lines.append(f"{prefix}{role}: {text}")
        formatted_transcript = "\n".join(formatted_lines)
    elif isinstance(transcript, str):
        formatted_transcript = transcript
    else:
        formatted_transcript = str(transcript)

    call_log_id = context.get("call_log_id")
    if call_log_id:
        try:
            existing = db_svc.get_call_log(call_log_id)
            exec_log = existing.get("execution_log") or [] if existing else []
            exec_log.append({
                "node_id": node.get("id"),
                "node_type": "transcript",
                "transcript": formatted_transcript[:10000],
            })
            db_svc.update_call_log(call_log_id, {"execution_log": exec_log})
        except Exception:
            pass

    preview = formatted_transcript[:200] + ("..." if len(formatted_transcript) > 200 else "")
    return True, _step_log(
        node, "ok",
        f"Transcript generated ({len(formatted_transcript)} chars)",
        extra={"transcript_length": len(formatted_transcript), "preview": preview},
    )


async def _handle_create_report(node: dict, context: dict) -> tuple[bool, dict]:
    """Generate and store a structured execution report."""
    import app.services.supabase_service as db_svc

    patient = context.get("patient", {})
    execution_log = context.get("_execution_log", [])

    report_data = {
        "workflow_id": context.get("workflow_id"),
        "workflow_name": context.get("workflow_name", "Unknown"),
        "patient_name": patient.get("name", "Unknown"),
        "patient_id": patient.get("id"),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "node_results": [
            {
                "node_id": step.get("node_id"),
                "node_type": step.get("node_type"),
                "label": step.get("label"),
                "status": step.get("status"),
                "message": step.get("message"),
            }
            for step in execution_log
        ],
        "total_nodes": len(execution_log),
        "successful": sum(1 for s in execution_log if s.get("status") == "ok"),
        "failed": sum(1 for s in execution_log if s.get("status") == "error"),
        "skipped": sum(1 for s in execution_log if s.get("status") == "skipped"),
    }

    try:
        record = db_svc.create_report({
            "workflow_id": context.get("workflow_id"),
            "patient_id": patient.get("id"),
            "call_log_id": context.get("call_log_id"),
            "report_data": report_data,
        })
        report_id = record.get("id", "")
        return True, _step_log(
            node, "ok",
            f"Report generated: {report_data['successful']}/{report_data['total_nodes']} nodes succeeded",
            extra={"report_id": report_id},
        )
    except Exception as exc:
        logger.exception("Failed to create report")
        return False, _step_log(node, "error", f"Report creation error: {exc}")


async def _handle_send_summary_to_doctor(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Compile and send workflow summary to the doctor.
    In production this would send via email (SendGrid/SMTP).
    Currently stores the summary in a notification record for the doctor.
    """
    import app.services.supabase_service as db_svc

    doctor_id = context.get("doctor_id")
    patient = context.get("patient", {})
    execution_log = context.get("_execution_log", [])

    if not doctor_id:
        return False, _step_log(node, "error", "No doctor_id in context")

    ok_count = sum(1 for s in execution_log if s.get("status") == "ok")
    err_count = sum(1 for s in execution_log if s.get("status") == "error")
    total = len(execution_log)

    summary = (
        f"Workflow Summary for patient {patient.get('name', 'Unknown')}:\n"
        f"- Workflow: {context.get('workflow_name', 'N/A')}\n"
        f"- Nodes executed: {total} ({ok_count} ok, {err_count} errors)\n"
        f"- Key events:\n"
    )
    for step in execution_log:
        if step.get("status") in ("ok", "error"):
            summary += f"  [{step.get('status').upper()}] {step.get('label', '')}: {step.get('message', '')}\n"

    try:
        db_svc.create_notification({
            "patient_id": patient.get("id"),
            "recipient": doctor_id,
            "message": summary,
            "priority": "normal" if err_count == 0 else "urgent",
            "status": "unread",
        })

        return True, _step_log(
            node, "ok",
            f"Summary sent to doctor ({total} nodes, {err_count} errors)",
            extra={"doctor_id": doctor_id, "summary_length": len(summary)},
        )
    except Exception as exc:
        logger.exception("Failed to send summary to doctor")
        return False, _step_log(node, "error", f"Summary delivery error: {exc}")


_OUTPUT_HANDLERS: dict[str, Any] = {
    "log_completion": _handle_log_completion,
    "generate_transcript": _handle_generate_transcript,
    "create_report": _handle_create_report,
    "send_summary_to_doctor": _handle_send_summary_to_doctor,
}


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_ACTION_HANDLERS: dict[str, Any] = {
    "call_patient": _handle_call_patient,
    "send_sms": _handle_send_sms,
    "schedule_appointment": _handle_schedule_appointment,
    "send_notification": _handle_send_notification,
    "create_lab_order": _handle_create_lab_order,
    "create_referral": _handle_create_referral,
    "update_patient_record": _handle_update_patient_record,
    "assign_to_staff": _handle_assign_to_staff,
}


async def _dispatch(node: dict, context: dict) -> tuple[bool, dict]:
    node_type = (node.get("data", {}).get("nodeType", "") or node.get("type", "")).lower()

    if node_type in TRIGGER_TYPES:
        return await _handle_trigger(node, context)

    if node_type in CONDITION_TYPES:
        handler = _CONDITION_HANDLERS.get(node_type)
        if handler:
            return await handler(node, context)
        return False, _step_log(node, "error", f"No handler for condition '{node_type}'")

    if node_type in OUTPUT_TYPES:
        handler = _OUTPUT_HANDLERS.get(node_type)
        if handler:
            return await handler(node, context)
        return True, _step_log(node, "ok", f"Output '{node_type}' logged")

    if node_type in ACTION_TYPES:
        handler = _ACTION_HANDLERS.get(node_type, _handle_generic_action)
        return await handler(node, context)

    return True, _step_log(node, "skipped", f"Unknown node type '{node_type}' — skipped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def execute_workflow(
    workflow: dict,
    patient: dict,
    trigger_node_type: str | None = None,
    call_log_id: str | None = None,
    doctor_id: str | None = None,
    lab_results: list[dict] | None = None,
    metadata: dict | None = None,
) -> list[dict]:
    """
    Execute a workflow for a given patient.

    Args:
        workflow: Row from the `workflows` table (must have `nodes` and `edges` keys).
        patient:  Row from the `patients` table.
        trigger_node_type: Optional type string to filter which trigger to use.
        call_log_id: ID of the call_log row so callbacks can update it.
        doctor_id: Auth0 ``user.sub`` of the doctor (needed for Google Calendar).
        lab_results: Optional lab results (from PDF extraction or trigger metadata).
        metadata: Optional extra metadata from the triggering event.

    Returns:
        A list of step-log dicts (suitable for storing as execution_log JSONB).
    """
    nodes: list[dict] = workflow.get("nodes") or []
    edges: list[dict] = workflow.get("edges") or []

    if not nodes:
        return [{"status": "error", "message": "Workflow has no nodes"}]

    nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}
    adj_simple = _build_adjacency(edges)
    adj_with_handles = _build_adjacency_with_handles(edges)

    trigger = _find_trigger_node(nodes)
    if not trigger:
        return [{"status": "error", "message": "No trigger node found in workflow"}]

    context: dict = {
        "patient": patient,
        "call_log_id": call_log_id,
        "workflow_id": workflow.get("id"),
        "workflow_name": workflow.get("name", "Unknown"),
        "doctor_id": doctor_id or workflow.get("doctor_id"),
        "doctor_name": workflow.get("doctor_name", "your doctor"),
        "lab_results": lab_results or [],
        "metadata": metadata or {},
    }

    execution_log: list[dict] = []
    visited: set[str] = set()
    queue: list[str] = [trigger["id"]]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        node = nodes_by_id.get(current_id)
        if not node:
            continue

        context["_execution_log"] = execution_log

        ok, step = await _dispatch(node, context)
        execution_log.append(step)

        node_type = (node.get("data", {}).get("nodeType", "") or node.get("type", "")).lower()

        condition_passed: bool | None = None
        if node_type in CONDITION_TYPES:
            condition_passed = ok

        successors = _get_successors(
            current_id,
            node_type,
            condition_passed,
            adj_with_handles,
            adj_simple,
        )

        for neighbor in successors:
            if neighbor not in visited:
                queue.append(neighbor)

    return execution_log
