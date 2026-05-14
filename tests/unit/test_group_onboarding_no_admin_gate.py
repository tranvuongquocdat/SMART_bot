"""group_onboarding.start must not refuse based on bot admin status."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.group_onboarding as group_onboarding


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
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_start_continues_when_bot_not_admin(setup_db, monkeypatch):
    """Bot status is 'member' (not admin) → onboarding still picks up; no early return
    that asks the user to promote the bot."""
    monkeypatch.setattr(group_onboarding.telegram, "get_bot_id", AsyncMock(return_value="bot-1"))
    monkeypatch.setattr(
        group_onboarding.telegram, "get_chat_member",
        AsyncMock(return_value={"status": "member"}),
    )
    send_mock = AsyncMock()
    monkeypatch.setattr(group_onboarding, "_send_and_save", send_mock)

    await group_onboarding.start("group-xyz", "sender-1")

    for call in send_mock.await_args_list:
        msg = call.args[1] if len(call.args) > 1 else ""
        assert "Administrator" not in msg, f"unexpected admin prompt: {msg}"
    msgs = [c.args[1] for c in send_mock.await_args_list if len(c.args) > 1]
    assert any("workspace" in m.lower() or "thuộc workspace" in m for m in msgs), \
        f"workspace prompt missing; sent: {msgs}"
