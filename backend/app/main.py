"""Clarus API — application entry point.

Run locally:  uvicorn app.main:app --reload
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, patients, webhooks
from app.core.config import get_settings
from app.core.errors import register_error_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Resolved at import so a missing required setting fails the boot rather than
# the first request that happens to need it.
settings = get_settings()

app = FastAPI(
    title="Clarus API",
    description="Medical workflow automation backend",
    version="0.1.0",
    # The interactive docs describe every route and its auth requirements.
    # Useful in development, an inventory of attack surface in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # Glob entries like "https://*.vercel.app" never worked: allow_origins is an
    # exact string match. Preview deployments need the regex.
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(patients.router, prefix="/api")
# Signature-authenticated, not token-authenticated. See routes/webhooks.py.
app.include_router(webhooks.router, prefix="/api")
