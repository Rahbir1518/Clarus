"""Shared FastAPI dependencies."""
from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.security import CurrentUser, get_current_user
from app.db.client import get_supabase
from app.db.tenancy import TenantScope

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]

# Injected rather than called directly so tests can substitute a fake store
# without stubbing out authentication as well.
SupabaseDep = Annotated[Any, Depends(get_supabase)]


def get_tenant_scope(user: CurrentUserDep, client: SupabaseDep) -> TenantScope:
    """The tenant key comes from the verified token, never from the request.

    Because this is the only constructor of TenantScope used by routes, no
    handler can address a tenant other than the caller's.
    """
    return TenantScope(client, user.subject)


TenantDep = Annotated[TenantScope, Depends(get_tenant_scope)]


async def get_raw_body(request: Request) -> bytes:
    """The exact bytes received, for signature verification.

    Async so it runs before FastAPI dispatches a sync handler to the
    threadpool. Webhook handlers stay sync (the Supabase client blocks), and
    they cannot await the body themselves — hence reading it here.

    Signature checks must use these bytes, never a re-serialised copy of the
    parsed JSON: json.dumps would reorder keys and change whitespace, and the
    HMAC would never match.
    """
    return await request.body()


RawBodyDep = Annotated[bytes, Depends(get_raw_body)]
