"""
Workflow Execution Engine
--------------------------
Takes a saved workflow's nodes[] and edges[] (React Flow format),
walks the graph in topological order starting from the trigger node,
and dispatches each node type to its handler.

Returns a list of step-log dicts that gets stored in call_logs.execution_log.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node type constants (must match frontend node `type` field)
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
        node_type = node.get("type") or node.get("data", {}).get("nodeType", "")
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
        "node_type": node.get("type") or data.get("nodeType"),
        "label": data.get("label", ""),
        "status": status,          # "ok" | "skipped" | "error"
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }


def _handle_trigger(node: dict, context: dict) -> tuple[bool, dict]:
    """Trigger nodes are always the entry point — mark them as ok."""
    return True, _step_log(node, "ok", "Trigger fired")


def _handle_condition(node: dict, context: dict) -> tuple[bool, dict]:
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


def _handle_call_patient(node: dict, context: dict) -> tuple[bool, dict]:
    """
    Places a Twilio outbound call.
    Requires: context['patient_phone'], context['call_log_id'], settings.twilio_*
    """
    patient = context.get("patient", {})
    phone = patient.get("phone")
    call_log_id = context.get("call_log_id")

    if not phone:
        return False, _step_log(node, "error", "No patient phone number available")

    try:
        from twilio.rest import Client as TwilioClient  # type: ignore

        twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        twiml_url = f"{settings.app_base_url}/api/twilio/voice?log_id={call_log_id}"
        call = twilio.calls.create(
            to=phone,
            from_=settings.twilio_phone_number,
            url=twiml_url,
        )
        return True, _step_log(
            node, "ok", f"Twilio call initiated: {call.sid}",
            extra={"call_sid": call.sid},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Twilio call failed")
        return False, _step_log(node, "error", f"Twilio error: {exc}")


def _handle_send_sms(node: dict, context: dict) -> tuple[bool, dict]:
    patient = context.get("patient", {})
    phone = patient.get("phone")
    data = node.get("data", {})
    body = data.get("message", "You have a message from your healthcare provider.")

    if not phone:
        return False, _step_log(node, "error", "No patient phone number available")

    try:
        from twilio.rest import Client as TwilioClient  # type: ignore

        twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = twilio.messages.create(to=phone, from_=settings.twilio_phone_number, body=body)
        return True, _step_log(node, "ok", f"SMS sent: {msg.sid}", extra={"message_sid": msg.sid})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Twilio SMS failed")
        return False, _step_log(node, "error", f"Twilio SMS error: {exc}")


def _handle_generic_action(node: dict, context: dict) -> tuple[bool, dict]:
    """Placeholder handler for actions that aren't yet wired (schedule appt, lab order, etc.)."""
    data = node.get("data", {})
    label = data.get("label", node.get("type", "unknown"))
    return True, _step_log(node, "ok", f"Action '{label}' recorded (not yet wired)")


def _handle_output(node: dict, context: dict) -> tuple[bool, dict]:
    data = node.get("data", {})
    label = data.get("label", node.get("type", "output"))
    return True, _step_log(node, "ok", f"Output '{label}' logged")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_ACTION_HANDLERS: dict[str, Any] = {
    "call_patient": _handle_call_patient,
    "send_sms": _handle_send_sms,
}


def _dispatch(node: dict, context: dict) -> tuple[bool, dict]:
    node_type = (node.get("type") or node.get("data", {}).get("nodeType", "")).lower()

    if node_type in TRIGGER_TYPES:
        return _handle_trigger(node, context)
    if node_type in CONDITION_TYPES:
        return _handle_condition(node, context)
    if node_type in OUTPUT_TYPES:
        return _handle_output(node, context)
    if node_type in ACTION_TYPES:
        handler = _ACTION_HANDLERS.get(node_type, _handle_generic_action)
        return handler(node, context)

    # Unknown node — log and continue
    return True, _step_log(node, "skipped", f"Unknown node type '{node_type}' — skipped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_workflow(
    workflow: dict,
    patient: dict,
    trigger_node_type: str | None = None,
    call_log_id: str | None = None,
) -> list[dict]:
    """
    Execute a workflow for a given patient.

    Args:
        workflow: Row from the `workflows` table (must have `nodes` and `edges` keys).
        patient:  Row from the `patients` table.
        trigger_node_type: Optional type string to filter which trigger to use.
        call_log_id: ID of the call_log row so Twilio callbacks can update it.

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
    }

    execution_log: list[dict] = []
    active = True  # If a condition fails we stop following that branch

    for node in ordered_nodes:
        if not active:
            execution_log.append(_step_log(node, "skipped", "Skipped — previous condition not met"))
            continue

        ok, step = _dispatch(node, context)
        execution_log.append(step)

        node_type = (node.get("type") or node.get("data", {}).get("nodeType", "")).lower()
        # If a condition failed, stop the pipeline
        if node_type in CONDITION_TYPES and not ok:
            active = False

    return execution_log
