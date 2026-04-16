import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def _llm_json(extracted: dict, reply: str):
    resp = MagicMock()
    resp.content = json.dumps({"extracted": extracted, "reply": reply})
    return resp, {}


_BOSSES = [{"chat_id": 100, "name": "Boss A", "company": "Alpha Corp",
            "lark_base_token": "tok", "lark_table_projects": "proj"}]


@pytest.mark.asyncio
async def test_workspace_selection_sets_boss_chat_id():
    from src import group_onboarding
    session = {
        "step": "collecting",
        "boss_chat_id": None,
        "project_id": None,
        "confirmed": None,
        "bosses": _BOSSES,
        "projects": [],
        "group_name": "Dev Group",
        "sender_id": 1,
    }
    extracted = {"boss_chat_id": 100, "project_id": None, "confirmed": None, "load_projects": True}
    saved = {}

    async def fake_save(gid, s):
        saved.update(s)

    with patch("src.group_onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=session), \
         patch("src.group_onboarding.db.save_onboarding_state", new_callable=AsyncMock,
               side_effect=fake_save), \
         patch("src.group_onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_json(extracted, "Chọn dự án nào?")), \
         patch("src.group_onboarding.lark.search_records", new_callable=AsyncMock,
               return_value=[{"Tên dự án": "Dự án X", "record_id": "rec1"}]), \
         patch("src.group_onboarding.telegram.send", new_callable=AsyncMock):
        await group_onboarding.handle("1", -100, "Dev Group")

    assert saved.get("boss_chat_id") == 100
    assert len(saved.get("projects", [])) == 1


@pytest.mark.asyncio
async def test_confirmation_triggers_complete_group():
    from src import group_onboarding
    session = {
        "step": "collecting",
        "boss_chat_id": 100,
        "project_id": "rec1",
        "confirmed": None,
        "bosses": _BOSSES,
        "projects": [{"name": "Dự án X", "record_id": "rec1"}],
        "group_name": "Dev Group",
        "sender_id": 1,
    }
    extracted = {"boss_chat_id": None, "project_id": None, "confirmed": True, "load_projects": False}

    with patch("src.group_onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=session), \
         patch("src.group_onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_json(extracted, "Đang setup...")), \
         patch("src.group_onboarding.telegram.send", new_callable=AsyncMock), \
         patch("src.group_onboarding._complete_group", new_callable=AsyncMock) as mock_cg:
        await group_onboarding.handle("có", -100, "Dev Group")

    mock_cg.assert_awaited_once()
