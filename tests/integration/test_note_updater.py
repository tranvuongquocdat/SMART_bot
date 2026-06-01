"""NoteUpdater integration: trigger + LLM-driven rebuild."""

from __future__ import annotations

import asyncio

import pytest

import src.agents  # noqa: F401 — register ops
from src.agents.dispatcher import OperationDispatcher
from src.agents.triggers import TriggerEngine
from src.events.bus import InMemoryEventBus
from src.llm.base import LLMResponse, LLMUsage
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo


class _FakeMem:
    async def recall(self, *a, **kw):
        return []


class _FakeLLM:
    async def complete(self, req):
        return LLMResponse(
            content="## Cần xử lý\n- new bullet from delta",
            tool_calls=[],
            usage=LLMUsage(0, 0, 0, 0, "fake", "fake"),
            status="ok",
        )

    async def embed(self, texts, model):
        return [[0.0] * 8 for _ in texts]


class _State:
    def __init__(self, db_pool, bus, llm, memory):
        self.db_pool = db_pool
        self.bus = bus
        self.llm_gateway = llm
        self.memory_provider = memory
        self.qdrant = None
        self.retriever_factory = None


@pytest.mark.asyncio
async def test_note_updater_on_demand_rebuild(db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    repo = GroupNotesRepo(db_pool, ctx)
    nid = await repo.insert(provider="zalo", chat_id="g-note", group_name="N")

    # Seed messages
    async with db_pool.acquire() as c:
        for i in range(3):
            await c.execute(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type,
                                      provider_msg_id, sender_name, text, media_kind, ts)
                VALUES ($1,'zalo','g-note','group',$2,'Alice',$3,'text', NOW())
                """,
                boss_user["id"],
                f"p{i}",
                f"msg {i}",
            )

    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM(), _FakeMem())
    OperationDispatcher(bus, state).attach_all()

    note_updated = []

    async def collect(p):
        note_updated.append(p)

    bus.subscribe("note.updated", collect)

    # Simulate on-demand fire (from refresh_group_note tool).
    await bus.publish(
        "op.note_updater.fire",
        {
            "reason": "on_demand",
            "boss_id": boss_user["id"],
            "source_event": {
                "boss_id": boss_user["id"],
                "provider": "zalo",
                "chat_id": "g-note",
            },
        },
    )
    await asyncio.sleep(0)

    note = await repo.get(nid)
    assert "new bullet" in (note.content or "")
    assert note.last_seen_message_id is not None
    assert note_updated and note_updated[0]["group_note_id"] == nid


@pytest.mark.asyncio
async def test_note_updater_threshold_fires_via_trigger_engine(db_pool, boss_user):
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM(), _FakeMem())

    fires: list[dict] = []

    async def collect(p):
        fires.append(p)

    bus.subscribe("op.note_updater.fire", collect)

    engine = TriggerEngine(bus)
    engine.attach_all()

    # Threshold = 30 messages. Fire 30 group messages.
    for i in range(30):
        await bus.publish(
            "message.captured",
            {
                "boss_id": boss_user["id"],
                "chat_id": "g-note",
                "chat_type": "group",
                "provider": "zalo",
                "text": f"m{i}",
            },
        )
    await asyncio.sleep(0)

    assert any(f["reason"] == "threshold" for f in fires), fires


@pytest.mark.asyncio
async def test_trigger_engine_when_filters_dm(db_pool, boss_user):
    """when=lambda chat_type=='group' should filter out dm-typed events."""
    bus = InMemoryEventBus()
    fires: list[dict] = []
    bus.subscribe("op.note_updater.fire", lambda p: fires.append(p) or asyncio.sleep(0))
    engine = TriggerEngine(bus)
    engine.attach_all()

    for _ in range(40):  # well above threshold
        await bus.publish(
            "message.captured",
            {
                "boss_id": boss_user["id"],
                "chat_id": "boss-dm",
                "chat_type": "dm",
                "provider": "zalo",
                "text": "x",
            },
        )
    await asyncio.sleep(0)
    assert fires == []
