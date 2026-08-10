"""One handler per node type.

A handler takes the run context and its node, does one thing, and returns an
`Outcome`. It does not decide what runs next — that is the walk in runner.py —
and it does not write to the execution log directly, so that every step is
recorded the same way whether it succeeded, refused, or raised.

Three rules hold across all of them:

1. **A handler that cannot do its job returns `failed` or `blocked`, and the
   branch stops.** Nothing returns `ok` on the strength of having tried. The
   failure this prevents is named in REBUILD_CHECKLIST.md: "generate transcript"
   and "send summary" running after a call that never connected.

2. **A missing input is not a false.** A conditional that cannot find the value
   it needs blocks rather than taking its false branch. There is no safe default
   for "I do not know", so there is no default.

3. **`raise PolicyRefusal` rather than returning blocked** where a safety rule
   is the reason. The runner converts it, and keeping the raise means a handler
   cannot accidentally continue past a refusal.

`_registry_is_complete` at the foot of the module asserts every dispatch key in
catalogue.py has a handler, at import time. A node type added to the catalogue
without one fails the boot rather than a run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Final

from app.engine import policy
from app.engine.catalogue import ALL_NODE_TYPES
from app.engine.context import RunContext
from app.engine.graph import FALSE_BRANCH, TRUE_BRANCH, Node
from app.engine.policy import PolicyRefusal
from app.engine.steps import BLOCKED, FAILED, OK, PARKED, SKIPPED
from app.integrations.elevenlabs.client import ElevenLabsClient, ElevenLabsError
from app.integrations.elevenlabs.variables import build_dynamic_variables

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outcome:
    status: str
    message: str
    branch: str | None = None
    entity: dict[str, str] | None = None


def ok(message: str, *, entity: dict[str, str] | None = None) -> Outcome:
    return Outcome(OK, message, entity=entity)


def branched(message: str, *, taken: bool) -> Outcome:
    return Outcome(OK, message, branch=TRUE_BRANCH if taken else FALSE_BRANCH)


def skipped(message: str) -> Outcome:
    return Outcome(SKIPPED, message)


def failed(message: str) -> Outcome:
    return Outcome(FAILED, message)


def blocked(message: str) -> Outcome:
    return Outcome(BLOCKED, message)


Handler = Callable[[RunContext, Node], Outcome]


# ---------------------------------------------------------------------------
# Shared parameter handling
# ---------------------------------------------------------------------------


def _required(node: Node, name: str) -> str:
    value = node.param(name)
    if not value:
        raise _MissingParam(
            f"Parameter {name!r} is required on a {node.node_type} node and is empty."
        )
    return value


class _MissingParam(Exception):
    """A node is missing a parameter it cannot work without.

    Its own exception rather than an early return so that reading a handler
    shows what it does, not what it checks. The runner turns this into a
    `blocked` step: an incomplete node is the workflow being unfinished, which
    is a question for its author, not a system failure.
    """


def _one_of(node: Node, name: str, allowed: set[str], default: str) -> str:
    """A parameter constrained by a database CHECK, validated before the write.

    Without this a bad value is a 500 from Postgres naming a constraint, which
    tells the workflow's author nothing they can act on.
    """
    value = node.param(name) or default
    if value not in allowed:
        raise _MissingParam(
            f"Parameter {name}={value!r} is not one of "
            f"{', '.join(sorted(allowed))}."
        )
    return value


def _numeric(node: Node, name: str) -> float:
    raw = _required(node, name)
    try:
        return float(raw)
    except ValueError:
        raise _MissingParam(
            f"Parameter {name}={raw!r} on a {node.node_type} node is not a number."
        ) from None


# Operator names as the builder's own dropdown writes them, in
# frontend/components/workflow/PropertiesPanel.tsx. The aliases are for graphs
# drawn by hand or by an earlier version of that list.
_NEEDS_MAX: Final[frozenset[str]] = frozenset(
    {"between", "in_range", "out_of_range"}
)
_OPERATOR_ALIASES: Final[dict[str, str]] = {
    "equals": "equal_to",
    "eq": "equal_to",
    "gt": "greater_than",
    "lt": "less_than",
    "greater_than_or_equal": "at_least",
    "gte": "at_least",
    "less_than_or_equal": "at_most",
    "lte": "at_most",
}


def _compare(node: Node, value: float) -> tuple[bool, str]:
    """Evaluate `value` against the node's operator and thresholds.

    Returns the result and a phrase describing the comparison, so the execution
    log records why a branch was taken rather than only which one.
    """
    operator = node.param("operator") or "greater_than"
    operator = _OPERATOR_ALIASES.get(operator, operator)
    threshold = _numeric(node, "threshold")
    maximum = _numeric(node, "threshold_max") if operator in _NEEDS_MAX else None

    if operator == "greater_than":
        return value > threshold, f"{value:g} > {threshold:g}"
    if operator == "at_least":
        return value >= threshold, f"{value:g} >= {threshold:g}"
    if operator == "less_than":
        return value < threshold, f"{value:g} < {threshold:g}"
    if operator == "at_most":
        return value <= threshold, f"{value:g} <= {threshold:g}"
    if operator == "equal_to":
        return value == threshold, f"{value:g} == {threshold:g}"
    if operator in {"between", "in_range"}:
        assert maximum is not None
        return (
            threshold <= value <= maximum,
            f"{threshold:g} <= {value:g} <= {maximum:g}",
        )
    if operator == "out_of_range":
        assert maximum is not None
        return (
            value < threshold or value > maximum,
            f"{value:g} outside {threshold:g}–{maximum:g}",
        )
    raise _MissingParam(f"Unknown operator {operator!r}.")


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

# A trigger does no work. It is the entry point the walk starts from, and its
# step exists so the log says which event began the run — which matters when a
# workflow has several triggers and only one of them fired.
_ABNORMAL_TRIGGER: Final[str] = "abnormal_result_detected"


def _trigger(ctx: RunContext, node: Node) -> Outcome:
    if node.node_type == _ABNORMAL_TRIGGER:
        ctx.taint_abnormal("the abnormal_result_detected trigger fired")
        ctx.require_review("an abnormal result started this run")
        return ok(
            "Abnormal result trigger. This run is routed to a human; no "
            "automated call will be placed on it."
        )

    values = ctx.lab_values
    if values:
        detail = ", ".join(f"{name} {value:g}" for name, value in sorted(values.items()))
        return ok(f"Triggered with {len(values)} value(s): {detail}")
    return ok("Triggered")


# ---------------------------------------------------------------------------
# Conditionals
# ---------------------------------------------------------------------------

# Which branch of a threshold node its author considers the abnormal one.
# Defaults to "true" — the branch where the threshold is met — because that is
# how these graphs are drawn, and because the two failure directions are not
# equally bad. Defaulting the other way would place automated calls on abnormal
# paths until somebody noticed. `none` opts out for a node whose comparison is
# not clinical.
_ABNORMAL_BRANCH_PARAM: Final[str] = "abnormal_branch"


def _check_result_values(ctx: RunContext, node: Node) -> Outcome:
    test_name = _required(node, "test_name")
    value = ctx.lab_value(test_name)

    if value is None:
        available = ", ".join(sorted(ctx.lab_values)) or "none"
        ctx.require_review(f"no value for {test_name} was available to evaluate")
        # Not the false branch. An absent value read as a negative is how a
        # system decides a result is normal because it could not find it.
        return blocked(
            f"No numeric value for {test_name!r} in the triggering event, so this "
            f"condition cannot be evaluated. Values received: {available}."
        )

    result, description = _compare(node, value)
    branch = TRUE_BRANCH if result else FALSE_BRANCH

    abnormal_branch = node.param(_ABNORMAL_BRANCH_PARAM) or TRUE_BRANCH
    if abnormal_branch == branch:
        ctx.taint_abnormal(f"{test_name} {description} on the abnormal branch")
        ctx.require_review(f"{test_name} was {description}")
        return Outcome(
            OK,
            f"{test_name}: {description} — took the {branch} branch, which this "
            f"node marks abnormal. Routed to a human.",
            branch=branch,
        )

    return Outcome(
        OK, f"{test_name}: {description} — took the {branch} branch", branch=branch
    )


def _check_patient_age(ctx: RunContext, node: Node) -> Outcome:
    age = ctx.patient_age()
    if age is None:
        ctx.require_review("the patient has no date of birth on record")
        return blocked(
            "The patient has no date of birth recorded, so an age condition "
            "cannot be evaluated."
        )
    result, description = _compare(node, float(age))
    return branched(f"Age {age}: {description}", taken=result)


def _check_insurance(ctx: RunContext, node: Node) -> Outcome:
    insurance = str(ctx.patient.get("insurance") or "").strip()
    wanted = node.param("insurance_type") or "any"

    if wanted.lower() == "any":
        return branched(
            f"Insurance on record: {insurance or 'none'}", taken=bool(insurance)
        )
    matched = wanted.lower() in insurance.lower()
    return branched(
        f"Insurance {insurance or 'none'} "
        f"{'matches' if matched else 'does not match'} {wanted!r}",
        taken=matched,
    )


def _check_appointment_history(ctx: RunContext, node: Node) -> Outcome:
    days = int(_numeric(node, "days_since_last"))
    elapsed = ctx.days_since_last_appointment()
    if elapsed is None:
        # Never seen is unambiguously "longer ago than N days", so this one does
        # have a safe answer, unlike an absent lab value.
        return branched(
            f"No appointment or visit on record, which is longer ago than {days} days",
            taken=True,
        )
    return branched(
        f"Last appointment was {elapsed} day(s) ago, threshold {days}",
        taken=elapsed >= days,
    )


def _check_medication_list(ctx: RunContext, node: Node) -> Outcome:
    wanted = [
        term.strip().lower()
        for term in _required(node, "medication").split(",")
        if term.strip()
    ]
    if not wanted:
        raise _MissingParam("Parameter 'medication' lists no medication names.")

    active = ctx.active_medications()
    hits = sorted(
        {
            str(row.get("name"))
            for row in active
            for term in wanted
            if term in str(row.get("name") or "").lower()
        }
    )
    if hits:
        return branched(f"Patient is taking {', '.join(hits)}", taken=True)
    return branched(
        f"None of {', '.join(wanted)} found among {len(active)} active medication(s)",
        taken=False,
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _call_patient(ctx: RunContext, node: Node) -> Outcome:
    """Place the call, then park the run until the webhook completes it.

    The order of the gates is deliberate. Content rules come first, because a
    graph carrying clinical text is wrong whether or not calls happen to be
    switched on today, and its author should hear about that rather than about
    the kill switch. Operational gates follow, cheapest first.

    Nothing here is reached twice in one run. A second call on the same run
    would need a second conversation bound to the same call log, and
    `conversation_id` is write-once under a unique index, so its webhook could
    never be resolved — the outcome would be silently lost. Refused instead.
    """
    if ctx.call_placed:
        return blocked(
            "This run has already placed a call. A second call needs its own "
            "call log to receive an outcome, so it is refused rather than "
            "placed with nowhere to report back to."
        )

    # --- what may be said ---
    policy.assert_no_clinical_params(node.params)
    reason = policy.resolve_call_reason(node.params)
    policy.assert_not_abnormal(abnormal=ctx.abnormal, reason=ctx.abnormal_reason)

    # --- whether to dial ---
    phone = policy.assert_dialable(ctx.patient.get("phone"))
    policy.assert_calls_enabled(ctx.settings)
    policy.assert_number_allowed(phone, ctx.settings)
    policy.assert_within_calling_hours(settings=ctx.settings)
    policy.assert_attempts_available(ctx.recent_call_attempts(), ctx.settings)

    callback = node.param("callback_number") or ctx.settings.practice_callback_number
    if not callback:
        return blocked(
            "No callback number is configured, so a voicemail would ask the "
            "patient to ring back on nothing. Set PRACTICE_CALLBACK_NUMBER or "
            "the node's callback_number."
        )

    variables = build_dynamic_variables(
        patient=ctx.patient,
        appointment_reason=reason,
        callback_number=callback,
        doctor_name=ctx.doctor_display_name(),
        settings=ctx.settings,
    )

    # The run row already exists — runner.py creates it before the walk starts,
    # so a conversation can never exist without somewhere to record its
    # outcome. This moves it to the state that says a call is in flight, and
    # pins the timezone the agent will resolve spoken dates in.
    ctx.scope.update_owned(
        "call_logs",
        ctx.call_log_id,
        {"status": "in_progress", "timezone": ctx.settings.default_timezone},
    )

    try:
        response = ElevenLabsClient().outbound_call(
            to_number=phone, dynamic_variables=variables
        )
    except ElevenLabsError as exc:
        return failed(f"The call was not placed: {exc}")

    conversation_id = str(response.get("conversation_id") or "")
    if not conversation_id:
        # The call may well be ringing. Without an id there is no way to match
        # its webhook, so this is a failure that needs a person.
        ctx.require_review("a call was queued but returned no conversation id")
        return failed(
            "The provider accepted the call but returned no conversation id, so "
            "its outcome cannot be matched to this run."
        )

    try:
        ctx.scope.bind_conversation(ctx.call_log_id, conversation_id)
    except Exception as exc:  # noqa: BLE001 - the call is already in flight
        ctx.require_review("a call was placed but its conversation could not be bound")
        logger.exception(
            "Call placed but binding conversation %s to call log %s failed",
            conversation_id,
            ctx.call_log_id,
        )
        return failed(
            f"The call was placed but its conversation could not be recorded, so "
            f"the outcome will not arrive automatically: {exc}"
        )

    ctx.call_placed = True
    return Outcome(
        PARKED,
        f"Calling {phone} about {reason}. The run resumes when the post-call "
        f"webhook arrives.",
        entity={"table": "call_logs", "id": str(ctx.call_log_id)},
    )


def _send_sms(ctx: RunContext, node: Node) -> Outcome:
    """Not implemented, and loud about it.

    There is no SMS provider in this backend. `app/integrations/` has an
    ElevenLabs client and nothing else, and STATUS.md records that Twilio
    credentials go to ElevenLabs rather than here.

    A logged no-op returning `ok` was the alternative and is worse than useless:
    a workflow whose branch is "text the patient instead of calling" would
    report success while nobody was ever told anything.
    """
    return failed(
        "send_sms is not implemented — this backend has no SMS provider. The "
        "branch stopped here rather than reporting a message nobody received."
    )


def _schedule_appointment(ctx: RunContext, node: Node) -> Outcome:
    """Book the time the patient agreed to on the call.

    Only reachable with a call result, which means only on the resume path.
    Placed before a call in a graph, it has nothing to book and says so — that
    is the "fetching a transcript milliseconds after dialling" failure in a
    different costume.
    """
    result = ctx.call_result
    if result is None:
        return failed(
            "There is no call result to book from. A schedule_appointment node "
            "runs after a call_patient node, on the outcome the webhook brings."
        )

    if not result.is_bookable:
        ctx.require_review("a call finished without a time that could be booked")
        return skipped(
            f"Nothing booked: outcome {result.call_outcome or 'unknown'}, "
            f"confirmed={result.patient_confirmed}, "
            f"date={result.confirmed_date or 'none'}, "
            f"time={result.confirmed_time or 'none'}. Left for a human."
        )

    zone = policy.calling_zone(ctx.settings)
    try:
        starts_at = datetime.fromisoformat(
            f"{result.confirmed_date}T{result.confirmed_time}"
        ).replace(tzinfo=zone)
    except ValueError:
        ctx.require_review("the agreed appointment time could not be parsed")
        return failed(
            f"Could not read {result.confirmed_date!r} at "
            f"{result.confirmed_time!r} as a date and time."
        )

    minutes = int(node.param("duration_minutes") or 30)
    appointment = ctx.scope.insert_owned(
        "appointments",
        {
            "patient_id": ctx.patient.get("id"),
            "workflow_id": ctx.workflow.get("id"),
            "call_log_id": ctx.call_log_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(minutes=minutes)).isoformat(),
            # The patient agreed to this time on a recorded call and confirmed
            # it read back to them, which is what `confirmed` means here.
            "status": "confirmed",
            "location": node.param("location") or None,
            "reason": node.param("reason") or None,
        },
    )
    return ok(
        f"Booked {starts_at.strftime('%Y-%m-%d %H:%M')} "
        f"({ctx.settings.default_timezone}), {minutes} minutes",
        entity={"table": "appointments", "id": str(appointment.get("id"))},
    )


def _send_notification(ctx: RunContext, node: Node) -> Outcome:
    """Tell somebody on the staff.

    Clinical content is allowed here — see the destinations table in
    AI_CALL_SAFETY_POLICY.md. This is an internal row read by the practice, not
    words spoken to a patient.
    """
    row = ctx.scope.insert_for_patient(
        "notifications",
        str(ctx.patient.get("id")),
        {
            "recipient": node.param("recipient") or "staff",
            "message": _required(node, "message"),
            "priority": node.param("priority") or "normal",
        },
    )
    return ok(
        f"Notified {row.get('recipient')} at {row.get('priority')} priority",
        entity={"table": "notifications", "id": str(row.get("id"))},
    )


def _create_lab_order(ctx: RunContext, node: Node) -> Outcome:
    row = ctx.scope.insert_for_patient(
        "lab_orders",
        str(ctx.patient.get("id")),
        {
            "test_type": _required(node, "test_type"),
            "priority": node.param("priority") or "routine",
            "notes": node.param("notes") or None,
        },
    )
    return ok(
        f"Lab order raised for {row.get('test_type')} ({row.get('priority')})",
        entity={"table": "lab_orders", "id": str(row.get("id"))},
    )


def _create_referral(ctx: RunContext, node: Node) -> Outcome:
    row = ctx.scope.insert_for_patient(
        "referrals",
        str(ctx.patient.get("id")),
        {
            "specialty": _required(node, "specialty"),
            "reason": _required(node, "reason"),
            "urgency": _one_of(
                node, "urgency", {"routine", "urgent", "emergent"}, "routine"
            ),
            "target_provider_name": node.param("target_provider_name") or None,
            "target_facility": node.param("target_facility") or None,
            # Attribution comes from the run's own tenant, never a parameter.
            # TenantScope refuses any other value anyway; passing it explicitly
            # is what makes the referral attributable at all.
            "referring_doctor_id": ctx.scope.doctor_id,
        },
    )
    return ok(
        f"Referral raised to {row.get('specialty')} ({row.get('urgency')})",
        entity={"table": "referrals", "id": str(row.get("id"))},
    )


def _assign_to_staff(ctx: RunContext, node: Node) -> Outcome:
    due = node.param("due_date")
    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            raise _MissingParam(
                f"Parameter due_date={due!r} is not a date in YYYY-MM-DD form."
            ) from None

    row = ctx.scope.insert_for_patient(
        "staff_assignments",
        str(ctx.patient.get("id")),
        {
            "staff_id": _required(node, "staff_id"),
            "task_type": node.param("task_type") or "follow_up",
            "due_date": due or None,
        },
    )
    return ok(
        f"Assigned to {row.get('staff_id')} for {row.get('task_type')}",
        entity={"table": "staff_assignments", "id": str(row.get("id"))},
    )


def _update_patient_record(ctx: RunContext, node: Node) -> Outcome:
    """Change the two patient fields a workflow is allowed to touch.

    Notes are appended with a dated line rather than replaced. A workflow
    silently overwriting a clinician's own notes is data loss that nothing
    records, and the node's purpose — "the workflow observed something" — is
    served by adding to them.
    """
    updates: dict[str, Any] = {}
    changed: list[str] = []

    risk = node.param("risk_level")
    if risk:
        if risk not in {"low", "moderate", "high"}:
            raise _MissingParam(
                f"Parameter risk_level={risk!r} is not low, moderate or high."
            )
        updates["risk_level"] = risk
        changed.append(f"risk_level={risk}")

    note = node.param("notes")
    if note:
        existing = str(ctx.patient.get("notes") or "").rstrip()
        stamp = date.today().isoformat()
        line = f"[{stamp}] {note}"
        updates["notes"] = f"{existing}\n{line}" if existing else line
        changed.append("notes appended")

    if not updates:
        return skipped("No fields to update: risk_level and notes are both empty.")

    row = ctx.scope.update_owned("patients", str(ctx.patient.get("id")), updates)
    # Keep the in-memory patient in step, so a later node in the same run reads
    # what was just written rather than what it was called with.
    ctx.patient.update(row)
    return ok(
        f"Patient record updated: {', '.join(changed)}",
        entity={"table": "patients", "id": str(row.get("id"))},
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _log_completion(ctx: RunContext, node: Node) -> Outcome:
    return ok(node.param("message") or "Workflow reached a completion node")


def _generate_transcript(ctx: RunContext, node: Node) -> Outcome:
    """Not implemented, because it should not need to be.

    The transcript arrives with the post-call webhook and is written to
    `call_logs.transcript` there. A node that fetches it separately can only run
    either before the call has finished — the previous system's version fetched
    it milliseconds after dialling, so it could never succeed — or after the
    webhook has already stored it, in which case it is fetching what we have.
    """
    if ctx.call_result is not None and ctx.call_result.transcript:
        return skipped(
            "The transcript arrived with the post-call webhook and is already "
            "stored on this call log; there is nothing to fetch."
        )
    return failed(
        "generate_transcript is not implemented. A transcript exists only once "
        "the call has ended, and at that point the post-call webhook has "
        "already stored it. Remove this node."
    )


def _summarise(ctx: RunContext) -> str:
    counts: dict[str, int] = {}
    for step in ctx.log.steps:
        status = str(step.get("status"))
        counts[status] = counts.get(status, 0) + 1
    parts = [f"{count} {status}" for status, count in sorted(counts.items())]

    summary = f"{len(ctx.log.steps)} step(s): {', '.join(parts)}"
    if ctx.call_result is not None:
        summary += f". Call outcome: {ctx.call_result.call_outcome or 'unknown'}"
    if ctx.review_reasons:
        summary += f". For review: {'; '.join(ctx.review_reasons)}"
    return summary


def _create_report(ctx: RunContext, node: Node) -> Outcome:
    """Summarise the run into the execution log.

    No `reports` row is written, and that is a gap rather than a design: the
    table exists and RLS covers it, but it has no entry in `PATIENT_CHILD_TABLES`
    or `WRITABLE_COLUMNS`, so the application cannot write to it at all. See
    "Deliberately not built" in backend/STATUS.md.

    Summarising into the log is the honest version of what this node can do
    today — the report is real, its storage is not yet separate.
    """
    return ok(f"Run report — {_summarise(ctx)}")


def _send_summary_to_doctor(ctx: RunContext, node: Node) -> Outcome:
    row = ctx.scope.insert_for_patient(
        "notifications",
        str(ctx.patient.get("id")),
        {
            "recipient": "doctor",
            "message": (
                f"Workflow '{ctx.workflow.get('name') or 'unnamed'}' — "
                f"{_summarise(ctx)}"
            ),
            "priority": "urgent" if ctx.review_reasons else "normal",
        },
    )
    return ok(
        "Summary sent to the doctor",
        entity={"table": "notifications", "id": str(row.get("id"))},
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

HANDLERS: Final[dict[str, Handler]] = {
    # Triggers all share one handler: a trigger's only job is to be the node the
    # walk starts from.
    "lab_results_received": _trigger,
    "abnormal_result_detected": _trigger,
    "follow_up_due": _trigger,
    "appointment_missed": _trigger,
    "new_patient_registered": _trigger,
    "prescription_expiring": _trigger,
    # Conditionals
    "check_result_values": _check_result_values,
    "check_insurance": _check_insurance,
    "check_patient_age": _check_patient_age,
    "check_appointment_history": _check_appointment_history,
    "check_medication_list": _check_medication_list,
    # Actions
    "call_patient": _call_patient,
    "send_sms": _send_sms,
    "schedule_appointment": _schedule_appointment,
    "send_notification": _send_notification,
    "create_lab_order": _create_lab_order,
    "create_referral": _create_referral,
    "update_patient_record": _update_patient_record,
    "assign_to_staff": _assign_to_staff,
    # Output
    "log_completion": _log_completion,
    "generate_transcript": _generate_transcript,
    "create_report": _create_report,
    "send_summary_to_doctor": _send_summary_to_doctor,
}


def run_node(ctx: RunContext, node: Node) -> Outcome:
    """Dispatch one node, turning its refusals into outcomes.

    Every exception a handler can raise deliberately is converted here, so a
    handler never has to decide how a refusal is recorded and the log cannot end
    up with two spellings of the same thing.

    An unexpected exception is not caught. It propagates to the runner, which
    records the run as failed and re-raises — a bug in a handler must not be
    indistinguishable from a workflow that was drawn wrong.
    """
    handler = HANDLERS.get(node.node_type)
    if handler is None:  # pragma: no cover - _registry_is_complete prevents it
        return failed(f"No handler for node type {node.node_type!r}")

    try:
        return handler(ctx, node)
    except PolicyRefusal as exc:
        ctx.require_review(str(exc))
        return blocked(str(exc))
    except _MissingParam as exc:
        return blocked(str(exc))


def _registry_is_complete() -> None:
    """Assert at import time that every catalogued node type has a handler.

    A node type added to catalogue.py without one would otherwise pass the
    graph's validation — it is a known type — and then fail at the moment it is
    reached, halfway through a run. This makes it fail the boot instead.
    """
    missing = ALL_NODE_TYPES - set(HANDLERS)
    if missing:
        raise RuntimeError(
            f"Node types with no handler: {', '.join(sorted(missing))}"
        )
    extra = set(HANDLERS) - ALL_NODE_TYPES
    if extra:
        raise RuntimeError(
            f"Handlers for node types absent from the catalogue: "
            f"{', '.join(sorted(extra))}"
        )


_registry_is_complete()
