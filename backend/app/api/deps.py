"""Shared FastAPI dependencies."""
from typing import Annotated, Any

from fastapi import Depends

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
