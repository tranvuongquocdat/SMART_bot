import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src import onboarding

@pytest.fixture(autouse=True)
def clear_sessions():
    onboarding._join_sessions.clear()
    yield
    onboarding._join_sessions.clear()

@pytest.mark.asyncio
async def test_list_companies_starts_join_flow():
    with patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock,
               return_value=[{"chat_id": "1", "name": "Anh X", "company": "Công ty A"}]):
        reply = await onboarding.handle_join_inquiry(chat_id=999)
    assert "Công ty A" in reply
    assert 999 in onboarding._join_sessions
    assert onboarding._join_sessions[999]["step"] == "pick_company"

@pytest.mark.asyncio
async def test_no_companies_returns_empty_message():
    with patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock, return_value=[]):
        reply = await onboarding.handle_join_inquiry(chat_id=999)
    assert 999 not in onboarding._join_sessions
    assert "chưa có" in reply.lower() or "không có" in reply.lower()

@pytest.mark.asyncio
async def test_pick_company_step():
    onboarding._join_sessions[999] = {
        "step": "pick_company",
        "bosses": [{"chat_id": "1", "name": "Anh X", "company": "Công ty A"}]
    }
    with patch("src.onboarding._ai_classify", new_callable=AsyncMock,
               return_value={"index": 0}):
        reply = await onboarding.handle_join_message("Công ty A", chat_id=999)
    assert onboarding._join_sessions[999]["step"] == "pick_role"
    assert onboarding._join_sessions[999]["target_boss"]["chat_id"] == "1"

@pytest.mark.asyncio
async def test_pick_role_member():
    onboarding._join_sessions[999] = {
        "step": "pick_role",
        "target_boss": {"chat_id": "1", "company": "Công ty A"}
    }
    reply = await onboarding.handle_join_message("nhân viên", chat_id=999)
    assert onboarding._join_sessions[999]["step"] == "get_info"
    assert onboarding._join_sessions[999]["role"] == "member"

@pytest.mark.asyncio
async def test_pick_role_partner():
    onboarding._join_sessions[999] = {
        "step": "pick_role",
        "target_boss": {"chat_id": "1", "company": "Công ty A"}
    }
    reply = await onboarding.handle_join_message("đối tác", chat_id=999)
    assert onboarding._join_sessions[999]["role"] == "partner"

@pytest.mark.asyncio
async def test_get_info_creates_pending_membership():
    onboarding._join_sessions[999] = {
        "step": "get_info",
        "role": "partner",
        "target_boss": {"chat_id": "1", "name": "Anh X", "company": "Công ty A"}
    }
    with patch("src.onboarding._ai_classify", new_callable=AsyncMock,
               return_value={"name": "Anh Bình"}), \
         patch("src.onboarding.db.upsert_membership", new_callable=AsyncMock) as mock_upsert, \
         patch("src.onboarding.tg.send_message", new_callable=AsyncMock):
        reply = await onboarding.handle_join_message("Tôi là Bình, freelance design", chat_id=999)
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args
    assert "pending" in str(call_kwargs)
    assert 999 not in onboarding._join_sessions  # session cleaned up

@pytest.mark.asyncio
async def test_boss_approve_activates_membership():
    with patch("src.onboarding.db.get_membership", new_callable=AsyncMock,
               return_value={"chat_id": "999", "boss_chat_id": "1",
                             "person_type": "partner", "name": "Anh Bình",
                             "status": "pending", "request_info": "freelance"}), \
         patch("src.onboarding.db.get_boss", new_callable=AsyncMock,
               return_value={"chat_id": "1", "name": "Anh X", "company": "Co A",
                             "lark_base_token": "tok", "lark_table_people": "tp"}), \
         patch("src.onboarding.db.upsert_membership", new_callable=AsyncMock) as mock_upsert, \
         patch("src.onboarding.lark.create_record", new_callable=AsyncMock,
               return_value={"record_id": "lr1"}), \
         patch("src.onboarding.tg.send_message", new_callable=AsyncMock):
        reply = await onboarding.handle_boss_join_decision("approve 999", boss_chat_id="1")
    assert reply is not None
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args
    assert "active" in str(call_kwargs)

@pytest.mark.asyncio
async def test_boss_reject_rejects_membership():
    with patch("src.onboarding.db.get_membership", new_callable=AsyncMock,
               return_value={"chat_id": "999", "boss_chat_id": "1",
                             "person_type": "partner", "name": "Anh Bình",
                             "status": "pending", "request_info": "test"}), \
         patch("src.onboarding.db.get_boss", new_callable=AsyncMock,
               return_value={"chat_id": "1", "name": "Anh X", "company": "Co A"}), \
         patch("src.onboarding.db.upsert_membership", new_callable=AsyncMock) as mock_upsert, \
         patch("src.onboarding.tg.send_message", new_callable=AsyncMock):
        reply = await onboarding.handle_boss_join_decision("reject 999", boss_chat_id="1")
    assert reply is not None
    call_kwargs = mock_upsert.call_args
    assert "rejected" in str(call_kwargs)

@pytest.mark.asyncio
async def test_non_join_decision_returns_none():
    reply = await onboarding.handle_boss_join_decision("hello world", boss_chat_id="1")
    assert reply is None
