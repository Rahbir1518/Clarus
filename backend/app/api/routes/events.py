"""Server-sent events: the live half of the API.

One long-lived GET per browser tab. The stream carries notifications only — a
name and a row id — and the client answers each by re-fetching through the
ordinary routes. So the data path is unchanged, still tenant-scoped by
TenantScope and still auditable; only the "when" moved.

Why SSE and not a websocket: the traffic is one-directional and the client has
nothing to say back. SSE is a plain HTTP response, so it inherits the CORS
config, the auth dependency and the error handlers already in place, and the
browser reconnects on its own.

Why not EventSource on the client: it cannot set an Authorization header, and
the alternative — a token in the query string — puts a credential into access
logs, proxy logs and browser history. The frontend reads this with `fetch` and
a ReadableStream instead; see frontend/services/events.ts.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import TenantDep
from app.events.broker import Event, broker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

# Idle streams look dead to intermediaries. Nginx and most managed proxies drop
# a connection after 30-60s of silence, so send a comment frame well inside
# that. A comment is the cheapest legal SSE frame and clients ignore it.
_HEARTBEAT_SECONDS = 15.0

# Streams end themselves, and the reason is authentication. The Clerk token was
# verified when the request arrived and is never re-checked afterwards — a
# stream held open for a day would be running on a credential that expired
# minutes in. Capping the lifetime means the client reconnects with a fresh
# token, which re-runs the whole auth path. Well under the token's own lifetime
# would be pointless churn; well over it is the thing being avoided.
_MAX_STREAM_SECONDS = 600.0


def _frame(event: Event) -> bytes:
    # No JSON encoder here on purpose: entity_id is a UUID from our own
    # database and name is a module-level constant, so there is nothing to
    # escape, and keeping the frame this literal makes it obvious that no row
    # data can reach it.
    return f"event: {event.name}\ndata: {{\"id\": \"{event.entity_id}\"}}\n\n".encode()


async def _stream(doctor_id: str) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MAX_STREAM_SECONDS

    with broker.subscribe(doctor_id) as queue:
        # Tells the client the stream is live. It fetches its initial state on
        # seeing this, which also closes the gap between subscribing and the
        # first event — anything that changed while connecting is picked up by
        # that fetch rather than missed.
        yield b": connected\n\n"

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                # Named so the client reconnects deliberately rather than
                # treating a clean close as an error.
                yield b"event: reconnect\ndata: {}\n\n"
                return

            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=min(_HEARTBEAT_SECONDS, remaining)
                )
            except asyncio.TimeoutError:
                yield b": ping\n\n"
                continue

            yield _frame(event)


@router.get("/events")
async def stream_events(scope: TenantDep) -> StreamingResponse:
    """Subscribe to the caller's own change notifications.

    Scoped by the token like every other route: TenantScope is constructed from
    the verified subject, and the broker is keyed on the same value, so a
    stream cannot be pointed at another tenant.
    """
    return StreamingResponse(
        _stream(scope.doctor_id),
        media_type="text/event-stream",
        headers={
            # no-transform matters as much as no-cache: compressing proxies
            # buffer, and a buffered event stream is not a live one.
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Nginx-specific, ignored elsewhere. Without it nginx buffers the
            # response and nothing arrives until the stream ends.
            "X-Accel-Buffering": "no",
        },
    )
