"""Regression guard: _build_turn_messages must include recent message history.

Structural rule from feedback_message_semantics.md — any LLM call path is required to
carry recent conversational context. Future refactors that strip history break this test."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext


def _ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="b1", is_group=False, group_name="",
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
    for role, text in [
        ("user", "first msg"),
        ("assistant", "ack"),
        ("user", "second msg"),
        ("assistant", "ack2"),
    ]:
        await conn.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) "
            "VALUES ('b1', ?, ?, datetime('now'))", (role, text),
        )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_build_turn_messages_includes_recent_history(setup_db, monkeypatch):
    """_build_turn_messages must surface recent DB messages into the LLM prompt."""
    from src.agent import secretary_agent
    from src.config import Settings

    monkeypatch.setattr(secretary_agent, "_settings", Settings())
    monkeypatch.setattr(
        "src.agent.secretary_agent.qdrant.search", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.agent.secretary_agent._build_people_summary",
        AsyncMock(return_value="(no people)"),
    )

    built = {
        "memberships": [],
        "language": "vi",
        "active_sessions": {
            "reset_pending": None, "join_pending": [], "approvals_pending": [],
        },
        "last_5_messages": [],
        "primary_workspace_id": "b1",
    }

    messages, recent_count, _rag_count = await secretary_agent._build_turn_messages(
        _ctx(), text="third msg", chat_id="b1", is_group=False,
        built=built, group_ctx=None,
    )

    assert recent_count >= 2, f"expected ≥2 recent messages, got {recent_count}"

    blob = "\n".join(
        (m.get("content") or "") if isinstance(m, dict) else "" for m in messages
    )
    assert "first msg" in blob or "second msg" in blob, (
        "_build_turn_messages must surface recent history into the prompt; "
        f"got: {blob[:500]}"
    )
