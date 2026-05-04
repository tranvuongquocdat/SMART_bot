"""note_service must inline-await Lark sync and persist lark_record_id."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest_asyncio
import pytest

import src.db as db
from src.context import ChatContext
from src.services import note_service


def _ctx(boss="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss, boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
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


async def _passthrough(fn, **kw):
    return await fn()


async def test_update_note_calls_sync_and_persists_id(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-1")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    monkeypatch.setattr("src.services.note_service.lark.with_retry", _passthrough)

    msg = await note_service.update_note(
        _ctx(), note_type="personal", ref_id="b1", content="hi",
    )
    assert "Đã cập nhật" in msg
    sync_mock.assert_awaited_once()

    async with in_memory_db.execute(
        "SELECT lark_record_id FROM notes WHERE boss_chat_id='b1' AND type='personal' AND ref_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-1"


async def test_append_note_calls_sync(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-2")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    monkeypatch.setattr("src.services.note_service.lark.with_retry", _passthrough)
    await note_service.update_note(_ctx(), note_type="personal", ref_id="b1", content="A")
    sync_mock.reset_mock()
    await note_service.append_note(_ctx(), note_type="personal", ref_id="b1", content="B")
    sync_mock.assert_awaited_once()
    fields = sync_mock.await_args.args[2]
    assert "A\n\nB" in fields["content"]


async def test_update_note_no_lark_table_skips_sync(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-x")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    ctx = _ctx()
    object.__setattr__(ctx, "lark_table_notes", "")  # tenant without notes table
    await note_service.update_note(ctx, note_type="personal", ref_id="b1", content="hi")
    sync_mock.assert_not_awaited()
