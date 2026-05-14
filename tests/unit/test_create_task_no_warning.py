"""create_task must not return any '⚠️' or 'không có trong danh sách' warning lines."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import tasks_service


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


async def test_create_task_no_warning_for_unknown_assignee(in_memory_db, monkeypatch):
    """Lark People returns empty (assignee not onboarded) → tool result has no warning lines."""
    monkeypatch.setattr(
        "src.services.tasks_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.lark.search_records",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.telegram.send", AsyncMock(),
    )

    msg = await tasks_service.create_task(
        _ctx(), name="prepare deck", assignee="Tân",
    )

    assert "⚠️" not in msg
    assert "không có trong danh sách" not in msg
    assert "chưa có tài khoản liên kết" not in msg
