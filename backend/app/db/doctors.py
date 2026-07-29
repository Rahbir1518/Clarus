"""Tenant row provisioning.

Every table carrying doctor_id now has a foreign key to `doctors`, which means a
doctors row must exist before the first patient, workflow, call log or
appointment is written for a tenant. Nothing in the product asks a doctor to
create a profile first — they sign in and start using it — so the row has to
appear on its own, and the only place that reliably happens is the
authenticated request path.

This is called from `get_tenant_scope`, which is the sole constructor of
TenantScope used by routes. Putting it there rather than in each handler means a
new resource cannot be added that writes a tenant-owned row without the parent
existing; it is the same reasoning that keeps the tenant filter in TenantScope.

The write is an insert-if-missing, not an update. Refreshing name and email from
the token on every request looks tidier and is wrong twice over: access tokens
frequently carry no profile claims at all, so it would overwrite a real name
with a placeholder, and once a doctor edits their own name, NPI or practice, the
identity provider is no longer the authority on it.
"""
import logging
import threading
import time
from typing import Any

from app.core.security import CurrentUser

logger = logging.getLogger(__name__)

# One insert attempt per subject per window, rather than per request. The row is
# immutable once created, so re-checking it is pure overhead on every call.
_TTL_SECONDS = 900.0

# Bounds the memory in a process serving many tenants. Eviction is by insertion
# order, and being evicted early costs one redundant insert that conflicts and
# does nothing.
_MAX_TRACKED = 4096

# Guarded because FastAPI runs sync dependencies in a threadpool, so several
# requests touch this concurrently. A lost update here would only cause a
# duplicate insert that the ON CONFLICT swallows, but a dict mutated from
# multiple threads while being iterated for eviction will not.
_lock = threading.Lock()
_seen: dict[str, float] = {}


def reset_cache() -> None:
    """Forget which subjects have been provisioned. For tests."""
    with _lock:
        _seen.clear()


def _claim_provisioning(subject: str) -> bool:
    """True if this caller should attempt the insert.

    Marks the subject as handled before the write is attempted, so a burst of
    concurrent requests from one doctor produces one insert rather than one per
    request. The mark is removed again if the write fails.
    """
    now = time.monotonic()
    with _lock:
        last = _seen.get(subject)
        if last is not None and now - last < _TTL_SECONDS:
            return False
        if len(_seen) >= _MAX_TRACKED:
            _seen.pop(next(iter(_seen)), None)
        _seen[subject] = now
        return True


def _forget(subject: str) -> None:
    with _lock:
        _seen.pop(subject, None)


def _display_name(claims: dict[str, Any]) -> str:
    """A best-effort name from whatever the token happens to carry.

    'Unknown' is the common case, not the exceptional one: an API access token
    normally carries no profile claims, only `sub`. It is a placeholder for a
    profile screen to replace, and `doctors.name` is NOT NULL specifically so
    that there is always something to render.
    """
    for key in ("name", "nickname", "preferred_username"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    given, family = claims.get("given_name"), claims.get("family_name")
    parts = [p.strip() for p in (given, family) if isinstance(p, str) and p.strip()]
    if parts:
        return " ".join(parts)

    email = claims.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()

    return "Unknown"


def ensure_doctor(client: Any, user: CurrentUser) -> None:
    """Create the caller's doctors row if it is not already there.

    Never raises. A failure here would otherwise turn a transient database blip
    into a 500 on reads that did not need the row at all; writes will still fail
    on the foreign key, loudly and with an incident id, which is the correct
    place for that error to surface. The subject is un-marked so the next
    request retries rather than waiting out the cache window.
    """
    if not _claim_provisioning(user.subject):
        return

    payload = {"id": user.subject, "name": _display_name(user.claims)}
    email = user.claims.get("email")
    if isinstance(email, str) and email.strip():
        payload["email"] = email.strip()

    try:
        client.table("doctors").upsert(
            payload,
            on_conflict="id",
            # ON CONFLICT DO NOTHING. A DO UPDATE would clobber a profile the
            # doctor has edited with claims from a token that may not have them.
            ignore_duplicates=True,
        ).execute()
    except Exception:
        _forget(user.subject)
        logger.warning(
            "Could not provision doctors row for subject %s; "
            "tenant-owned writes will fail on the foreign key until this succeeds",
            user.subject,
            exc_info=True,
        )
