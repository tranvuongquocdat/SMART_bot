"""reminder_service must inline-await Lark sync and persist lark_record_id.
On Lark failure: keep DB row, return graceful message; reconciler will retry."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import reminder_service


def _ctx(boss_chat_id="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss_chat_id,
        sender_name="Boss",
        sender_type="boss",
        boss_chat_id=boss_chat_id,
        boss_name="Boss",
        lark_base_token="base",
        lark_table_people="ppl",
        lark_table_tasks="tsk",
        lark_table_projects="prj",
        lark_table_ideas="idea",
        lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss_chat_id,
        is_group=False,
        group_name="",
        messages_collection="m",
        tasks_collection="t",
    )


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_create_reminder_persists_lark_record_id(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-123")
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark", sync_mock
    )
    async def _passthrough(fn, **kw):
        return await fn()
    monkeypatch.setattr("src.services.reminder_service.lark.with_retry", _passthrough)
    monkeypatch.setattr(
        "src.services.reminder_service.lark.search_records",
        AsyncMock(return_value=[]),
    )

    msg = await reminder_service.create_reminder(
        _ctx(), content="check email", remind_at="2026-05-04 10:00",
    )

    assert "Da tao nhac nho" in msg
    sync_mock.assert_awaited_once()
    async with in_memory_db.execute(
        "SELECT lark_record_id FROM reminders WHERE boss_chat_id = 'b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-123"


async def test_create_reminder_lark_failure_keeps_db_row(in_memory_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=Exception("Lark down")),
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.search_records",
        AsyncMock(return_value=[]),
    )

    msg = await reminder_service.create_reminder(
        _ctx(), content="check email", remind_at="2026-05-04 10:00",
    )

    assert "dang cho dong bo" in msg.lower() or "đang chờ đồng bộ" in msg.lower()
    async with in_memory_db.execute(
        "SELECT id, lark_record_id FROM reminders WHERE boss_chat_id = 'b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None  # DB row kept
    assert row["lark_record_id"] is None  # not synced
