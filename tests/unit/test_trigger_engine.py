import asyncio

import pytest

from src.agents import triggers as trig_mod
from src.agents.triggers import (
    Debounce,
    Threshold,
    TriggerEngine,
    parse_window,
    trigger,
)
from src.events.bus import InMemoryEventBus


@pytest.fixture(autouse=True)
def _clear_registry():
    snap = list(trig_mod._TRIGGER_REGISTRY)
    trig_mod._TRIGGER_REGISTRY.clear()
    yield
    trig_mod._TRIGGER_REGISTRY.clear()
    trig_mod._TRIGGER_REGISTRY.extend(snap)


def test_parse_window():
    assert parse_window("10s") == 10.0
    assert parse_window("5m") == 300.0
    assert parse_window("2h") == 7200.0
    assert parse_window("0.5") == 0.5


@pytest.mark.asyncio
async def test_threshold_fires_once_and_resets():
    @trigger(
        op="meeting_note",
        event="message.captured",
        threshold=Threshold(key="boss_id,chat_id", count=30),
    )
    class _T:
        pass

    bus = InMemoryEventBus()
    engine = TriggerEngine(bus)
    engine.attach_all()

    fired: list[dict] = []

    async def on_fire(payload):
        fired.append(payload)

    bus.subscribe("op.meeting_note.fire", on_fire)

    for _ in range(30):
        await bus.publish(
            "message.captured", {"boss_id": 1, "chat_id": "g1"}
        )
    assert len(fired) == 1
    assert fired[0]["reason"] == "threshold"
    assert fired[0]["boss_id"] == 1

    # Counter resets — next 29 should not fire
    for _ in range(29):
        await bus.publish(
            "message.captured", {"boss_id": 1, "chat_id": "g1"}
        )
    assert len(fired) == 1

    # The 30th after reset fires again
    await bus.publish("message.captured", {"boss_id": 1, "chat_id": "g1"})
    assert len(fired) == 2


@pytest.mark.asyncio
async def test_threshold_keyed_per_chat():
    @trigger(
        op="op_a",
        event="evt.x",
        threshold=Threshold(key="boss_id,chat_id", count=3),
    )
    class _T:
        pass

    bus = InMemoryEventBus()
    engine = TriggerEngine(bus)
    engine.attach_all()

    fired: list[dict] = []
    bus.subscribe("op.op_a.fire", lambda p: _append(fired, p))

    # 2 events in chat g1, 3 in g2 → only g2 fires
    await bus.publish("evt.x", {"boss_id": 1, "chat_id": "g1"})
    await bus.publish("evt.x", {"boss_id": 1, "chat_id": "g1"})
    await bus.publish("evt.x", {"boss_id": 1, "chat_id": "g2"})
    await bus.publish("evt.x", {"boss_id": 1, "chat_id": "g2"})
    await bus.publish("evt.x", {"boss_id": 1, "chat_id": "g2"})

    assert len(fired) == 1


async def _append(lst, p):
    lst.append(p)


@pytest.mark.asyncio
async def test_debounce_fires_after_window():
    @trigger(
        op="op_d",
        event="evt.d",
        debounce=Debounce(key="boss_id,chat_id", window="0.05s"),
    )
    class _T:
        pass

    bus = InMemoryEventBus()
    engine = TriggerEngine(bus)
    engine.attach_all()

    fired: list[dict] = []
    bus.subscribe("op.op_d.fire", lambda p: _append(fired, p))

    await bus.publish("evt.d", {"boss_id": 1, "chat_id": "g1"})
    await bus.publish("evt.d", {"boss_id": 1, "chat_id": "g1"})
    # Timer hasn't fired yet
    assert len(fired) == 0
    await asyncio.sleep(0.12)
    assert len(fired) == 1
    assert fired[0]["reason"] == "debounce"
