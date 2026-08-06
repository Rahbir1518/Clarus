"""Live notifications.

Two properties matter here and neither is about latency:

  * a stream only ever receives its own tenant's events, and
  * an event carries no row data, so the stream cannot become an unaudited
    path to PHI.

The rest — heartbeats, lifetime caps — is about surviving proxies and expiring
tokens, and is tested by reading a whole short-lived stream.
"""
import asyncio

import pytest

from app.api.routes import events as events_route
from app.events.broker import Event, EventBroker

ALICE = "user_2alice"
BOB = "user_2bob"


@pytest.fixture
def broker() -> EventBroker:
    """Unbound, so delivery is synchronous and these tests need no loop."""
    return EventBroker()


# -- fan-out ----------------------------------------------------------------


def test_an_event_reaches_only_its_own_tenant(broker):
    with broker.subscribe(ALICE) as mine, broker.subscribe(BOB) as theirs:
        broker.publish(ALICE, Event("call_log.updated", "call-1"))

        assert mine.get_nowait().entity_id == "call-1"
        assert theirs.empty()


def test_every_stream_of_one_tenant_is_notified(broker):
    """Two tabs, both open on the calls page."""
    with broker.subscribe(ALICE) as first, broker.subscribe(ALICE) as second:
        broker.publish(ALICE, Event("call_log.updated", "call-1"))

        assert first.get_nowait().entity_id == "call-1"
        assert second.get_nowait().entity_id == "call-1"


def test_publishing_to_nobody_is_not_an_error(broker):
    """The common case: a call completes while no one is looking."""
    broker.publish(ALICE, Event("call_log.updated", "call-1"))
    assert broker.stream_count(ALICE) == 0


def test_an_empty_tenant_key_is_refused(broker):
    with pytest.raises(ValueError):
        with broker.subscribe(""):
            pass  # pragma: no cover


def test_a_closed_stream_stops_receiving(broker):
    with broker.subscribe(ALICE):
        pass
    assert broker.stream_count(ALICE) == 0

    # Would raise or leak if the queue were still registered.
    broker.publish(ALICE, Event("call_log.updated", "call-1"))


def test_a_stalled_reader_keeps_the_newest_event(broker):
    """A client that stopped reading must not grow this process without limit.

    Every event means "re-fetch", so the newest subsumes what it displaced —
    dropping the oldest keeps the queue bounded without the client ending up
    on stale state."""
    with broker.subscribe(ALICE) as queue:
        for n in range(200):
            broker.publish(ALICE, Event("call_log.updated", f"call-{n}"))

        assert queue.qsize() <= 32
        drained = [queue.get_nowait().entity_id for _ in range(queue.qsize())]
        assert drained[-1] == "call-199"


# -- what a frame may contain ----------------------------------------------


def test_a_frame_carries_an_id_and_no_row_data():
    """call_logs.transcript is PHI. If a payload ever reaches the wire, the
    stream has become a path to patient data that no audit record observes."""
    frame = events_route._frame(Event("call_log.updated", "call-1")).decode()

    assert frame == 'event: call_log.updated\ndata: {"id": "call-1"}\n\n'
    assert "transcript" not in frame


# -- the endpoint -----------------------------------------------------------


def test_the_stream_requires_a_token(unauthenticated_client):
    assert unauthenticated_client.get("/api/events").status_code == 401


def test_the_stream_heartbeats_and_then_asks_to_reconnect(
    client, auth_header, monkeypatch
):
    """Both behaviours exist for something outside this process: proxies drop
    idle connections, and the Clerk token is never re-verified once the stream
    is open."""
    monkeypatch.setattr(events_route, "_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(events_route, "_MAX_STREAM_SECONDS", 0.3)

    response = client.get("/api/events", headers=auth_header(ALICE))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    # Buffering proxies turn a live stream into a slow batch.
    assert response.headers["x-accel-buffering"] == "no"

    body = response.text
    assert body.startswith(": connected\n\n")
    assert ": ping\n\n" in body
    assert body.endswith("event: reconnect\ndata: {}\n\n")


def test_a_finished_stream_leaves_nothing_behind(client, auth_header, monkeypatch):
    monkeypatch.setattr(events_route, "_MAX_STREAM_SECONDS", 0.1)

    client.get("/api/events", headers=auth_header(ALICE))

    assert events_route.broker.stream_count(ALICE) == 0


# -- the webhook publishes --------------------------------------------------


def test_a_call_outcome_notifies_the_owning_tenant(client, fake_db, monkeypatch):
    """End to end: the provider posts an outcome, and the doctor who owns that
    call log is the one told about it."""
    received: list[tuple[str, Event]] = []
    monkeypatch.setattr(
        events_route.broker,
        "publish",
        lambda doctor_id, event: received.append((doctor_id, event)),
    )

    fake_db.store["call_logs"] = [
        {
            "id": "call-1",
            "doctor_id": ALICE,
            "conversation_id": "conv_abc",
            "status": "pending",
        }
    ]

    from app.db.system import update_call_log_by_conversation

    row = update_call_log_by_conversation(fake_db, "conv_abc", {"status": "completed"})
    events_route.broker.publish(
        row["doctor_id"], Event("call_log.updated", row["id"])
    )

    assert received == [(ALICE, Event("call_log.updated", "call-1"))]


def test_publishing_never_raises_after_the_loop_closes():
    """A publish during shutdown must not turn into a failed webhook, which
    the provider would answer by retrying."""
    broker = EventBroker()
    loop = asyncio.new_event_loop()
    broker.bind(loop)
    loop.close()

    broker.publish(ALICE, Event("call_log.updated", "call-1"))
