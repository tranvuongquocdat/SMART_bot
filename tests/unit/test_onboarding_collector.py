import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def _llm_response(extracted: dict, reply: str):
    resp = MagicMock()
    resp.content = json.dumps({"extracted": extracted, "reply": reply})
    return resp, {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_first_message_shows_greeting():
    from src import onboarding
    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value={"first": True}), \
         patch("src.onboarding.db.save_onboarding_state", new_callable=AsyncMock), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response({}, "Xin chào!")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock) as mock_send:
        await onboarding.handle_onboard_message("hi", 999)
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_extracts_all_boss_fields_in_one_message():
    from src import onboarding
    extracted = {"type": "boss", "name": "Đạt", "company": "ABC Corp",
                 "language": "vi", "confirmed": None, "target_boss_id": None}
    state_saved = {}

    async def fake_save(chat_id, state):
        state_saved.update(state)

    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value={"first": False}), \
         patch("src.onboarding.db.save_onboarding_state", new_callable=AsyncMock,
               side_effect=fake_save), \
         patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock, return_value=[]), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response(extracted, "Tuyệt! Xác nhận tạo workspace?")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock):
        await onboarding.handle_onboard_message("tôi là sếp tên Đạt công ty ABC Corp", 999)

    assert state_saved.get("type") == "boss"
    assert state_saved.get("name") == "Đạt"
    assert state_saved.get("company") == "ABC Corp"


@pytest.mark.asyncio
async def test_confirmation_triggers_complete_boss():
    from src import onboarding
    extracted = {"type": None, "name": None, "company": None,
                 "language": None, "confirmed": True, "target_boss_id": None}
    existing_state = {"type": "boss", "name": "Đạt", "company": "ABC", "language": "vi", "confirmed": None}

    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=existing_state), \
         patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock, return_value=[]), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response(extracted, "Đang tạo workspace...")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock), \
         patch("src.onboarding._complete_boss", new_callable=AsyncMock) as mock_complete:
        await onboarding.handle_onboard_message("ok tạo đi", 999)

    mock_complete.assert_awaited_once()
