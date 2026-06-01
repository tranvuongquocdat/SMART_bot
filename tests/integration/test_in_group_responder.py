"""InGroupResponder end-to-end (mocked LLM + memory)."""

from __future__ import annotations

import asyncio

import pytest

import src.agents  # noqa: F401 — register all ops
import src.tools  # noqa: F401 — register tools
from src.agents.dispatcher import OperationDispatcher
from src.agents.registry import OperationRegistry
from src.events.bus import InMemoryEventBus
from src.llm.base import LLMResponse, LLMUsage


class _FakeMem:
    async def recall(self, *a, **kw):
        return []

    async def write(self, scope, content, boss_id, meta=None, key=None):
        class _M:
            id = 1

        return _M()

    async def forget(self, *a, **kw):
        return None


class _FakeLLM:
    def __init__(self, content="OK"):
        self._content = content

    async def complete(self, req):
        return LLMResponse(
            content=self._content,
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


def _ensure_registered():
    names = {op._op_config.name for op in OperationRegistry.all()}
    assert "in_group_responder" in names


@pytest.mark.asyncio
async def test_in_group_responder_replies_on_mention(db_pool, boss_user):
    _ensure_registered()
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM("Vâng, em hiểu."), _FakeMem())
    OperationDispatcher(bus, state).attach_all()

    # Insert a real source message so FK reply_to_message_id resolves.
    async with db_pool.acquire() as c:
        src_msg_id = await c.fetchval(
            """
            INSERT INTO messages (boss_id, provider, chat_id, chat_type,
                                  provider_msg_id, sender_name, text, media_kind, ts)
            VALUES ($1,'zalo','team-a','group','pmsg42','Boss','...','text', NOW())
            RETURNING id
            """,
            boss_user["id"],
        )

    sent: list[dict] = []

    async def collect(p):
        sent.append(p)

    bus.subscribe("outbound.send", collect)

    await bus.publish(
        "message.captured",
        {
            "boss_id": boss_user["id"],
            "provider": "zalo",
            "chat_id": "team-a",
            "chat_type": "group",
            "mentions_bot": True,
            "sender_is_boss": False,
            "text": (
                "Bot ơi check giúp anh em xem số liệu Q2 năm 2026 đầy đủ"
                " các tháng được không nhỉ?"
            ),  # > 60 chars → triggers quick_ack
            "message_id": src_msg_id,
        },
    )
    await asyncio.sleep(0)

    triggers = [s["trigger"] for s in sent]
    # > 60 chars → quick_ack first, then mention reply.
    assert "quick_ack" in triggers
    assert "mention" in triggers
    answer = next(s for s in sent if s["trigger"] == "mention")
    assert answer["content"] == "Vâng, em hiểu."
    assert answer["reply_to_message_id"] == src_msg_id


@pytest.mark.asyncio
async def test_in_group_responder_skips_when_not_mentioned(db_pool, boss_user):
    _ensure_registered()
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM(), _FakeMem())
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
            "chat_id": "team-a",
            "chat_type": "group",
            "mentions_bot": False,
            "text": "không tag bot",
        },
    )
    await asyncio.sleep(0)
    assert sent == []


@pytest.mark.asyncio
async def test_in_group_short_message_no_quick_ack(db_pool, boss_user):
    _ensure_registered()
    bus = InMemoryEventBus()
    state = _State(db_pool, bus, _FakeLLM("OK"), _FakeMem())
    OperationDispatcher(bus, state).attach_all()

    sent: list[dict] = []

    async def collect(p):
        sent.append(p)

    bus.subscribe("outbound.send", collect)
    await bus.publish(
        "message.captured",
        {
            "boss_id": boss_user["id"],
            "provider": "zalo",
            "chat_id": "team-a",
            "chat_type": "group",
            "mentions_bot": True,
            "text": "hi bot",  # < 60 chars
        },
    )
    await asyncio.sleep(0)
    triggers = [s["trigger"] for s in sent]
    assert "quick_ack" not in triggers
    assert "mention" in triggers
