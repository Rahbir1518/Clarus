"""Liveness and readiness. The only unauthenticated routes in the API."""
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness. Deliberately does no I/O and reveals no configuration."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict:
    """Readiness. Reports whether required configuration resolved.

    Returns booleans only — never the values themselves, since this endpoint is
    unauthenticated.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "checks": {
            "supabase_configured": bool(settings.supabase_url),
            "auth0_configured": bool(settings.auth0_domain and settings.auth0_audience),
        },
    }
