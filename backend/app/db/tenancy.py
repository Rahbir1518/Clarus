"""Tenant-scoped database access.

The old backend enforced isolation with a `WHERE doctor_id = ?` that callers
were trusted to remember. They did not always remember: one workflow listing
shipped with no filter at all and showed every doctor's workflows to every user.

The approach here is to remove the opportunity. `TenantScope` cannot be
constructed without a doctor_id, and it exposes no method that returns an
unfiltered query builder. Writing a cross-tenant read is not a thing you can
forget to prevent; it is a thing you cannot express.

The same idea governs writes, in two parts. `WRITABLE_COLUMNS` is an allowlist,
so a column added to the schema is unwritable by a client until someone decides
otherwise. And every foreign key in an accepted payload is resolved through
this scope before the write, so owning the row you are writing does not let you
point it at a row you do not own.
"""
from datetime import datetime, timezone
from typing import Any, Final

from app.core.errors import Conflict, NotFound

# Tables carrying doctor_id directly.
TENANT_TABLES: Final[frozenset[str]] = frozenset(
    {"patients", "workflows", "call_logs", "appointments"}
)

# Tables whose ownership resolves through patients.doctor_id.
PATIENT_CHILD_TABLES: Final[frozenset[str]] = frozenset(
    {
        "patient_conditions",
        "patient_medications",
        "notifications",
        "lab_orders",
        "referrals",
        "staff_assignments",
        "pdf_documents",
    }
)

# Tables with a `deleted_at` column. A delete on one of these sets the
# timestamp; a read on one of these excludes rows that have it. Both happen
# here rather than in handlers, because a soft delete that some read path
# forgets about is worse than no soft delete at all — the record looks gone
# in one view and present in another.
#
# `workflows` is absent on purpose: it is retired via status = 'ARCHIVED' so
# the call logs and reports it produced keep a live reference to it.
SOFT_DELETE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "patients",
        "call_logs",
        "appointments",
        "patient_conditions",
        "patient_medications",
        "lab_orders",
        "referrals",
        "pdf_documents",
    }
)

# Columns a client is allowed to supply, per table.
#
# This is an allowlist rather than a list of blocked system fields, and the
# difference is the whole point. A blocklist names what is dangerous today and
# silently admits every column added tomorrow — which is exactly how
# `referring_doctor_id` and `prescriber_doctor_id` became writable: they are
# foreign keys to `doctors`, no rule here mentioned them, so a request body
# could attribute a referral or a prescription to a doctor who never made it.
# An allowlist fails the other way: a new column is unwritable until someone
# adds it here, having looked at it.
#
# Absent by design, and worth stating so they are not "fixed" later:
#   * id, doctor_id, created_at, updated_at, deleted_at — owned by the database
#     or by this class. deleted_at in particular means a request body can
#     neither delete a row nor resurrect one.
#   * call_logs.conversation_id — the key app/db/system.py uses to resolve an
#     inbound provider webhook to one call log, under a unique index. A client
#     that could set it could squat the id of a call it does not own and
#     receive that call's transcript into its own tenant.
#   * call_logs.transcript — written from the provider webhook, not by a caller.
#   * appointments.calendar_event_id — same squatting shape as conversation_id,
#     under its own unique index.
#   * pdf_documents.uploaded_by — provenance; see _ACTOR_COLUMNS below.
WRITABLE_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "patients": frozenset(
        {
            "name", "phone", "email", "dob", "mrn", "insurance",
            "primary_physician", "last_visit", "risk_level", "notes",
        }
    ),
    "workflows": frozenset(
        {"doctor_name", "name", "description", "category", "status", "nodes", "edges"}
    ),
    "call_logs": frozenset(
        {
            "patient_id", "workflow_id", "trigger_node", "status", "outcome",
            "keypress", "execution_log",
            # The review queue: a human decides a call has been dealt with.
            # Every other outcome column from 002_call_outcomes.sql is absent
            # deliberately — patient_confirmed, reached_patient, confirmed_date
            # and the rest are what the provider reported, and a client that
            # could rewrite them could make a call that never reached anyone
            # look like a confirmed appointment.
            "needs_review", "reviewed_at",
        }
    ),
    "appointments": frozenset(
        {
            "patient_id", "workflow_id", "call_log_id", "starts_at", "ends_at",
            "status", "location", "reason", "notes",
        }
    ),
    "patient_conditions": frozenset(
        {"icd10_code", "description", "hcc_category", "raf_impact", "status"}
    ),
    "patient_medications": frozenset(
        {
            "name", "dosage", "frequency", "route", "prescriber",
            "prescriber_doctor_id", "start_date", "end_date", "status", "notes",
        }
    ),
    "notifications": frozenset({"recipient", "message", "priority", "status", "read_at"}),
    "staff_assignments": frozenset(
        {"staff_id", "task_type", "due_date", "status", "completed_at"}
    ),
    "lab_orders": frozenset({"test_type", "priority", "status", "notes", "completed_at"}),
    "referrals": frozenset(
        {
            "referring_doctor_id", "target_provider_name", "target_facility",
            "specialty", "reason", "urgency", "status", "completed_at",
        }
    ),
    "pdf_documents": frozenset(
        {
            "filename", "file_url", "page_count", "raw_text", "patient_info",
            "lab_results", "tables_data",
        }
    ),
}

# Foreign keys pointing at other tenant-owned rows. Being allowed to *supply*
# one of these is not the same as being allowed to point it anywhere: the value
# names a row that has an owner, and that owner has to be the caller. Verified
# on every write, because a forged id here builds a cross-tenant link out of a
# request that is otherwise entirely legitimate.
_TENANT_REFERENCES: Final[dict[str, str]] = {
    "patient_id": "patients",
    "workflow_id": "workflows",
    "call_log_id": "call_logs",
}

# Foreign keys pointing at `doctors`. Any Clerk subject satisfies the database
# constraint, so the only value a caller may write is their own — anything else
# is a record attributed to a clinician who did not create it.
_SELF_REFERENCES: Final[frozenset[str]] = frozenset(
    {"referring_doctor_id", "prescriber_doctor_id"}
)

# Provenance columns this class fills in from the token, so "who did this" is
# never something the request body gets an opinion about.
_ACTOR_COLUMNS: Final[dict[str, str]] = {"pdf_documents": "uploaded_by"}

# patient_id is legitimate when creating a tenant-owned row that points at a
# patient — call_logs does exactly that. It is never re-assignable afterwards,
# because that would move an existing row to a different patient.
_REPARENTING_FIELDS: Final[frozenset[str]] = frozenset({"patient_id"})


def _sanitise(
    table: str, values: dict[str, Any], *, allow_patient_id: bool
) -> dict[str, Any]:
    try:
        allowed = WRITABLE_COLUMNS[table]
    except KeyError:  # pragma: no cover - guarded by _owned_table/_child_table
        raise ValueError(f"{table!r} has no entry in WRITABLE_COLUMNS") from None
    if not allow_patient_id:
        allowed = allowed - _REPARENTING_FIELDS
    return {k: v for k, v in values.items() if k in allowed}


def _rows(response: Any) -> list[dict]:
    return list(getattr(response, "data", None) or [])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TenantScope:
    """Every database read and write for one authenticated caller."""

    def __init__(self, client: Any, doctor_id: str) -> None:
        if not doctor_id:
            # Defensive: a scope with a falsy tenant key would silently match
            # rows whose doctor_id is NULL or empty.
            raise ValueError("TenantScope requires a non-empty doctor_id")
        self._client = client
        self._doctor_id = doctor_id

    @property
    def doctor_id(self) -> str:
        return self._doctor_id

    # -- internal ----------------------------------------------------------

    def _owned_table(self, table: str) -> str:
        if table not in TENANT_TABLES:
            raise ValueError(
                f"{table!r} is not a tenant-owned table; "
                f"use the *_for_patient methods or add it to TENANT_TABLES"
            )
        return table

    def _child_table(self, table: str) -> str:
        if table not in PATIENT_CHILD_TABLES:
            raise ValueError(
                f"{table!r} is not a patient-owned table; add it to PATIENT_CHILD_TABLES"
            )
        return table

    @staticmethod
    def _alive(query: Any, table: str) -> Any:
        """Exclude soft-deleted rows. Applied to every read in this class."""
        if table in SOFT_DELETE_TABLES:
            query = query.is_("deleted_at", "null")
        return query

    def _verify_references(self, payload: dict[str, Any]) -> None:
        """Refuse any foreign key in `payload` that points outside this tenant.

        Owning the row you are writing says nothing about where its foreign
        keys point. Without this, a caller can create an appointment that is
        unimpeachably theirs by doctor_id while its workflow_id names another
        practice's workflow — a cross-tenant link built from a request that
        passes every other check.

        Everything here raises NotFound, never a distinct "forbidden". The
        alternative tells the caller that the id they guessed exists and
        belongs to someone else, which is the question they were asking.
        """
        for column, table in _TENANT_REFERENCES.items():
            value = payload.get(column)
            if value:
                # Scoped read: not ours, deleted, or absent are all NotFound.
                self.get_owned(table, value)

        for column in _SELF_REFERENCES:
            value = payload.get(column)
            if value is not None and value != self._doctor_id:
                raise NotFound("Doctor")

    # -- tenant-owned tables ------------------------------------------------

    def list_owned(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[dict]:
        table = self._owned_table(table)
        query = self._alive(
            self._client.table(table).select("*").eq("doctor_id", self._doctor_id),
            table,
        )
        for column, value in (filters or {}).items():
            if value is not None:
                query = query.eq(column, value)
        return _rows(query.order(order_by, desc=descending).execute())

    def get_owned(self, table: str, row_id: str) -> dict:
        table = self._owned_table(table)
        rows = _rows(
            self._alive(
                self._client.table(table)
                .select("*")
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id),
                table,
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def insert_owned(self, table: str, values: dict[str, Any]) -> dict:
        table = self._owned_table(table)
        payload = _sanitise(table, values, allow_patient_id=True)

        # A tenant-owned row may reference a patient, a workflow or a call log.
        # Verify every one of those rather than trusting it — a forged id would
        # otherwise link this row to a stranger's record.
        self._verify_references(payload)

        # Set last, so a client-supplied doctor_id can never win.
        payload["doctor_id"] = self._doctor_id
        rows = _rows(self._client.table(table).insert(payload).execute())
        if not rows:
            raise RuntimeError(f"Insert into {table} returned no row")
        return rows[0]

    def update_owned(self, table: str, row_id: str, values: dict[str, Any]) -> dict:
        table = self._owned_table(table)
        payload = _sanitise(table, values, allow_patient_id=False)
        if not payload:
            return self.get_owned(table, row_id)
        # patient_id is already excluded, but workflow_id and call_log_id are
        # updatable and carry the same cross-tenant risk on the way in.
        self._verify_references(payload)
        rows = _rows(
            self._alive(
                self._client.table(table)
                .update(payload)
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id),
                table,
            ).execute()
        )
        if not rows:
            # Either absent, already deleted, or another tenant's. Same answer
            # for all three.
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def bind_conversation(self, call_log_id: str, conversation_id: str) -> dict:
        """Attach a provider conversation id to a call log this caller owns.

        A narrow, single-purpose write, and it has its own method rather than a
        line in WRITABLE_COLUMNS on purpose. conversation_id is the capability
        app/db/system.py resolves an unauthenticated webhook against: whoever
        holds one can write a call outcome. If a client could set it through
        the generic update path, it could point its own call log at someone
        else's conversation and harvest that call's result.

        So: write-once, scoped to the tenant, and never re-pointed.

        A browser-initiated WebRTC session is why this is needed at all. On the
        phone path the id comes back from ElevenLabs on the server, but a web
        session mints it in the browser, so it has to be reported back.
        """
        if not conversation_id:
            raise ValueError("conversation_id must not be empty")

        # Read first, so "already bound" is distinguishable from "not yours".
        row = self.get_owned("call_logs", call_log_id)
        existing = row.get("conversation_id")
        if existing:
            if existing == conversation_id:
                return row  # Idempotent: the browser retried.
            raise Conflict("This call is already bound to another conversation")

        rows = _rows(
            self._alive(
                self._client.table("call_logs")
                .update({"conversation_id": conversation_id})
                .eq("id", call_log_id)
                .eq("doctor_id", self._doctor_id)
                # Lost-update guard. Between the read above and this write,
                # another request may have bound the same row; the filter makes
                # the second writer match nothing instead of overwriting.
                .is_("conversation_id", "null"),
                "call_logs",
            ).execute()
        )
        if not rows:
            raise Conflict("This call was bound to a conversation concurrently")
        return rows[0]

    def delete_owned(self, table: str, row_id: str) -> None:
        """Soft-delete where the table supports it, hard-delete where it does not.

        Filtered on `deleted_at IS NULL` either way, so deleting an
        already-deleted row is a 404 rather than a silent success that moves
        the timestamp and loses when the deletion actually happened.
        """
        table = self._owned_table(table)
        base = self._client.table(table)
        query = (
            base.update({"deleted_at": _now()})
            if table in SOFT_DELETE_TABLES
            else base.delete()
        )
        rows = _rows(
            self._alive(
                query.eq("id", row_id).eq("doctor_id", self._doctor_id), table
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())

    # -- audit trail ---------------------------------------------------------
    #
    # audit_log is deliberately in neither table set. It has no update and no
    # delete — the database enforces that with a trigger — so routing it
    # through the generic CRUD methods would offer operations that cannot
    # succeed. These two methods are the whole interface.

    def record_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        patient_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Append one event to the tenant's audit trail.

        PHIPA wants the record of *access*, not only of change, so this is
        worth calling on reads of patient data as well as writes. Keep
        `metadata` free of PHI: it lands in the same log exports as everything
        else, and the point of the trail is to describe an access rather than
        to duplicate what was accessed.
        """
        row = {
            "doctor_id": self._doctor_id,
            "actor": self._doctor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "patient_id": patient_id,
            "metadata": metadata or {},
        }
        rows = _rows(self._client.table("audit_log").insert(row).execute())
        if not rows:
            raise RuntimeError("Insert into audit_log returned no row")
        return rows[0]

    def list_audit_events(self, *, limit: int = 200) -> list[dict]:
        return _rows(
            self._client.table("audit_log")
            .select("*")
            .eq("doctor_id", self._doctor_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    # -- patient-owned child tables -----------------------------------------

    def assert_owns_patient(self, patient_id: str) -> dict:
        """Resolve the parent patient, or 404. The gate for every child table."""
        return self.get_owned("patients", patient_id)

    def list_for_patient(
        self,
        table: str,
        patient_id: str,
        *,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[dict]:
        # Table validation first: an unknown table is a programming error and
        # should surface as one regardless of what happens to be in the database.
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        return _rows(
            self._alive(
                self._client.table(table).select("*").eq("patient_id", patient_id),
                table,
            )
            .order(order_by, desc=descending)
            .execute()
        )

    def get_for_patient(self, table: str, patient_id: str, row_id: str) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        rows = _rows(
            self._alive(
                self._client.table(table)
                .select("*")
                .eq("id", row_id)
                .eq("patient_id", patient_id),
                table,
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def insert_for_patient(
        self, table: str, patient_id: str, values: dict[str, Any]
    ) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        # patient_id comes from the verified path, never from the body.
        payload = _sanitise(table, values, allow_patient_id=False)
        self._verify_references(payload)
        payload["patient_id"] = patient_id
        # Provenance from the token, after the body has had its say.
        if actor_column := _ACTOR_COLUMNS.get(table):
            payload[actor_column] = self._doctor_id
        rows = _rows(self._client.table(table).insert(payload).execute())
        if not rows:
            raise RuntimeError(f"Insert into {table} returned no row")
        return rows[0]

    def update_for_patient(
        self, table: str, patient_id: str, row_id: str, values: dict[str, Any]
    ) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        payload = _sanitise(table, values, allow_patient_id=False)
        if not payload:
            return self.get_for_patient(table, patient_id, row_id)
        self._verify_references(payload)
        rows = _rows(
            self._alive(
                self._client.table(table)
                .update(payload)
                .eq("id", row_id)
                .eq("patient_id", patient_id),
                table,
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def delete_for_patient(self, table: str, patient_id: str, row_id: str) -> None:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        base = self._client.table(table)
        query = (
            base.update({"deleted_at": _now()})
            if table in SOFT_DELETE_TABLES
            else base.delete()
        )
        rows = _rows(
            self._alive(
                query.eq("id", row_id).eq("patient_id", patient_id), table
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
