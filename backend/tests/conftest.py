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

TEST_ISSUER = "https://clarus-test.clerk.accounts.dev"
TEST_AUTHORIZED_PARTY = "http://localhost:3000"
TEST_WEBHOOK_SECRET = "wsec_test_secret"

# Must be set before app.core.config resolves its cached Settings.
os.environ.update(
    {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        "CLERK_ISSUER": TEST_ISSUER,
        "CLERK_AUTHORIZED_PARTIES": TEST_AUTHORIZED_PARTY,
        "ENVIRONMENT": "test",
        "ELEVENLABS_WEBHOOK_SECRET": TEST_WEBHOOK_SECRET,
    }
)

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_tenant_scope  # noqa: E402
from app.core import security  # noqa: E402
from app.db import doctors as doctors_db  # noqa: E402
from app.db.client import get_supabase  # noqa: E402
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Supabase
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _Query:
    """The subset of postgrest-py's builder that TenantScope relies on."""

    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._op: str | None = None
        self._payload: dict | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "_Query":
        self._op = "select"
        return self

    def insert(self, payload: dict) -> "_Query":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: dict) -> "_Query":
        self._op = "update"
        self._payload = payload
        return self

    def delete(self) -> "_Query":
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> "_Query":
        self._filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: Any) -> "_Query":
        # postgrest spells IS NULL as the literal string "null".
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "_Query":
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> "_Query":
        self._limit = count
        return self

    def _matches(self, row: dict) -> bool:
        for op, col, val in self._filters:
            if op == "eq":
                if row.get(col) != val:
                    return False
            elif op == "is":
                if val in ("null", None):
                    if row.get(col) is not None:
                        return False
                elif row.get(col) is not val:
                    return False
            else:  # pragma: no cover — guards a typo in a new filter
                raise AssertionError(f"unsupported filter {op!r}")
        return True

    def execute(self) -> _Result:
        rows = self._store.setdefault(self._table, [])

        if self._op == "select":
            found = [dict(r) for r in rows if self._matches(r)]
            if self._order:
                column, desc = self._order
                found.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
            if self._limit is not None:
                found = found[: self._limit]
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
    """Mint a real RS256 token shaped like a Clerk session token.

    Defaults are valid; override to make it invalid. Note the absence of `aud`:
    that matches Clerk, which omits the claim unless a JWT template adds one,
    and it means these tests exercise the same code path production does.
    """

    def _make(
        subject: str = "user_default",
        *,
        issuer: str = TEST_ISSUER,
        azp: str | None = TEST_AUTHORIZED_PARTY,
        expires_in: int = 60,
        not_before: int = 0,
        **extra_claims: Any,
    ) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        claims: dict[str, Any] = {
            "sub": subject,
            "iss": issuer,
            "iat": now,
            "nbf": now + dt.timedelta(seconds=not_before),
            "exp": now + dt.timedelta(seconds=expires_in),
            "sid": "sess_test",
        }
        if azp is not None:
            claims["azp"] = azp
        claims.update(extra_claims)
        return jwt.encode(claims, signing_key, algorithm="RS256")

    return _make


@pytest.fixture
def auth_header(make_token):
    def _header(subject: str = "user_default", **kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(subject, **kwargs)}"}

    return _header


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_doctor_cache() -> None:
    """Each test gets a fresh FakeSupabase, so the provisioning cache — which
    is process-global — would otherwise report subjects from an earlier test
    as already provisioned against a store that has never seen them."""
    doctors_db.reset_cache()


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


__all__ = [
    "FakeSupabase",
    "get_tenant_scope",
    "TEST_AUTHORIZED_PARTY",
    "TEST_ISSUER",
    "TEST_WEBHOOK_SECRET",
]
