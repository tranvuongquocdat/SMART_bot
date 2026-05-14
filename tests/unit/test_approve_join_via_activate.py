"""approve_join must call membership_service.activate(source='approval')."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import join_service


def _boss_ctx(boss_id="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss_id, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss_id, boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss_id, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status, request_info) "
        "VALUES ('u1', 'b1', 'member', 'Alice', 'pending', 'Hi please add')"
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_approve_join_routes_through_activate(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.join_service.membership_service.activate", activate_mock,
    )

    result = await join_service.approve_join(
        _boss_ctx(), membership_chat_id="u1",
    )
    activate_mock.assert_awaited_once()
    kwargs = activate_mock.await_args.kwargs
    assert kwargs["chat_id"] == "u1"
    assert kwargs["boss_chat_id"] == "b1"
    assert kwargs["source"] == "approval"
    assert kwargs["person_type"] == "member"
    assert "Approved" in result


async def test_approve_join_refuses_when_no_pending(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.join_service.membership_service.activate", activate_mock,
    )
    result = await join_service.approve_join(
        _boss_ctx(), membership_chat_id="does-not-exist",
    )
    activate_mock.assert_not_awaited()
    assert "No pending" in result
