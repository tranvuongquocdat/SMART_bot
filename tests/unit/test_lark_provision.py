import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import src.services.lark as lark_svc

@pytest.mark.asyncio
async def test_provision_workspace_creates_6_tables():
    """provision_workspace should create People, Tasks, Projects, Ideas, Reminders, Notes"""
    with patch.object(lark_svc, "create_base", new_callable=AsyncMock,
                      return_value={"app_token": "base1", "default_table_id": "tbl0"}), \
         patch.object(lark_svc, "create_table", new_callable=AsyncMock) as mock_table, \
         patch.object(lark_svc, "delete_table", new_callable=AsyncMock), \
         patch.object(lark_svc, "_get_token", new_callable=AsyncMock, return_value="tok"):
        mock_table.side_effect = [
            {"table_id": "tbl1"},
            {"table_id": "tbl2"},
            {"table_id": "tbl3"},
            {"table_id": "tbl4"},
            {"table_id": "tbl5"},
            {"table_id": "tbl6"},
        ]
        result = await lark_svc.provision_workspace("Test Co")

    assert mock_table.call_count == 6
    assert "table_reminders" in result
    assert "table_notes" in result
    assert result["table_reminders"] == "tbl5"
    assert result["table_notes"] == "tbl6"

@pytest.mark.asyncio
async def test_provision_workspace_returns_all_keys():
    with patch.object(lark_svc, "create_base", new_callable=AsyncMock,
                      return_value={"app_token": "base1", "default_table_id": "tbl0"}), \
         patch.object(lark_svc, "create_table", new_callable=AsyncMock) as mock_table, \
         patch.object(lark_svc, "delete_table", new_callable=AsyncMock), \
         patch.object(lark_svc, "_get_token", new_callable=AsyncMock, return_value="tok"):
        mock_table.side_effect = [{"table_id": f"t{i}"} for i in range(1, 7)]
        result = await lark_svc.provision_workspace("Test Co")

    expected_keys = {"base_token", "table_people", "table_tasks",
                     "table_projects", "table_ideas", "table_reminders", "table_notes"}
    assert expected_keys == set(result.keys())
