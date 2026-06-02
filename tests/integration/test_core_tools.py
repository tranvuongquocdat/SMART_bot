"""Smoke tests for each of the 16 core tools (Task D0).

LLM, memory, retrieval, qdrant, and external HTTP are mocked. Postgres + the
real tool registry are exercised end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio

import src.tools  # noqa: F401 — force-import core tools so @tool decorators run
from src.events.bus import InMemoryEventBus
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.messages import MessagesRepo
from src.tools import registry
from src.tools.base import ToolContext


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeMemory:
    def __init__(self):
        self.store: dict[int, dict[str, Any]] = {}
        self._next_id = 1

    async def write(self, scope, content, boss_id, meta=None, key=None):
        mid = self._next_id
        self._next_id += 1
        self.store[mid] = {
            "id": mid,
            "scope": scope,
            "content": content,
            "boss_id": boss_id,
            "key": key,
        }

        @dataclass
        class _M:
            id: int

        return _M(id=mid)

    async def forget(self, memory_id, boss_id):
        self.store.pop(memory_id, None)


class _FakePipeline:
    async def run(self, query, retr_ctx):
        from src.retrieval.base import Hit

        return [
            Hit(
                message_id=1,
                score=0.9,
                text=f"match for {query}",
                sender="alice",
                ts="2026-06-01T10:00:00+00:00",
                source="fake",
            )
        ]


async def _fake_retriever_factory(feature: str):
    return _FakePipeline()


class _FakeLLM:
    """Always returns a deterministic content; tools should not call this directly,
    but services do (e.g. NoteService.update). Keep it tiny."""

    async def complete(self, req):
        from src.llm.base import LLMResponse, LLMUsage

        return LLMResponse(
            content="updated note",
            tool_calls=[],
            usage=LLMUsage(0, 0, 0, 0, "fake", "fake"),
            status="ok",
        )

    async def embed(self, texts, model):
        return [[0.0] * 8 for _ in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tool_ctx(db_pool, boss_user) -> ToolContext:
    return ToolContext(
        boss_id=boss_user["id"],
        boss_role="boss",
        pool=db_pool,
        qdrant=None,
        bus=InMemoryEventBus(),
        memory=_FakeMemory(),
        retriever_factory=_fake_retriever_factory,
        llm=_FakeLLM(),
        trace_id="trace-test",
        span_id="span-test",
    )


def _h(name: str):
    return registry.get(name).handler


# ---------------------------------------------------------------------------
# Registration count
# ---------------------------------------------------------------------------


def test_sixteen_core_tools_registered():
    expected = {
        # memory
        "remember",
        "forget",
        # search
        "search_history",
        "find_exact_quote",
        "count_messages",
        # notes
        "read_group_note",
        "refresh_group_note",
        "edit_group_note",
        "pin_message",
        "unpin_message",
        # action items
        "list_action_items",
        "mark_action_item",
        # reminders
        "set_reminder",
        "list_reminders",
        "cancel_reminder",
        # meta
        "list_groups",
        "current_time",
        # web
        "fetch_url",
    }
    registered = set(registry._REGISTRY.keys())
    missing = expected - registered
    assert not missing, f"missing tools: {missing}"


def test_count_matches_spec_at_least_16():
    # Plan/spec calls for ≥16 named tools (we have 17 incl. fetch_url; +1 count_messages).
    assert len(registry._REGISTRY) >= 16


# ---------------------------------------------------------------------------
# memory.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remember(tool_ctx):
    r = await _h("remember")(ctx=tool_ctx, key="preferred_name", value="Đạt")
    assert r.content["key"] == "preferred_name"
    assert "memory_id" in r.content


@pytest.mark.asyncio
async def test_forget(tool_ctx):
    saved = await _h("remember")(ctx=tool_ctx, key="alias:Tân", value="Nguyễn Văn Tân")
    r = await _h("forget")(ctx=tool_ctx, memory_id=saved.content["memory_id"])
    assert r.content == {"ok": True}


# ---------------------------------------------------------------------------
# search.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_history(tool_ctx):
    r = await _h("search_history")(ctx=tool_ctx, query="báo cáo Q2")
    assert isinstance(r.content, list)
    assert r.content[0]["text"].startswith("match for")


@pytest.mark.asyncio
async def test_search_history_with_filters_passes_to_retriever(tool_ctx):
    """search_history forwards with_users / after / before into RetrievalContext."""
    captured: dict = {}

    class _CapturePipeline:
        async def run(self, query, retr_ctx):
            captured["with_users"] = retr_ctx.with_users
            captured["after"] = retr_ctx.after
            captured["before"] = retr_ctx.before
            captured["chat_id"] = retr_ctx.chat_id
            return []

    async def _factory(feature: str):
        return _CapturePipeline()

    tool_ctx.retriever_factory = _factory
    await _h("search_history")(
        ctx=tool_ctx,
        query="x",
        group_id="g1",
        with_users=["Tuấn Anh"],
        after="2026-05-01",
        before="2026-06-01",
    )
    assert captured["with_users"] == ["Tuấn Anh"]
    assert captured["after"] == datetime(2026, 5, 1)
    assert captured["before"] == datetime(2026, 6, 1)
    assert captured["chat_id"] == "g1"


@pytest.mark.asyncio
async def test_count_messages(tool_ctx, db_pool, boss_user):
    from src.domain.message import NewMessage

    repo = MessagesRepo(
        db_pool, BossContext(boss_user["id"], "boss")
    )
    base = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    for i, (sender, ts_offset) in enumerate(
        [("Tuấn Anh", 0), ("Tuấn Anh", 1), ("Lan", 2), ("Tuấn Anh", -40 * 24)]
    ):
        await repo.insert(
            NewMessage(
                provider="zalo",
                chat_id="g1",
                chat_type="group",
                provider_msg_id=f"m{i}",
                sender_provider_id=None,
                sender_name=sender,
                text=f"msg {i}",
                media_kind=None,
                media_url=None,
                media_text=None,
                ts=base + timedelta(hours=ts_offset),
            )
        )

    # No filter → 4
    r = await _h("count_messages")(ctx=tool_ctx)
    assert r.content["count"] == 4

    # Filter by sender → 3 Tuấn Anh
    r = await _h("count_messages")(ctx=tool_ctx, with_users=["Tuấn Anh"])
    assert r.content["count"] == 3

    # Filter by sender + time window (only the 2 inside the window)
    r = await _h("count_messages")(
        ctx=tool_ctx,
        with_users=["Tuấn Anh"],
        after="2026-05-01",
        before="2026-06-01",
    )
    assert r.content["count"] == 2


@pytest.mark.asyncio
async def test_find_exact_quote(tool_ctx, db_pool, boss_user):
    # Insert a message so FTS has something to match.
    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id,
                                  sender_provider_id, sender_name, text, media_kind, ts)
            VALUES ($1,'zalo','g1','group','p1','u1','Alice','báo cáo quý hai phải xong',
                    'text', NOW())
            """,
            boss_user["id"],
        )
    r = await _h("find_exact_quote")(ctx=tool_ctx, fragment="báo cáo quý hai")
    assert isinstance(r.content, list)


# ---------------------------------------------------------------------------
# notes.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_group_note(tool_ctx, db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    repo = GroupNotesRepo(db_pool, ctx)
    await repo.insert(provider="zalo", chat_id="g1", group_name="Sales")
    r = await _h("read_group_note")(ctx=tool_ctx, group_id="g1")
    assert r.content["group_name"] == "Sales"


@pytest.mark.asyncio
async def test_refresh_group_note(tool_ctx, db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    await GroupNotesRepo(db_pool, ctx).insert(
        provider="zalo", chat_id="g2", group_name="Ops"
    )
    fired: list[dict] = []

    async def collect(payload):
        fired.append(payload)

    tool_ctx.bus.subscribe("op.note_updater.fire", collect)
    r = await _h("refresh_group_note")(ctx=tool_ctx, group_id="g2")
    assert r.content["queued"] is True
    assert fired and fired[0]["reason"] == "on_demand"


@pytest.mark.asyncio
async def test_edit_group_note(tool_ctx, db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    await GroupNotesRepo(db_pool, ctx).insert(
        provider="zalo", chat_id="g3", group_name="Edit"
    )
    r = await _h("edit_group_note")(
        ctx=tool_ctx,
        group_id="g3",
        section_key="todo",
        new_content="- new item",
    )
    assert r.content == {"ok": True}
    note = await GroupNotesRepo(db_pool, ctx).get_by_chat("g3")
    assert "section:todo" in note.content
    assert "todo" in note.manually_edited_sections


@pytest.mark.asyncio
async def test_pin_message(tool_ctx, db_pool, boss_user):
    async with db_pool.acquire() as c:
        msg_id = await c.fetchval(
            """
            INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id,
                                  sender_provider_id, sender_name, text, media_kind, ts)
            VALUES ($1,'zalo','g4','group','p9','u1','Alice','important','text', NOW())
            RETURNING id
            """,
            boss_user["id"],
        )
    r = await _h("pin_message")(ctx=tool_ctx, message_id=msg_id, note="key info")
    assert isinstance(r.content["pin_id"], int)


@pytest.mark.asyncio
async def test_unpin_message(tool_ctx, db_pool, boss_user):
    async with db_pool.acquire() as c:
        msg_id = await c.fetchval(
            """
            INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id,
                                  sender_provider_id, sender_name, text, media_kind, ts)
            VALUES ($1,'zalo','g5','group','p1','u1','Alice','x','text', NOW())
            RETURNING id
            """,
            boss_user["id"],
        )
    pin_r = await _h("pin_message")(ctx=tool_ctx, message_id=msg_id)
    r = await _h("unpin_message")(ctx=tool_ctx, pin_id=pin_r.content["pin_id"])
    assert r.content == {"ok": True}


# ---------------------------------------------------------------------------
# action_items.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_action_items_empty(tool_ctx):
    r = await _h("list_action_items")(ctx=tool_ctx)
    assert r.content == []


@pytest.mark.asyncio
async def test_mark_action_item(tool_ctx, db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    gn_id = await GroupNotesRepo(db_pool, ctx).insert(
        provider="zalo", chat_id="g6", group_name="X"
    )
    async with db_pool.acquire() as c:
        item_id = await c.fetchval(
            """
            INSERT INTO action_items (boss_id, group_note_id, text, source)
            VALUES ($1,$2,'do thing','llm') RETURNING id
            """,
            boss_user["id"],
            gn_id,
        )
    r = await _h("mark_action_item")(ctx=tool_ctx, item_id=item_id, status="done")
    assert r.content == {"ok": True}
    async with db_pool.acquire() as c:
        status = await c.fetchval(
            "SELECT status FROM action_items WHERE id=$1", item_id
        )
    assert status == "done"


# ---------------------------------------------------------------------------
# reminders.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_cancel_reminder(tool_ctx, db_pool, boss_user):
    iso = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
    r = await _h("set_reminder")(
        ctx=tool_ctx,
        text="nộp báo cáo Q2",
        due_at_iso=iso,
        scope="dm",
        target_chat_id="boss-dm",
    )
    rid = r.content["reminder_id"]
    assert isinstance(rid, int)
    r2 = await _h("list_reminders")(ctx=tool_ctx)
    assert any(item["id"] == rid for item in r2.content)
    r3 = await _h("cancel_reminder")(ctx=tool_ctx, reminder_id=rid)
    assert r3.content == {"ok": True}


# ---------------------------------------------------------------------------
# meta.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_groups(tool_ctx, db_pool, boss_user):
    ctx = BossContext(boss_user["id"], "boss")
    await GroupNotesRepo(db_pool, ctx).insert(
        provider="zalo", chat_id="g7", group_name="Hello"
    )
    r = await _h("list_groups")(ctx=tool_ctx)
    assert any(g["group_name"] == "Hello" for g in r.content)


@pytest.mark.asyncio
async def test_current_time(tool_ctx):
    r = await _h("current_time")(ctx=tool_ctx)
    assert "iso" in r.content
    assert "tz" in r.content


# ---------------------------------------------------------------------------
# web.py — mock httpx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_url(tool_ctx, monkeypatch):
    class _Resp:
        text = "<html><head><title>Hi</title></head><body>World</body></html>"
        headers = {"content-type": "text/html"}

    class _AC:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", _AC)
    r = await _h("fetch_url")(ctx=tool_ctx, url="https://example.test")
    assert r.content["title"] == "Hi"
    assert "World" in r.content["text"]
