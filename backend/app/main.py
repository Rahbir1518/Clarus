"""Clarus API — application entry point.

Run locally:  uvicorn app.main:app --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    call_logs,
    calls,
    clinical,
    events,
    executions,
    health,
    patients,
    webhooks,
    workflows,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.events.broker import broker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Resolved at import so a missing required setting fails the boot rather than
# the first request that happens to need it.
settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Hand the broker the serving loop.

    Webhook handlers are sync `def` and run in a threadpool, so publishing from
    one has to cross into this loop. The broker cannot discover it on its own —
    there is no running loop at import time — so it is handed over here.
    """
    broker.bind(asyncio.get_running_loop())
    try:
        yield
    finally:
        broker.unbind()


app = FastAPI(
    lifespan=lifespan,
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
app.include_router(clinical.conditions_router, prefix="/api")
app.include_router(clinical.medications_router, prefix="/api")
app.include_router(workflows.router, prefix="/api")
# Workflow *runs*, kept out of workflows.py because they are a different thing
# from CRUD on the definition. See routes/executions.py.
app.include_router(executions.workflow_router, prefix="/api")
app.include_router(executions.lab_event_router, prefix="/api")
app.include_router(call_logs.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(events.router, prefix="/api")
# Signature-authenticated, not token-authenticated. See routes/webhooks.py.
app.include_router(webhooks.router, prefix="/api")
