"""Supabase client construction.

The key used here is the service role key, which bypasses Row Level Security
on every table. Nothing in this package should be handed a raw client — go
through app.db.tenancy.TenantScope, which is the only thing that knows how to
scope a query to a tenant.
"""
from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
