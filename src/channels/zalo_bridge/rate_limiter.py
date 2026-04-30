"""Minimal Zalo outbound throttle (per-thread spacing + jitter).

Scope (demo, 1 account): keep send cadence to any one thread looking
human-paced so Zalo's heuristic anti-spam doesn't flag the account.

Out of scope (Phase 6b proper):
  - Global per-account per-minute cap
  - Daily cap with calendar-day reset
  - Cross-account isolation
Those become meaningful only with multi-account.
"""
from __future__ import annotations

import asyncio
import random
import time


class ZaloRateLimiter:
    def __init__(
        self,
        per_thread_interval_s: float = 2.0,
        jitter_s: tuple[float, float] = (0.2, 0.8),
    ) -> None:
        self.per_thread_interval_s = per_thread_interval_s
        self.jitter_s = jitter_s
        self._last_send: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, thread_id: str) -> asyncio.Lock:
        lock = self._locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[thread_id] = lock
        return lock

    async def acquire(self, thread_id: str) -> None:
        async with self._lock_for(thread_id):
            now = time.monotonic()
            last = self._last_send.get(thread_id, 0.0)
            wait = self.per_thread_interval_s - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            lo, hi = self.jitter_s
            if hi > 0:
                await asyncio.sleep(random.uniform(lo, hi))
            self._last_send[thread_id] = time.monotonic()
