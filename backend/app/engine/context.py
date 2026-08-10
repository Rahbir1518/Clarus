"""The state one run carries, and the reads its nodes make.

Separated from nodes.py so a handler is a function of context rather than a
method on the runner, and separated from runner.py so the resume path can
rebuild the same context from a stored row without duplicating any of it.

Every database read here goes through the run's `TenantScope`. That includes the
resume path, where there is no authenticated caller: the scope is built from the
`doctor_id` on the stored call log rather than from anything a webhook sent. See
`app.db.system.tenant_scope_for_row` for why that is sound.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.db.tenancy import TenantScope
from app.engine.graph import Graph
from app.engine.steps import ExecutionLog
from app.integrations.elevenlabs.webhook import CallResult

logger = logging.getLogger(__name__)

# Keys under which an incoming event may carry lab values. Several, because the
# event body is free-form JSON from whatever produced it — the dashboard's
# trigger simulator today, a PDF extractor or a lab feed later — and rejecting a
# reasonable synonym would make the same data unusable depending on who sent it.
_RESULT_KEYS = ("results", "values", "lab_results", "lab_values")


def _coerce_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        # Accept a full timestamp too: `last_visit` is a DATE column but
        # PostgREST has been known to hand back either form.
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def extract_lab_values(metadata: dict[str, Any]) -> dict[str, float]:
    """Pull numeric lab values out of an event body.

    Two shapes are accepted, because both are natural to send:

        {"results": {"hba1c": 8.2}}
        {"results": [{"test": "hba1c", "value": 8.2}, ...]}

    Names are lowercased and stripped so "HbA1c" in the event matches "hba1c"
    on the node. Anything non-numeric is dropped here rather than at the
    comparison, so a node asking for a value that arrived as "pending" sees it
    as absent — which is the state that blocks the branch rather than the state
    that silently compares false.
    """
    values: dict[str, float] = {}

    def put(name: Any, raw: Any) -> None:
        key = str(name or "").strip().lower()
        number = _coerce_float(raw)
        if key and number is not None:
            values[key] = number

    for source_key in _RESULT_KEYS:
        source = metadata.get(source_key)
        if isinstance(source, dict):
            for name, raw in source.items():
                put(name, raw)
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    put(
                        item.get("test") or item.get("name") or item.get("test_name"),
                        item.get("value") if "value" in item else item.get("result"),
                    )
    return values


@dataclass
class RunContext:
    """Everything one walk of the graph can see."""

    scope: TenantScope
    workflow: dict
    patient: dict
    graph: Graph
    call_log_id: str
    log: ExecutionLog
    settings: Settings
    metadata: dict[str, Any] = field(default_factory=dict)

    # Set only on the resume path, from the post-call webhook.
    call_result: CallResult | None = None

    # A run places at most one call. See the call_patient handler for why.
    call_placed: bool = False

    # Abnormal-result taint. Once true it never goes back to false: a run that
    # touched an abnormal result stays a run that touched an abnormal result,
    # whatever it does afterwards.
    abnormal: bool = False
    abnormal_reason: str = ""

    # Accumulated reasons a human should look at this run. Empty means the run
    # may clear `needs_review`; anything in it means the flag stays set.
    review_reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.metadata.get("abnormal") is True:
            self.taint_abnormal("the triggering event was marked abnormal")

    # -- run-level state ----------------------------------------------------

    def taint_abnormal(self, reason: str) -> None:
        """Mark this run as carrying an abnormal result.

        The first reason wins. A run tainted by its trigger and then again by a
        threshold node is more usefully described by how it started.
        """
        if not self.abnormal:
            self.abnormal = True
            self.abnormal_reason = reason

    def require_review(self, why: str) -> None:
        self.review_reasons.append(why)

    @property
    def lab_values(self) -> dict[str, float]:
        return extract_lab_values(self.metadata)

    def lab_value(self, test_name: str) -> float | None:
        return self.lab_values.get(test_name.strip().lower())

    def doctor_display_name(self) -> str | None:
        """What the agent calls the doctor.

        The workflow's own `doctor_name` first: it is the field the builder
        offers for exactly this, and it is free text set by the practice about
        itself rather than an identity claim — the tenant key is `doctor_id`,
        which no payload can set.
        """
        name = self.workflow.get("doctor_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None

    # -- patient facts ------------------------------------------------------

    def patient_age(self, today: date | None = None) -> int | None:
        born = _parse_date(self.patient.get("dob"))
        if born is None:
            return None
        today = today or date.today()
        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )

    def days_since_last_appointment(self, today: date | None = None) -> int | None:
        """Days since the most recent appointment in the past, or None.

        Prefers the `appointments` table and falls back to
        `patients.last_visit`, because the table is authoritative but only holds
        what this system booked — a practice migrating in has a `last_visit` and
        no appointment rows.
        """
        today = today or date.today()
        latest: date | None = None

        for row in self.scope.list_owned(
            "appointments", filters={"patient_id": self.patient.get("id")}
        ):
            starts = _parse_timestamp(row.get("starts_at"))
            if starts is None:
                continue
            when = starts.date()
            if when <= today and (latest is None or when > latest):
                latest = when

        if latest is None:
            latest = _parse_date(self.patient.get("last_visit"))
        if latest is None:
            return None
        return (today - latest).days

    def active_medications(self) -> list[dict]:
        rows = self.scope.list_for_patient(
            "patient_medications", str(self.patient.get("id"))
        )
        # A medication with no status recorded counts as active: the column is
        # free text and an older row may simply not have one, and treating that
        # as "not taking it" is the direction that gets a contraindication
        # missed.
        return [
            row
            for row in rows
            if str(row.get("status") or "active").strip().lower()
            not in {"stopped", "completed", "cancelled", "inactive"}
        ]

    # -- call history -------------------------------------------------------

    def recent_call_attempts(self, *, hours: int = 24, now: datetime | None = None) -> int:
        """Calls actually placed to this patient in the trailing window.

        Counts only rows that reached a provider conversation, so a run blocked
        before dialling does not consume one of the patient's attempts. This
        run's own row is excluded — it exists before the call is placed, and
        counting it would make the cap off by one.

        A row whose `created_at` cannot be parsed is counted rather than
        skipped. Both directions are wrong; this one errs towards fewer calls.
        """
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)
        attempts = 0
        for row in self.scope.list_owned(
            "call_logs", filters={"patient_id": self.patient.get("id")}
        ):
            if str(row.get("id")) == str(self.call_log_id):
                continue
            if not row.get("conversation_id"):
                continue
            created = _parse_timestamp(row.get("created_at"))
            if created is None or created >= cutoff:
                attempts += 1
        return attempts
