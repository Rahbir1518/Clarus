"""Tenant-scoped database access.

The old backend enforced isolation with a `WHERE doctor_id = ?` that callers
were trusted to remember. They did not always remember: one workflow listing
shipped with no filter at all and showed every doctor's workflows to every user.

The approach here is to remove the opportunity. `TenantScope` cannot be
constructed without a doctor_id, and it exposes no method that returns an
unfiltered query builder. Writing a cross-tenant read is not a thing you can
forget to prevent; it is a thing you cannot express.

The same reasoning drives soft deletion. Retention rules for clinical records
outlast a user clicking a delete button, and the child tables cascade, so one
DELETE on a patient used to take their conditions, medications, transcripts,
labs and referrals with it. Rather than asking every future query to remember
`deleted_at IS NULL`, the filter lives here, next to the tenant filter, applied
by the same methods that already cannot be bypassed.
"""
import datetime as dt
from typing import Any, Final

from app.core.errors import NotFound

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

# Tables with a deleted_at column, where a delete marks the row and every read
# filters it out. Must stay in step with the schema: a table listed here without
# the column fails on the first delete, and a table with the column missing from
# here silently keeps hard-deleting.
#
# The tables deliberately absent are the ones holding no PHI — workflows are
# automation config, notifications and staff_assignments are operational
# ephemera — plus `reports`, which no scoped method reaches yet.
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

# Owned by the database or by this class. A client may never supply them.
#
# The *_doctor_id entries are here because they are foreign keys to doctors, and
# the child-table write path would otherwise pass them straight through from the
# request body — letting a caller attribute their referral to another tenant, or
# name one as a prescriber. Nothing populates them from client input; a server
# path that wants to set one does it deliberately, as insert_for_patient does
# below for referrals.
_SYSTEM_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "doctor_id",
        "created_at",
        "updated_at",
        "deleted_at",
        "referring_doctor_id",
        "prescriber_doctor_id",
    }
)

# patient_id is a legitimate field when creating a tenant-owned row that points
# at a patient — call_logs does exactly that. It is never re-assignable
# afterwards, because that would move an existing row to a different patient.
_REPARENTING_FIELDS: Final[frozenset[str]] = frozenset({"patient_id"})

# A referral is made by whoever is acting, so the caller is the only correct
# value. Medications are not in this map on purpose: `prescriber_doctor_id` is a
# claim about who wrote the prescription, and most medications on an intake list
# were prescribed by someone outside this system — defaulting it to the caller
# would record a falsehood. That column stays NULL until a route sets it.
_CALLER_ATTRIBUTED_COLUMN: Final[dict[str, str]] = {
    "referrals": "referring_doctor_id",
}


def _sanitise(values: dict[str, Any], *, allow_patient_id: bool) -> dict[str, Any]:
    blocked = _SYSTEM_FIELDS if allow_patient_id else _SYSTEM_FIELDS | _REPARENTING_FIELDS
    return {k: v for k, v in values.items() if k not in blocked}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _rows(response: Any) -> list[dict]:
    return list(getattr(response, "data", None) or [])


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

    def _live(self, table: str, query: Any) -> Any:
        """Restrict a query to rows that have not been soft-deleted.

        Applied by every read and every mutation, so a deleted row is not just
        hidden from listings — it cannot be fetched by id, updated, or deleted
        again either.
        """
        if table in SOFT_DELETE_TABLES:
            return query.is_("deleted_at", "null")
        return query

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
        query = self._live(
            table,
            self._client.table(table).select("*").eq("doctor_id", self._doctor_id),
        )
        for column, value in (filters or {}).items():
            if value is not None:
                query = query.eq(column, value)
        return _rows(query.order(order_by, desc=descending).execute())

    def get_owned(self, table: str, row_id: str) -> dict:
        table = self._owned_table(table)
        rows = _rows(
            self._live(
                table,
                self._client.table(table)
                .select("*")
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id),
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def insert_owned(self, table: str, values: dict[str, Any]) -> dict:
        payload = _sanitise(values, allow_patient_id=True)

        # A tenant-owned row may reference a patient. Verify that reference
        # points at a patient this tenant owns rather than trusting it — a
        # forged patient_id would otherwise link a call log to a stranger.
        if table != "patients" and payload.get("patient_id"):
            self.assert_owns_patient(payload["patient_id"])

        # Set last, so a client-supplied doctor_id can never win.
        payload["doctor_id"] = self._doctor_id
        rows = _rows(
            self._client.table(self._owned_table(table)).insert(payload).execute()
        )
        if not rows:
            raise RuntimeError(f"Insert into {table} returned no row")
        return rows[0]

    def update_owned(self, table: str, row_id: str, values: dict[str, Any]) -> dict:
        payload = _sanitise(values, allow_patient_id=False)
        if not payload:
            return self.get_owned(table, row_id)
        table = self._owned_table(table)
        rows = _rows(
            self._live(
                table,
                self._client.table(table)
                .update(payload)
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id),
            ).execute()
        )
        if not rows:
            # Either absent, soft-deleted, or another tenant's. Same answer for
            # all three.
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def delete_owned(self, table: str, row_id: str) -> None:
        table = self._owned_table(table)

        if table in SOFT_DELETE_TABLES:
            # Stamped rather than removed. Reads filter it out, so the caller
            # sees the same thing they would have seen after a real delete.
            builder = self._live(
                table,
                self._client.table(table)
                .update({"deleted_at": _now()})
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id),
            )
        else:
            builder = (
                self._client.table(table)
                .delete()
                .eq("id", row_id)
                .eq("doctor_id", self._doctor_id)
            )

        if not _rows(builder.execute()):
            raise NotFound(table.rstrip("s").replace("_", " ").title())

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
            self._live(
                table,
                self._client.table(table).select("*").eq("patient_id", patient_id),
            )
            .order(order_by, desc=descending)
            .execute()
        )

    def get_for_patient(self, table: str, patient_id: str, row_id: str) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        rows = _rows(
            self._live(
                table,
                self._client.table(table)
                .select("*")
                .eq("id", row_id)
                .eq("patient_id", patient_id),
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
        payload = _sanitise(values, allow_patient_id=False)
        payload["patient_id"] = patient_id

        attributed = _CALLER_ATTRIBUTED_COLUMN.get(table)
        if attributed:
            payload[attributed] = self._doctor_id

        rows = _rows(self._client.table(table).insert(payload).execute())
        if not rows:
            raise RuntimeError(f"Insert into {table} returned no row")
        return rows[0]

    def update_for_patient(
        self, table: str, patient_id: str, row_id: str, values: dict[str, Any]
    ) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        payload = _sanitise(values, allow_patient_id=False)
        if not payload:
            return self.get_for_patient(table, patient_id, row_id)
        rows = _rows(
            self._live(
                table,
                self._client.table(table)
                .update(payload)
                .eq("id", row_id)
                .eq("patient_id", patient_id),
            ).execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def delete_for_patient(self, table: str, patient_id: str, row_id: str) -> None:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)

        if table in SOFT_DELETE_TABLES:
            builder = self._live(
                table,
                self._client.table(table)
                .update({"deleted_at": _now()})
                .eq("id", row_id)
                .eq("patient_id", patient_id),
            )
        else:
            builder = (
                self._client.table(table)
                .delete()
                .eq("id", row_id)
                .eq("patient_id", patient_id)
            )

        if not _rows(builder.execute()):
            raise NotFound(table.rstrip("s").replace("_", " ").title())
