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

# The regex parser `handle_boss_join_decision` was deleted as part of the
# relaxed-group-flow / approval-cleanup spec. Boss approvals now go through
# the LLM with conversational context (see spec §2.3 + feedback_message_semantics).
# Coverage moved to: tests/unit/test_handle_boss_join_decision_removed.py and
# tests/unit/test_approve_join_via_activate.py.
