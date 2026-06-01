"""In-memory sliding-window rate limiter.

Process-local — fine for MVP single-worker uvicorn. Swap for Redis-backed
limiter once we go horizontal.

Contract: ``await limiter.check(key, limit, window_sec) -> bool`` returns True
if the call is allowed (and records the hit) or False if the bucket is full.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Protocol


class RateLimiter(Protocol):
    async def check(self, key: str, limit: int, window_sec: int) -> bool: ...


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_sec: int) -> bool:
        now = time.time()
        cutoff = now - window_sec
        async with self._lock:
            bucket = [t for t in self._hits[key] if t > cutoff]
            if len(bucket) >= limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True
