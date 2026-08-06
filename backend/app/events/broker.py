"""Tenant-scoped fan-out of change notifications.

Why this exists rather than Supabase Realtime
---------------------------------------------
Realtime solves the problem of writes arriving from many places — browsers,
edge functions, other services — where the database is the only point they all
pass through. In this system every write goes through FastAPI: the ElevenLabs
webhook, the Twilio callback, and every authenticated request. FastAPI is
already that common point, and it is holding the event before Postgres has even
been told about it. Routing the news back out through the database, its
replication stream and a separate websocket service is a longer path to
deliver something this process already knows.

Keeping it here also keeps the two properties the rest of the backend is built
around. `authenticated` needs no table grants (see migrations/001_rls.sql), and
every read of patient data still goes through TenantScope, where it can be
audited — a browser subscribed straight to Postgres would read PHI without
anything in Python ever seeing it.

What is published, and what is not
----------------------------------
An Event carries a name and a row id. It does not carry the row. A client that
receives one re-fetches through the normal audited route, which means the
notification stream cannot become an unaudited side channel for PHI — and
`call_logs.transcript` is exactly the PHI in question.

That discipline only holds if the Event stays this shape. Adding a `payload`
field is how it stops holding.

Scaling past one worker
-----------------------
Delivery is in-process. Today that is correct: the container runs a single
uvicorn worker. With two, a webhook can land on worker A while the browser's
stream is held by worker B, and B never hears about it.

`publish` is the seam for that. Swapping it for Postgres LISTEN/NOTIFY — no new
infrastructure, since Postgres is already here — means reimplementing this one
method and its delivery side. Nothing that calls `publish` has to change, which
is the reason handlers call it rather than touching `_subscribers` themselves.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, Iterator

logger = logging.getLogger(__name__)

# Bounded, so one stalled reader cannot grow this process without limit. On
# overflow the oldest notification is dropped rather than the newest: a client
# that is behind wants to know the current state, and since every event means
# "re-fetch", the newest one subsumes the ones it displaced.
_QUEUE_SIZE: Final[int] = 32


@dataclass(frozen=True, slots=True)
class Event:
    """Something changed. Deliberately not what it changed to.

    `name` is the SSE event type the browser switches on, e.g.
    "call_log.updated". `entity_id` is the row, so a client can decide whether
    it cares before re-fetching.
    """

    name: str
    entity_id: str


class EventBroker:
    """Delivers events to the streams belonging to one tenant."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- lifecycle ----------------------------------------------------------

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the serving loop, so `publish` can cross into it from a
        worker thread. Called once from the application lifespan."""
        self._loop = loop

    def unbind(self) -> None:
        self._loop = None
        self._subscribers.clear()

    # -- subscribing --------------------------------------------------------

    @contextmanager
    def subscribe(self, doctor_id: str) -> Iterator[asyncio.Queue[Event]]:
        """Yield a queue receiving this tenant's events, removed on exit.

        A context manager rather than a pair of methods because the removal is
        the part that matters: a stream that ends without it — client hung up,
        generator cancelled, handler raised — leaks a queue that is filled
        forever and read never.
        """
        if not doctor_id:
            raise ValueError("subscribe requires a non-empty doctor_id")

        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers[doctor_id].add(queue)
        try:
            yield queue
        finally:
            listeners = self._subscribers.get(doctor_id)
            if listeners is not None:
                listeners.discard(queue)
                # Drop the tenant entirely once nobody is listening, so the
                # dict tracks live streams rather than everyone ever seen.
                if not listeners:
                    self._subscribers.pop(doctor_id, None)

    # -- publishing ---------------------------------------------------------

    def publish(self, doctor_id: str, event: Event) -> None:
        """Deliver `event` to that tenant's streams. Safe from any thread.

        Route handlers are sync `def` and run in a threadpool, so a direct
        `put_nowait` from one would be touching loop-owned objects from the
        wrong thread. `call_soon_threadsafe` is what makes the call site
        ordinary.

        Never raises. A notification is an optimisation over polling, and
        failing a webhook — which the provider would then retry — because the
        UI missed a nudge would be the wrong trade.
        """
        if not doctor_id:
            return

        loop = self._loop
        if loop is None:
            # No server running: unit tests, or a publish during shutdown.
            # Delivery is in-thread and safe precisely because there is no
            # loop to race with.
            self._deliver(doctor_id, event)
            return

        try:
            loop.call_soon_threadsafe(self._deliver, doctor_id, event)
        except RuntimeError:
            # Loop already closed. Shutdown in progress; nothing to notify.
            logger.debug("Dropped %s: event loop closed", event.name)

    def _deliver(self, doctor_id: str, event: Event) -> None:
        for queue in self._subscribers.get(doctor_id, ()):
            if queue.full():
                # Discard the oldest to make room. See _QUEUE_SIZE.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - raced empty
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - raced full
                logger.warning("Dropped %s for a saturated stream", event.name)

    # -- introspection ------------------------------------------------------

    def stream_count(self, doctor_id: str) -> int:
        """Live streams for one tenant. For tests and health reporting."""
        return len(self._subscribers.get(doctor_id, ()))


# One per process. Imported by the webhook handlers that publish and by the
# route that subscribes.
broker = EventBroker()
