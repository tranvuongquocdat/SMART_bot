"""Per-thread spacing + jitter for the Zalo demo throttle."""
from __future__ import annotations

import asyncio
import time

import pytest

from src.channels.zalo_bridge.rate_limiter import ZaloRateLimiter


async def test_consecutive_sends_to_same_thread_are_spaced():
    rl = ZaloRateLimiter(per_thread_interval_s=0.1, jitter_s=(0.0, 0.0))
    t0 = time.monotonic()
    await rl.acquire("T1")  # first call: no wait
    await rl.acquire("T1")  # second call: must wait ≥ 0.1s
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.1, f"expected ≥0.1s, got {elapsed:.3f}s"


async def test_different_threads_dont_block_each_other():
    rl = ZaloRateLimiter(per_thread_interval_s=0.5, jitter_s=(0.0, 0.0))
    # Prime each thread.
    await rl.acquire("T1")
    await rl.acquire("T2")
    # Send to T3 — fresh thread, should be near-instant.
    t0 = time.monotonic()
    await rl.acquire("T3")
    assert (time.monotonic() - t0) < 0.05


async def test_concurrent_sends_to_same_thread_serialize():
    rl = ZaloRateLimiter(per_thread_interval_s=0.1, jitter_s=(0.0, 0.0))
    t0 = time.monotonic()
    await asyncio.gather(rl.acquire("T1"), rl.acquire("T1"), rl.acquire("T1"))
    # 3 sends to the same thread → 2 inter-message waits of 0.1s each.
    assert (time.monotonic() - t0) >= 0.2


async def test_jitter_adds_delay_within_range():
    rl = ZaloRateLimiter(per_thread_interval_s=0.0, jitter_s=(0.05, 0.06))
    t0 = time.monotonic()
    await rl.acquire("T1")
    elapsed = time.monotonic() - t0
    assert 0.04 <= elapsed <= 0.08, f"jitter out of expected range: {elapsed:.3f}s"
