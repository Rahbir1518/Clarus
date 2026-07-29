"""Test fixtures.

Two things are faked, and only two:

  * Supabase, by an in-memory store implementing the slice of the query builder
    that TenantScope actually uses.
  * The JWKS endpoint, by a locally generated RSA keypair.

Token verification itself is NOT faked. Tests sign real RS256 tokens and the
application verifies them with the real PyJWT path, so the audience, issuer and
expiry checks are genuinely exercised rather than mocked away.
"""
import datetime as dt
import os
import uuid
from typing import Any

import pytest

TEST_DOMAIN = "clarus-test.us.auth0.com"
TEST_AUDIENCE = "https://api.clarus.test"
TEST_ISSUER = f"https://{TEST_DOMAIN}/"

# Must be set before app.core.config resolves its cached Settings.
os.environ.update(
    {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        "AUTH0_DOMAIN": TEST_DOMAIN,
        "AUTH0_AUDIENCE": TEST_AUDIENCE,
        "ENVIRONMENT": "test",
    }
)

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_tenant_scope  # noqa: E402
from app.core import security  # noqa: E402
from app.db import doctors as doctors_provisioning  # noqa: E402
from app.db.client import get_supabase  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_doctor_provisioning_cache() -> None:
    """Each test gets a fresh store, so the memo of provisioned subjects has to
    be cleared too — otherwise the second test to use a subject skips the insert
    and its doctors row never appears."""
    doctors_provisioning.reset_cache()


# ---------------------------------------------------------------------------
# Fake Supabase
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


# Sentinels for IS NULL / IS NOT NULL, so they cannot collide with a real value.
_IS_NULL = object()
_IS_NOT_NULL = object()


class _Query:
    """The subset of postgrest-py's builder that TenantScope relies on."""

    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._op: str | None = None
        self._payload: dict | None = None
        self._filters: list[tuple[str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._conflict_columns: list[str] = ["id"]
        self._ignore_duplicates = False

    def select(self, *_args: Any, **_kwargs: Any) -> "_Query":
        self._op = "select"
        return self

    def insert(self, payload: dict) -> "_Query":
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(
        self,
        payload: dict,
        *,
        on_conflict: str = "id",
        ignore_duplicates: bool = False,
        **_kwargs: Any,
    ) -> "_Query":
        self._op = "upsert"
        self._payload = payload
        self._conflict_columns = [c.strip() for c in on_conflict.split(",") if c.strip()]
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload: dict) -> "_Query":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "_Query":
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append((column, value))
        return self

    def is_(self, column: str, value: Any) -> "_Query":
        """postgrest's IS filter. Only the NULL form is used, and it is the one
        that matters here: soft-delete reads all filter deleted_at IS NULL, and a
        fake that treated that as `== "null"` would match nothing and make every
        such test pass for the wrong reason."""
        if value in (None, "null", "NULL"):
            self._filters.append((column, _IS_NULL))
        elif value in ("not.null", "NOT NULL"):
            self._filters.append((column, _IS_NOT_NULL))
        else:
            raise AssertionError(f"is_({column!r}, {value!r}) is not supported")
        return self

    def order(self, column: str, desc: bool = False) -> "_Query":
        self._order = (column, desc)
        return self

    def _matches(self, row: dict) -> bool:
        for col, val in self._filters:
            actual = row.get(col)
            if val is _IS_NULL:
                if actual is not None:
                    return False
            elif val is _IS_NOT_NULL:
                if actual is None:
                    return False
            elif actual != val:
                return False
        return True

    def execute(self) -> _Result:
        rows = self._store.setdefault(self._table, [])

        if self._op == "select":
            found = [dict(r) for r in rows if self._matches(r)]
            if self._order:
                column, desc = self._order
                found.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
            return _Result(found)

        if self._op == "insert":
            assert self._payload is not None
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault(
                "created_at", dt.datetime.now(dt.timezone.utc).isoformat()
            )
            rows.append(row)
            return _Result([dict(row)])

        if self._op == "upsert":
            assert self._payload is not None
            existing = next(
                (
                    r
                    for r in rows
                    if all(
                        r.get(c) == self._payload.get(c) for c in self._conflict_columns
                    )
                ),
                None,
            )
            if existing is not None:
                if self._ignore_duplicates:
                    return _Result([])
                existing.update(self._payload)
                return _Result([dict(existing)])
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault(
                "created_at", dt.datetime.now(dt.timezone.utc).isoformat()
            )
            rows.append(row)
            return _Result([dict(row)])

        if self._op == "update":
            assert self._payload is not None
            changed = []
            for row in rows:
                if self._matches(row):
                    row.update(self._payload)
                    changed.append(dict(row))
            return _Result(changed)

        if self._op == "delete":
            removed = [dict(r) for r in rows if self._matches(r)]
            self._store[self._table] = [r for r in rows if not self._matches(r)]
            return _Result(removed)

        raise AssertionError(f"execute() with no operation on {self._table!r}")


class FakeSupabase:
    def __init__(self) -> None:
        self.store: dict[str, list[dict]] = {}

    def table(self, name: str) -> _Query:
        return _Query(self.store, name)


# ---------------------------------------------------------------------------
# Signing key
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _patch_jwks(monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey) -> None:
    """Serve the local public key in place of Auth0's JWKS endpoint."""

    class _StubKey:
        key = signing_key.public_key()

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, _token: str) -> _StubKey:
            return _StubKey()

    monkeypatch.setattr(security, "_jwk_client", lambda: _StubJWKClient())


@pytest.fixture
def make_token(signing_key: rsa.RSAPrivateKey):
    """Mint a real RS256 token. Defaults are valid; override to make it invalid."""

    def _make(
        subject: str = "auth0|doctor-default",
        *,
        audience: str = TEST_AUDIENCE,
        issuer: str = TEST_ISSUER,
        expires_in: int = 3600,
        scope: str = "",
        **extra_claims: Any,
    ) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        claims: dict[str, Any] = {
            "sub": subject,
            "aud": audience,
            "iss": issuer,
            "iat": now,
            "exp": now + dt.timedelta(seconds=expires_in),
        }
        if scope:
            claims["scope"] = scope
        claims.update(extra_claims)
        return jwt.encode(claims, signing_key, algorithm="RS256")

    return _make


@pytest.fixture
def auth_header(make_token):
    def _header(subject: str = "auth0|doctor-default", **kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(subject, **kwargs)}"}

    return _header


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client(fake_db: FakeSupabase):
    # Only the database is overridden. get_current_user and get_tenant_scope run
    # exactly as they do in production.
    app.dependency_overrides[get_supabase] = lambda: fake_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client(fake_db: FakeSupabase):
    app.dependency_overrides[get_supabase] = lambda: fake_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


__all__ = ["FakeSupabase", "get_tenant_scope", "TEST_AUDIENCE", "TEST_ISSUER"]
