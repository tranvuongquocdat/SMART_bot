"""Tests for ToolDispatcher — registry hit, fallback path, error envelopes."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.agent_pkg.tool_dispatcher import ToolDispatcher
from src.context import ChatContext


def _ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="u1", sender_name="x", sender_type="boss",
        boss_chat_id="b1", boss_name="b",
        lark_base_token="", lark_table_people="", lark_table_tasks="",
        lark_table_projects="", lark_table_ideas="",
        lark_table_reminders="", lark_table_notes="",
        chat_id="c1", is_group=False, group_name="",
        messages_collection="m_b1_1536", tasks_collection="t_b1_1536",
        all_memberships=[],
    )


@dataclass
class _Fake:
    name: str
    return_value: str

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return self.return_value


@pytest.mark.asyncio
async def test_known_name_invokes_handler():
    d = ToolDispatcher([_Fake(name="t1", return_value="ok")])
    out = await d.execute("t1", {}, _ctx())
    assert out == "ok"


@pytest.mark.asyncio
async def test_unknown_name_returns_not_found_message():
    """Phase 4b-2b: legacy tools.execute_tool fallback removed; unknown names
    now return a static error string."""
    d = ToolDispatcher([])
    out = await d.execute("unknown_tool", {"x": 1}, _ctx())
    assert "không tồn tại" in out


@pytest.mark.asyncio
async def test_handler_exception_wrapped():
    class _Boom:
        name = "boom"
        async def handle(self, args, ctx):
            raise RuntimeError("kaboom")

    d = ToolDispatcher([_Boom()])
    out = await d.execute("boom", {}, _ctx())
    assert out.startswith("[TOOL_ERROR:unknown]")
    assert "kaboom" in out


@pytest.mark.asyncio
async def test_bad_json_args_returns_error():
    d = ToolDispatcher([_Fake(name="t1", return_value="ok")])
    out = await d.execute("t1", "not-json{", _ctx())
    assert "[TOOL_ERROR:bad_args]" in out


def test_duplicate_handler_name_raises():
    a = _Fake(name="dup", return_value="a")
    b = _Fake(name="dup", return_value="b")
    with pytest.raises(ValueError, match="duplicate handler name"):
        ToolDispatcher([a, b])
