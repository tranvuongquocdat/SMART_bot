import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_ctx(boss_chat_id=1):
    ctx = MagicMock()
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"
    ctx.sender_chat_id = boss_chat_id
    ctx.boss_chat_id = boss_chat_id
    ctx.boss_name = "Boss"
    ctx.sender_type = "boss"
    return ctx


_TASK_A = {"Tên task": "Task A", "Status": "Đang làm", "Assignee": "Alice", "Deadline": 9999999999999}
_TASK_B = {"Tên task": "Task B", "Status": "Hoàn thành", "Assignee": "Bob", "Deadline": 9999999999999}


@pytest.mark.asyncio
async def test_get_summary_current_workspace():
    from src.tools.summary import get_summary
    ctx = _make_ctx()
    with patch("src.tools.summary.lark.search_records", new_callable=AsyncMock,
               return_value=[_TASK_A, _TASK_B]):
        result = await get_summary(ctx, summary_type="today", workspace_ids="current")
    assert "Task A" in result


@pytest.mark.asyncio
async def test_get_summary_all_workspaces_tags_workspace_name():
    from src.tools.summary import get_summary
    ctx = _make_ctx()
    ws = {
        "workspace_name": "Công ty X",
        "lark_base_token": "tok2",
        "lark_table_tasks": "tbl2",
    }
    with patch("src.tools.summary.resolve_workspaces", new_callable=AsyncMock, return_value=[ws]), \
         patch("src.tools.summary.lark.search_records", new_callable=AsyncMock,
               return_value=[_TASK_A]):
        result = await get_summary(ctx, summary_type="today", workspace_ids="all")
    assert "[Công ty X]" in result
    assert "Task A" in result
