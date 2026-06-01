"""DMResponder end-to-end (mocked LLM + memory + retriever)."""

from __future__ import annotations

import asyncio

import pytest

import src.tools  # noqa: F401 — register tools
from src.agents import dm_responder as dm_mod  # noqa: F401 — register op
from src.agents.dispatcher import OperationDispatcher
from src.agents.registry import OperationRegistry
from src.events.bus import InMemoryEventBus
from src.llm.base import LLMResponse, LLMUsage


class _FakeMem:
    async def recall(self, scope, query, boss_id, k=5):
        return []

    async def write(self, scope, content, boss_id, meta=None, key=None):
        class _M:
            id = 1

        return _M()

    async def forget(self, memory_id, boss_id):
        return None


class _FakeLLM:
    def __init__(self, content="Chào anh"):
        self._content = content
        self.calls = 0

    async def complete(self, req):
        self.calls += 1
        return LLMResponse(
            content=self._content,
            tool_calls=[],
            usage=LLMUsage(10, 5, 0, 100, "gpt-4o-mini", "openai_compat"),
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
async def test_dm_responder_replies_to_boss_dm(db_pool, boss_user):
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM("Chào anh"), _FakeMem())

    # Ensure DMResponder op is registered.
    assert any(
        op._op_config.name == "dm_responder" for op in OperationRegistry.all()
    )

    disp = OperationDispatcher(bus, state)
    disp.attach_all()

    sent: list[dict] = []

    async def collect(p):
        sent.append(p)

    bus.subscribe("outbound.send", collect)

    await bus.publish(
        "message.captured",
        {
            "message_id": 1,
            "boss_id": boss_user["id"],
            "provider": "zalo",
            "chat_id": "boss-dm",
            "chat_type": "dm",
            "sender_is_boss": True,
            "text": "Hi",
            "mentions_bot": False,
        },
    )
    # Give in-memory bus a moment in case of any sub-task scheduling.
    await asyncio.sleep(0)

    assert any(s["content"] == "Chào anh" for s in sent), sent


@pytest.mark.asyncio
async def test_dm_responder_skips_non_boss_dm(db_pool, boss_user):
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM("X"), _FakeMem())
    OperationDispatcher(bus, state).attach_all()

    sent: list[dict] = []
    bus.subscribe(
        "outbound.send", lambda p: sent.append(p) or asyncio.sleep(0)
    )

    await bus.publish(
        "message.captured",
        {
            "boss_id": boss_user["id"],
            "provider": "zalo",
            "chat_id": "boss-dm",
            "chat_type": "dm",
            "sender_is_boss": False,
            "text": "ignore me",
        },
    )
    await asyncio.sleep(0)
    assert sent == []


@pytest.mark.asyncio
async def test_dm_responder_skips_group(db_pool, boss_user):
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM("X"), _FakeMem())
    OperationDispatcher(bus, state).attach_all()

    sent: list[dict] = []
    bus.subscribe(
        "outbound.send", lambda p: sent.append(p) or asyncio.sleep(0)
    )

    await bus.publish(
        "message.captured",
        {
            "boss_id": boss_user["id"],
            "provider": "zalo",
            "chat_id": "team",
            "chat_type": "group",
            "sender_is_boss": True,
            "text": "anything",
        },
    )
    await asyncio.sleep(0)
    assert sent == []
