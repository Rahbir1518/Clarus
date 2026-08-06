"""Clerk session-token verification.

The previous backend had no authentication of any kind: not one of its ~40
endpoints checked a token, and `doctor_id` was an ordinary query parameter the
client supplied. Anyone with the deployment URL could dump every patient record
with curl.

The rule this module establishes: the tenant identity is the `sub` claim of a
cryptographically verified token, and there is no other way to obtain it.

Clerk's session tokens differ from Auth0's access tokens in three ways that
each matter here:

  * There is no `aud` claim unless you mint tokens from a JWT template that
    adds one. Requiring an audience unconditionally would reject every valid
    token, so `aud` is verified only when CLERK_AUDIENCE is configured.
  * The origin the token was issued to travels in `azp`, and Clerk's guidance
    is to check it. It is the replacement for the audience check: without it, a
    token minted for any other site on the same Clerk instance opens this API.
  * Tokens are short-lived (about a minute) and carry `nbf`, so a little clock
    leeway is the difference between working and intermittently 401ing.
"""
import logging
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# auto_error=False so a missing header produces our own 401 envelope with a
# WWW-Authenticate challenge, rather than Starlette's bare 403.
_bearer_scheme = HTTPBearer(auto_error=False, description="Clerk session token")

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}

# Clerk session tokens live for roughly 60 seconds and the SDK refreshes them
# continuously. A few seconds of tolerance covers ordinary clock drift between
# Clerk's servers and ours without meaningfully extending a token's life.
_LEEWAY_SECONDS = 5


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller.

    `subject` is the Clerk user id — `user_2abc...` — and is the tenant key
    used throughout the database as `doctor_id`. Frozen so a handler cannot
    reassign it partway through a request.
    """

    subject: str
    scopes: frozenset[str]
    claims: dict

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    # Caches keys in-process and refetches on unknown kid, so key rotation is
    # handled without a redeploy.
    return PyJWKClient(get_settings().clerk_jwks_url, cache_keys=True)


def _unauthenticated(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_UNAUTHENTICATED_HEADERS,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Verify the bearer token and return the caller.

    Defined with `def` rather than `async def` on purpose: both the JWKS fetch
    and the signature check are blocking calls, so FastAPI runs this in a
    threadpool instead of stalling the event loop.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthenticated("Missing bearer token")

    settings = get_settings()

    # Only require `aud` when we are actually configured to check one — see the
    # module docstring. Everything else is mandatory on every token.
    required = ["exp", "iat", "iss", "sub"]
    if settings.clerk_audience:
        required.append("aud")

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            # Pinned. Without this an attacker could present an HS256 token
            # signed with the public key as the shared secret.
            algorithms=["RS256"],
            audience=settings.clerk_audience or None,
            issuer=settings.clerk_issuer,
            leeway=_LEEWAY_SECONDS,
            options={
                "require": required,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_aud": bool(settings.clerk_audience),
                "verify_iss": True,
                "verify_signature": True,
            },
        )
    except jwt.PyJWTError as exc:
        # The specific reason (bad signature, wrong issuer, malformed header)
        # goes to the log, not to the caller. Echoing it back tells an attacker
        # which part of their forgery to fix next.
        logger.info("Token rejected: %s: %s", type(exc).__name__, exc)
        raise _unauthenticated("Invalid or expired token") from exc
    except Exception as exc:  # JWKS endpoint unreachable or malformed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify token signing key",
        ) from exc

    _verify_authorized_party(claims, settings.clerk_authorized_party_list)

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _unauthenticated("Token has no usable subject claim")

    return CurrentUser(subject=subject, scopes=_scopes(claims), claims=claims)


def _verify_authorized_party(claims: dict, allowed: list[str]) -> None:
    """Reject a token issued to an origin this API does not serve.

    Skipped entirely when no parties are configured. That is a deliberate
    development convenience and a production gap: with one Clerk instance
    shared across several apps, an unchecked `azp` means a token from any of
    them is accepted here.
    """
    if not allowed:
        return
    azp = claims.get("azp")
    if azp not in allowed:
        logger.info("Token rejected: azp %r is not an authorized party", azp)
        raise _unauthenticated("Invalid or expired token")


def _scopes(claims: dict) -> frozenset[str]:
    """Best-effort scope extraction.

    Default Clerk session tokens carry no `scope`, so this is normally empty.
    Organization permissions arrive as a list in `org_permissions` when the
    session is scoped to an organization; both shapes are folded into one set
    so `has_scope` means the same thing wherever the claim came from.
    """
    found: set[str] = set()

    raw_scope = claims.get("scope")
    if isinstance(raw_scope, str):
        found.update(raw_scope.split())

    permissions = claims.get("org_permissions")
    if isinstance(permissions, list):
        found.update(p for p in permissions if isinstance(p, str))

    return frozenset(found)
