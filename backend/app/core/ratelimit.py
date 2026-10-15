"""A small in-memory sliding-window rate limiter, and who is being limited.

Enough for the public routes this API has: the contact form and the call
links a patient opens. It lives in the process, so the
counts reset on restart and are per worker: run several workers or instances
and each keeps its own tally. That is a softer limit, not a hole — every
instance still refuses a flood — and the moment it matters the store can move
to Redis behind the same `hit()` call.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request

from app.core.config import Settings


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        # The right-most entry is the one our own proxy appended; anything to
        # its left came from the client and can say whatever it likes.
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def hit(self, rules: list[tuple[str, int, float]]) -> float | None:
        """Record one attempt against every rule, or refuse it.

        Each rule is (key, limit, window_seconds). If any rule is already at
        its limit nothing is recorded and the seconds until that rule frees up
        are returned; otherwise the attempt counts against all of them and the
        result is None. All-or-nothing, so a refused request never uses up
        allowance on the rules it did pass.
        """
        now = self._clock()
        with self._lock:
            retry_after = 0.0
            for key, limit, window in rules:
                hits = self._prune(key, now, window)
                if len(hits) >= limit:
                    retry_after = max(retry_after, hits[0] + window - now)
            if retry_after > 0:
                return retry_after
            for key, _, _ in rules:
                self._hits.setdefault(key, deque()).append(now)
            return None

    def _prune(self, key: str, now: float, window: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
