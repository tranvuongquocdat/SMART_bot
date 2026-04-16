import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
import asyncio


def _make_ctx(sender_type="member"):
    ctx = MagicMock()
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"
    ctx.lark_table_people = "ppl"
    ctx.lark_table_projects = "proj"
    ctx.sender_type = sender_type
    ctx.sender_name = "Alice"
    ctx.sender_chat_id = 200
    ctx.boss_chat_id = 100
    ctx.boss_name = "Boss"
    ctx.is_group = False
    ctx.chat_id = 200
    return ctx


_TASK = {
    "record_id": "rec123",
    "Tên task": "Viết báo cáo",
    "Assignee": "Alice",
    "Status": "Đang làm",
    "Project": "Dự án X",
}


@pytest.mark.asyncio
async def test_non_boss_completion_notifies_boss():
    from src.tools import tasks
    ctx = _make_ctx(sender_type="member")

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[_TASK]), \
         patch("src.tools.tasks.lark.update_record", new_callable=AsyncMock), \
         patch("src.tools.tasks.telegram.send", new_callable=AsyncMock) as mock_send, \
         patch("src.tools.tasks.db_mod.log_outbound_dm", new_callable=AsyncMock), \
         patch("src.tools.tasks.db_mod.get_db", new_callable=AsyncMock), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("src.tools.tasks._notify_group_completion", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=lambda coro: (coro.close(), None)[1]):
        result = await tasks.update_task(ctx, search_keyword="báo cáo", status="Hoàn thành")

    # Should NOT go through approval path
    assert "Yêu cầu" not in result
    assert "Đã cập nhật" in result
    # Boss should be notified directly
    mock_send.assert_awaited()
    boss_calls = [c for c in mock_send.call_args_list if c.args[0] == 100]
    assert len(boss_calls) >= 1
    assert "hoàn thành" in str(boss_calls[0])


@pytest.mark.asyncio
async def test_boss_completion_no_cross_chat_notification():
    from src.tools import tasks
    ctx = _make_ctx(sender_type="boss")

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[_TASK]), \
         patch("src.tools.tasks.lark.update_record", new_callable=AsyncMock), \
         patch("src.tools.tasks.telegram.send", new_callable=AsyncMock) as mock_send, \
         patch("src.tools.tasks.db_mod.log_outbound_dm", new_callable=AsyncMock), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=lambda coro: (coro.close(), None)[1]):
        result = await tasks.update_task(ctx, search_keyword="báo cáo", status="Hoàn thành")

    assert "Đã cập nhật" in result
    # No completion notification message sent to boss
    for c in mock_send.call_args_list:
        assert "vừa hoàn thành" not in str(c)


@pytest.mark.asyncio
async def test_non_boss_other_change_still_uses_approval():
    from src.tools import tasks
    ctx = _make_ctx(sender_type="member")

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[_TASK]), \
         patch("src.tools.tasks.db_mod.create_approval", new_callable=AsyncMock), \
         patch("src.tools.tasks.db_mod.get_boss", new_callable=AsyncMock,
               return_value={"chat_id": 100, "company": "Acme"}), \
         patch("src.tools.tasks.telegram.send", new_callable=AsyncMock), \
         patch("src.tools.tasks.db_mod._db", MagicMock()):
        result = await tasks.update_task(ctx, search_keyword="báo cáo", deadline="2026-05-01")

    assert "Yêu cầu" in result
