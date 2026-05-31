"""OperationDispatcher integration with InMemoryEventBus.

Uses Postgres pool from conftest to exercise build_context's UsersRepo lookup.
"""

import asyncio
from dataclasses import dataclass

import pytest

from src.agents import registry as op_reg
from src.agents.context import current
from src.agents.dispatcher import OperationDispatcher
from src.agents.registry import operation
from src.events.bus import InMemoryEventBus


@dataclass
class _Deps:
    boss: object
    bus: object
    db: object


class _State:
    def __init__(self, db_pool, bus):
        self.db_pool = db_pool
        self.bus = bus
        self.memory_provider = None
        self.llm_gateway = None
        self.qdrant = None


@pytest.fixture(autouse=True)
def _clear_reg():
    snap = dict(op_reg._OP_REGISTRY)
    op_reg._OP_REGISTRY.clear()
    yield
    op_reg._OP_REGISTRY.clear()
    op_reg._OP_REGISTRY.update(snap)


@pytest.mark.asyncio
async def test_dispatcher_routes_event_to_op(boss_user, db_pool):
    received: list[dict] = []
    trace_seen: list = []

    @operation(
        name="echo_op",
        triggered_by=["evt.echo"],
        deps_type=_Deps,
        prompt_key="p.echo",
        feature="responder",
    )
    class EchoOp:
        async def handle(self, event, ctx):
            received.append({"event": event, "boss_id": ctx.boss.id})
            trace_seen.append(current())

    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    disp = OperationDispatcher(bus, state)
    disp.attach_all()

    await bus.publish("evt.echo", {"boss_id": boss_user["id"], "payload": "x"})

    assert len(received) == 1
    assert received[0]["boss_id"] == boss_user["id"]
    assert trace_seen[0] is not None
    assert trace_seen[0].op_name == "echo_op"


@pytest.mark.asyncio
async def test_dispatcher_when_predicate_filters(boss_user, db_pool):
    received: list[dict] = []

    @operation(
        name="filtered_op",
        triggered_by=["evt.filtered"],
        when=lambda e: e.get("flag") is True,
        deps_type=_Deps,
        prompt_key="p.f",
        feature="responder",
    )
    class FOp:
        async def handle(self, event, ctx):
            received.append(event)

    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    disp = OperationDispatcher(bus, state)
    disp.attach_all()

    await bus.publish("evt.filtered", {"boss_id": boss_user["id"], "flag": False})
    await bus.publish("evt.filtered", {"boss_id": boss_user["id"], "flag": True})

    assert len(received) == 1
    assert received[0]["flag"] is True


@pytest.mark.asyncio
async def test_concurrency_gate_per_bot_account(boss_user, db_pool):
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    @operation(
        name="bounded_op",
        triggered_by=["evt.bounded"],
        deps_type=_Deps,
        prompt_key="p.b",
        feature="responder",
        max_concurrency_per_bot_account=2,
    )
    class BOp:
        async def handle(self, event, ctx):
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1

    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    disp = OperationDispatcher(bus, state)
    disp.attach_all()

    await asyncio.gather(
        *(
            bus.publish(
                "evt.bounded",
                {"boss_id": boss_user["id"], "bot_account_id": 7, "i": i},
            )
            for i in range(5)
        )
    )
    assert peak <= 2
