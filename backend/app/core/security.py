"""Auth0 JWT verification.

The previous backend had no authentication of any kind: not one of its ~40
endpoints checked a token, and `doctor_id` was an ordinary query parameter the
client supplied. Anyone with the deployment URL could dump every patient record
with curl.

The rule this module establishes: the tenant identity is the `sub` claim of a
cryptographically verified token, and there is no other way to obtain it.
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
_bearer_scheme = HTTPBearer(auto_error=False, description="Auth0 access token")

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class CurrentUser:
    """An authenticated caller.

    `subject` is the Auth0 `sub` claim and is the tenant key used throughout
    the database as `doctor_id`. Frozen so a handler cannot reassign it
    partway through a request.
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
    return PyJWKClient(get_settings().auth0_jwks_url, cache_keys=True)


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

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            # Pinned. Without this an attacker could present an HS256 token
            # signed with the public key as the shared secret.
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub"],
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_signature": True,
            },
        )
    except jwt.PyJWTError as exc:
        # The specific reason (bad signature, wrong audience, malformed header)
        # goes to the log, not to the caller. Echoing it back tells an attacker
        # which part of their forgery to fix next.
        logger.info("Token rejected: %s: %s", type(exc).__name__, exc)
        raise _unauthenticated("Invalid or expired token") from exc
    except Exception as exc:  # JWKS endpoint unreachable or malformed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify token signing key",
        ) from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _unauthenticated("Token has no usable subject claim")

    raw_scope = claims.get("scope") or ""
    scopes = frozenset(raw_scope.split()) if isinstance(raw_scope, str) else frozenset()

    return CurrentUser(subject=subject, scopes=scopes, claims=claims)
