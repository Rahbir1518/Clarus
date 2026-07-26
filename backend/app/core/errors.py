"""Error types and handlers.

Two rules drive this module:

1. Clients get a consistent JSON envelope, so the frontend can parse one shape.
2. Unhandled exceptions never leak internals. The old backend returned raw
   exception strings, which on a database error meant handing out table and
   column names.
"""
import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class NotFound(Exception):
    """A resource does not exist, or does not belong to the caller.

    Deliberately one exception for both cases. Distinguishing them would let a
    caller probe for the existence of other tenants' records by comparing 403s
    against 404s.
    """

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found")
        self.resource = resource


def _envelope(message: str, *, code: str, extra: dict | None = None) -> dict:
    body = {"error": {"code": code, "message": message}}
    if extra:
        body["error"].update(extra)
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def _handle_not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_envelope(str(exc), code="not_found"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(str(exc.detail), code="http_error"),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            # Literal rather than status.HTTP_422_*: Starlette renamed the
            # constant and referencing either name warns on one version or
            # breaks on the other.
            status_code=422,
            content=_envelope(
                "Request validation failed",
                code="validation_error",
                extra={"details": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Correlate the opaque client response with the full server-side trace.
        incident = uuid.uuid4().hex[:12]
        logger.exception(
            "Unhandled error [%s] on %s %s", incident, request.method, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                "Internal server error",
                code="internal_error",
                extra={"incident_id": incident},
            ),
        )
