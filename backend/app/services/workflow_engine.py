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
from datetime import datetime, timezone
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
    """Return {source_node_id: [target_node_id, ...]}."""
    adj: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)
    return adj


def _find_trigger_node(nodes: list[dict]) -> dict | None:
    """Return the first node whose type is a trigger type."""
    for node in nodes:
        # data.nodeType holds the engine dispatch key; node["type"] is the
        # React Flow rendering type ("trigger", "action", …) and must NOT
        # take precedence.
        node_type = node.get("data", {}).get("nodeType", "") or node.get("type", "")
        if node_type in TRIGGER_TYPES:
            return node
    return None


def _topological_walk(
    start_id: str, nodes_by_id: dict[str, dict], adj: dict[str, list[str]]
) -> list[dict]:
    """BFS from the trigger node, returns nodes in execution order."""
    visited: set[str] = set()
    queue: list[str] = [start_id]
    order: list[dict] = []
    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)
        node = nodes_by_id.get(current_id)
        if node:
            order.append(node)
        for neighbor in adj.get(current_id, []):
            if neighbor not in visited:
                queue.append(neighbor)
    return order


# ---------------------------------------------------------------------------
# Node handlers
# ---------------------------------------------------------------------------

def _step_log(node: dict, status: str, message: str, extra: dict | None = None) -> dict:
    data = node.get("data", {})
    return {
        "node_id": node.get("id"),
        "node_type": data.get("nodeType") or node.get("type"),
        "label": data.get("label", ""),
        "status": status,          # "ok" | "skipped" | "error"
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }


async def _handle_trigger(node: dict, context: dict) -> tuple[bool, dict]:
    """Trigger nodes are always the entry point — mark them as ok."""
    return True, _step_log(node, "ok", "Trigger fired")


async def _handle_condition(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Condition nodes evaluate a simple check.
    For now, all conditions pass (true branch) unless data.result == 'false'.
    The frontend can store `data.result` when configuring the node.
    """
    data = node.get("data", {})
    result = data.get("result", "true")
    passed = str(result).lower() not in ("false", "0", "no", "fail")
    status = "ok" if passed else "skipped"
    return passed, _step_log(node, status, f"Condition evaluated: {'PASS' if passed else 'FAIL'}")


async def _handle_call_patient(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Initiates an outbound call via ElevenLabs Conversational AI + Twilio.

    ElevenLabs manages the full AI voice conversation with the patient
    (informing them about lab results, scheduling an appointment, etc.).
    The conversation outcome is delivered later via the ElevenLabs webhook.
    """
    from app.services.elevenlabs_service import initiate_outbound_call

    patient = context.get("patient", {})
    phone = patient.get("phone")
    patient_name = patient.get("name", "Patient")
    doctor_name = context.get("doctor_name", "your doctor")
    call_log_id = context.get("call_log_id")

    if not phone:
        return False, _step_log(node, "error", "No patient phone number available")

    # Extra context the ElevenLabs agent can reference during the call
    node_data = node.get("data", {})
    params = node_data.get("params", {})
    lab_summary = params.get("lab_result_summary", "Your recent lab results are ready.")
    facility_name = params.get("facility_name", "")
    facility_address = params.get("facility_address", "")
    call_reason = params.get("call_reason", "")

    try:
        result = await initiate_outbound_call(
            patient_phone=phone,
            patient_name=patient_name,
            doctor_name=doctor_name,
            lab_result_summary=lab_summary,
            facility_name=facility_name,
            facility_address=facility_address,
            call_reason=call_reason,
            extra_context={
                "call_log_id": call_log_id or "",
                "workflow_id": context.get("workflow_id", ""),
            },
        )
        conversation_id = result.get("conversation_id", "")

        # Store the conversation_id in context so downstream nodes can use it
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
    """
    Creates a Google Calendar event for the appointment.

    The appointment details are expected in `context["appointment"]` (set by
    the ElevenLabs webhook when the patient confirms).  If no appointment
    data is present yet (because the call hasn't finished), this node logs
    that the appointment will be scheduled after the call completes.
    """
    from app.services.google_calendar_service import create_calendar_event

    patient = context.get("patient", {})
    patient_name = patient.get("name", "Patient")
    doctor_id = context.get("doctor_id")  # Auth0 user.sub
    appointment = context.get("appointment", {})

    # If we don't have appointment details yet (call still in progress),
    # the webhook will handle scheduling when the call ends.
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
            "No doctor_id (Auth0 sub) in context — cannot access Google Calendar",
        )

    confirmed_date = appointment["confirmed_date"]  # e.g. "2026-03-10"
    confirmed_time = appointment.get("confirmed_time", "09:00")  # e.g. "14:00"
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
    """Send a notification (placeholder — logs the intent)."""
    data = node.get("data", {})
    params = data.get("params", {})
    message = params.get("message", "Notification sent.")
    return True, _step_log(node, "ok", f"Notification: {message}")


async def _handle_generic_action(node: dict, context: dict) -> tuple[bool, dict]:
    """Placeholder handler for actions that aren't yet wired."""
    data = node.get("data", {})
    label = data.get("label", node.get("type", "unknown"))
    return True, _step_log(node, "ok", f"Action '{label}' recorded (not yet wired)")


async def _handle_output(node: dict, context: dict) -> tuple[bool, dict]:
    data = node.get("data", {})
    label = data.get("label", node.get("type", "output"))
    return True, _step_log(node, "ok", f"Output '{label}' logged")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_ACTION_HANDLERS: dict[str, Any] = {
    "call_patient": _handle_call_patient,
    "send_sms": _handle_send_sms,
    "schedule_appointment": _handle_schedule_appointment,
    "send_notification": _handle_send_notification,
}


async def _dispatch(node: dict, context: dict) -> tuple[bool, dict]:
    node_type = (node.get("data", {}).get("nodeType", "") or node.get("type", "")).lower()

    if node_type in TRIGGER_TYPES:
        return await _handle_trigger(node, context)
    if node_type in CONDITION_TYPES:
        return await _handle_condition(node, context)
    if node_type in OUTPUT_TYPES:
        return await _handle_output(node, context)
    if node_type in ACTION_TYPES:
        handler = _ACTION_HANDLERS.get(node_type, _handle_generic_action)
        return await handler(node, context)

    # Unknown node — log and continue
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
) -> list[dict]:
    """
    Execute a workflow for a given patient.

    Args:
        workflow: Row from the `workflows` table (must have `nodes` and `edges` keys).
        patient:  Row from the `patients` table.
        trigger_node_type: Optional type string to filter which trigger to use.
        call_log_id: ID of the call_log row so callbacks can update it.
        doctor_id: Auth0 ``user.sub`` of the doctor (needed for Google Calendar).

    Returns:
        A list of step-log dicts (suitable for storing as execution_log JSONB).
    """
    nodes: list[dict] = workflow.get("nodes") or []
    edges: list[dict] = workflow.get("edges") or []

    if not nodes:
        return [{"status": "error", "message": "Workflow has no nodes"}]

    # Build lookup
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}
    adj = _build_adjacency(edges)

    # Find trigger
    trigger = _find_trigger_node(nodes)
    if not trigger:
        return [{"status": "error", "message": "No trigger node found in workflow"}]

    # Walk the graph
    ordered_nodes = _topological_walk(trigger["id"], nodes_by_id, adj)

    context: dict = {
        "patient": patient,
        "call_log_id": call_log_id,
        "workflow_id": workflow.get("id"),
        "doctor_id": doctor_id or workflow.get("doctor_id"),
        "doctor_name": workflow.get("doctor_name", "your doctor"),
    }

    execution_log: list[dict] = []
    active = True  # If a condition fails we stop following that branch

    for node in ordered_nodes:
        if not active:
            execution_log.append(_step_log(node, "skipped", "Skipped — previous condition not met"))
            continue

        ok, step = await _dispatch(node, context)
        execution_log.append(step)

        node_type = (node.get("data", {}).get("nodeType", "") or node.get("type", "")).lower()
        # If a condition failed, stop the pipeline
        if node_type in CONDITION_TYPES and not ok:
            active = False

    return execution_log
