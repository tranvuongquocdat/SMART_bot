"""create_task posts a summary into the source group when ctx.is_group."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import tasks_service


def _group_ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="group-xyz", is_group=True, group_name="Test Group",
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


async def test_create_task_posts_in_group(in_memory_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.tasks_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.lark.search_records",
        AsyncMock(return_value=[]),
    )
    sent = AsyncMock()
    monkeypatch.setattr("src.services.tasks_service.telegram.send", sent)

    await tasks_service.create_task(
        _group_ctx(), name="prepare deck",
        assignee="Lan", deadline="2026-05-15",
    )

    group_calls = [c for c in sent.await_args_list if c.args[0] == "group-xyz"]
    assert group_calls, "no message posted into the source group"
    msg = group_calls[0].args[1]
    assert "prepare deck" in msg
    assert "Lan" in msg
