import asyncio

import pytest

from src.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_publish_subscribe():
    bus = InMemoryEventBus()
    received: list[dict] = []

    async def handler(payload):
        received.append(payload)

    bus.subscribe("test.event", handler)
    await bus.publish("test.event", {"x": 1})
    await asyncio.sleep(0.01)
    assert received == [{"x": 1}]


@pytest.mark.asyncio
async def test_concurrent_fanout():
    bus = InMemoryEventBus()
    counts = []

    async def h1(p):
        await asyncio.sleep(0.05)
        counts.append("h1")

    async def h2(p):
        counts.append("h2")

    bus.subscribe("e", h1)
    bus.subscribe("e", h2)
    await bus.publish("e", {})
    await asyncio.sleep(0.1)
    assert set(counts) == {"h1", "h2"}


@pytest.mark.asyncio
async def test_error_isolation():
    bus = InMemoryEventBus()
    good_received = []

    async def bad(p):
        raise RuntimeError("boom")

    async def good(p):
        good_received.append(p)

    bus.subscribe("e", bad)
    bus.subscribe("e", good)
    await bus.publish("e", {"ok": True})
    await asyncio.sleep(0.01)
    assert good_received == [{"ok": True}]
