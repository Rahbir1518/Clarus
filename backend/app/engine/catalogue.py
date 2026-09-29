"""Which node types exist, and what category each one is.

This is the backend half of a contract. The frontend half is
`frontend/components/workflow/types.ts`, whose header says a node's
`data.nodeType` must match one of TRIGGER_TYPES, ACTION_TYPES, CONDITION_TYPES
or OUTPUT_TYPES — these four sets, by these names.

Category is derived from the node type here rather than read from the node's
React Flow `type` field, and the difference matters. `type` is what the builder
renders with; a saved graph could carry `type: "action"` on a node whose
`nodeType` is a trigger, either through a builder bug or because someone edited
the JSON. Deciding "is this a trigger" from presentation would let that decide
what the engine does. The dispatch key is the only input.

A node type absent from all four sets is a hard error at parse time, not a
skipped step. An unrecognised node in a graph that is about to phone a patient
means the graph is not the graph its author thinks it is.
"""
from __future__ import annotations

from typing import Final

TRIGGER_TYPES: Final[frozenset[str]] = frozenset(
    {
        "lab_results_received",
        "abnormal_result_detected",
        "follow_up_due",
        "appointment_missed",
        "new_patient_registered",
        "prescription_expiring",
    }
)

ACTION_TYPES: Final[frozenset[str]] = frozenset(
    {
        "call_patient",
        "send_sms",
        "schedule_appointment",
        "send_notification",
        "create_lab_order",
        "create_referral",
        "update_patient_record",
        "assign_to_staff",
    }
)

CONDITION_TYPES: Final[frozenset[str]] = frozenset(
    {
        "check_result_values",
        "check_insurance",
        "check_patient_age",
        "check_appointment_history",
        "check_medication_list",
    }
)

OUTPUT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "log_completion",
        "generate_transcript",
        "create_report",
        "send_summary_to_doctor",
    }
)

TRIGGER: Final[str] = "trigger"
ACTION: Final[str] = "action"
CONDITION: Final[str] = "condition"
OUTPUT: Final[str] = "output"

_CATEGORIES: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    (TRIGGER, TRIGGER_TYPES),
    (ACTION, ACTION_TYPES),
    (CONDITION, CONDITION_TYPES),
    (OUTPUT, OUTPUT_TYPES),
)

ALL_NODE_TYPES: Final[frozenset[str]] = frozenset(
    node_type for _, types in _CATEGORIES for node_type in types
)


def category_of(node_type: str) -> str | None:
    """The category a dispatch key belongs to, or None if it is unknown."""
    for category, types in _CATEGORIES:
        if node_type in types:
            return category
    return None
