"""First-request provisioning of the tenant root.

Every tenant-owned table now has a foreign key to `doctors(id)`, so a caller
whose Clerk user id has no `doctors` row cannot insert anything at all — the
first patient they create fails on the constraint. Something has to create that
row, and this is it.

That constraint is the point rather than an obstacle. The old backend defaulted
a missing identity to the string `'anonymous'` and wrote records under it; those
records belonged to nobody and could never be recovered by the doctor who
created them. With the foreign key in place there is no such string to fall back
to: either the tenant exists or the write is refused by the database.

This module is a deliberate exception to "everything goes through TenantScope",
on the same terms as app/db/system.py: it writes exactly one row, that row is
the caller's own, and its primary key comes from a verified token rather than
from anything the request supplies.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Subjects known to have a row. Purely an optimisation — it saves a SELECT on
# every authenticated request. Losing it on restart costs one extra query per
# subject, and a stale entry cannot grant access to anything, because the tenant
# key still comes from the token on every request.
_provisioned: set[str] = set()
_lock = threading.Lock()


def reset_cache() -> None:
    """Forget which subjects are provisioned. For tests."""
    with _lock:
        _provisioned.clear()


def _rows(response: Any) -> list[dict]:
    return list(getattr(response, "data", None) or [])


def ensure_doctor(
    client: Any,
    *,
    doctor_id: str,
    name: str | None = None,
    email: str | None = None,
) -> None:
    """Create the caller's `doctors` row if it does not exist yet.

    Idempotent and safe under concurrency: two simultaneous first requests race
    to insert, one loses on the primary key, and the loser confirms the row is
    there rather than failing the request.
    """
    if not doctor_id:
        raise ValueError("ensure_doctor requires a non-empty doctor_id")

    with _lock:
        if doctor_id in _provisioned:
            return

    if _exists(client, doctor_id):
        _remember(doctor_id)
        return

    payload = {
        "id": doctor_id,
        # NOT NULL in the schema. Access tokens often carry no profile claims,
        # so the subject stands in until the doctor edits their profile — a
        # visibly provisional name is better than a fabricated one.
        "name": name or doctor_id,
        "email": email,
    }
    try:
        client.table("doctors").insert(payload).execute()
    except Exception:
        # Almost certainly the primary-key collision from a concurrent first
        # request. Confirm rather than assume: if the row genuinely is not
        # there, the original error is the useful one to surface.
        if not _exists(client, doctor_id):
            raise
        logger.debug("doctors row for %s created concurrently", doctor_id)

    _remember(doctor_id)


def _exists(client: Any, doctor_id: str) -> bool:
    return bool(
        _rows(client.table("doctors").select("id").eq("id", doctor_id).execute())
    )


def _remember(doctor_id: str) -> None:
    with _lock:
        _provisioned.add(doctor_id)
