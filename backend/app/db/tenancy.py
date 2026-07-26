"""Tenant-scoped database access.

The old backend enforced isolation with a `WHERE doctor_id = ?` that callers
were trusted to remember. They did not always remember: one workflow listing
shipped with no filter at all and showed every doctor's workflows to every user.

The approach here is to remove the opportunity. `TenantScope` cannot be
constructed without a doctor_id, and it exposes no method that returns an
unfiltered query builder. Writing a cross-tenant read is not a thing you can
forget to prevent; it is a thing you cannot express.
"""
from typing import Any, Final

from app.core.errors import NotFound

# Tables carrying doctor_id directly.
TENANT_TABLES: Final[frozenset[str]] = frozenset(
    {"patients", "workflows", "call_logs"}
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

# Owned by the database or by this class. A client may never supply them.
_SYSTEM_FIELDS: Final[frozenset[str]] = frozenset(
    {"id", "doctor_id", "created_at", "updated_at"}
)

# patient_id is a legitimate field when creating a tenant-owned row that points
# at a patient — call_logs does exactly that. It is never re-assignable
# afterwards, because that would move an existing row to a different patient.
_REPARENTING_FIELDS: Final[frozenset[str]] = frozenset({"patient_id"})


def _sanitise(values: dict[str, Any], *, allow_patient_id: bool) -> dict[str, Any]:
    blocked = _SYSTEM_FIELDS if allow_patient_id else _SYSTEM_FIELDS | _REPARENTING_FIELDS
    return {k: v for k, v in values.items() if k not in blocked}


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

    # -- tenant-owned tables ------------------------------------------------

    def list_owned(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> list[dict]:
        query = (
            self._client.table(self._owned_table(table))
            .select("*")
            .eq("doctor_id", self._doctor_id)
        )
        for column, value in (filters or {}).items():
            if value is not None:
                query = query.eq(column, value)
        return _rows(query.order(order_by, desc=descending).execute())

    def get_owned(self, table: str, row_id: str) -> dict:
        rows = _rows(
            self._client.table(self._owned_table(table))
            .select("*")
            .eq("id", row_id)
            .eq("doctor_id", self._doctor_id)
            .execute()
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
        rows = _rows(
            self._client.table(self._owned_table(table))
            .update(payload)
            .eq("id", row_id)
            .eq("doctor_id", self._doctor_id)
            .execute()
        )
        if not rows:
            # Either absent or another tenant's. Same answer for both.
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def delete_owned(self, table: str, row_id: str) -> None:
        rows = _rows(
            self._client.table(self._owned_table(table))
            .delete()
            .eq("id", row_id)
            .eq("doctor_id", self._doctor_id)
            .execute()
        )
        if not rows:
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
            self._client.table(table)
            .select("*")
            .eq("patient_id", patient_id)
            .order(order_by, desc=descending)
            .execute()
        )

    def get_for_patient(self, table: str, patient_id: str, row_id: str) -> dict:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        rows = _rows(
            self._client.table(table)
            .select("*")
            .eq("id", row_id)
            .eq("patient_id", patient_id)
            .execute()
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
            self._client.table(table)
            .update(payload)
            .eq("id", row_id)
            .eq("patient_id", patient_id)
            .execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
        return rows[0]

    def delete_for_patient(self, table: str, patient_id: str, row_id: str) -> None:
        table = self._child_table(table)
        self.assert_owns_patient(patient_id)
        rows = _rows(
            self._client.table(table)
            .delete()
            .eq("id", row_id)
            .eq("patient_id", patient_id)
            .execute()
        )
        if not rows:
            raise NotFound(table.rstrip("s").replace("_", " ").title())
