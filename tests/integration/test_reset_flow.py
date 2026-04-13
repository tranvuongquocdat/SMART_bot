"""
Integration tests: reset workspace 2-step safety flow.
Tests the state machine in src/tools/reset.py using a mock ChatContext.
Lark API calls are patched out — we verify the session logic, not actual deletion.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.tools.reset import (
    is_reset_trigger,
    is_reset_session,
    start_reset,
    handle_reset_message,
    _reset_sessions,
    _clear,
)


def _make_ctx(boss_id=1001, company="Acme Corp"):
    ctx = MagicMock()
    ctx.boss_chat_id = boss_id
    ctx.sender_type = "boss"
    return ctx


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure reset sessions are clean before each test."""
    _reset_sessions.clear()
    yield
    _reset_sessions.clear()


# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------

def test_reset_trigger_keyword():
    assert is_reset_trigger("reset workspace") is True
    assert is_reset_trigger("/reset") is True
    assert is_reset_trigger("xóa toàn bộ dữ liệu workspace") is True
    assert is_reset_trigger("bình thường") is False
    assert is_reset_trigger("ok task blah") is False


# ---------------------------------------------------------------------------
# Step 1 — start_reset asks for company name in UPPERCASE
# ---------------------------------------------------------------------------

async def test_start_reset_asks_for_company_name():
    ctx = _make_ctx()
    mock_boss = {"company": "Acme Corp", "chat_id": 1001}

    with patch("src.tools.reset.db") as mock_db:
        mock_db.get_boss = AsyncMock(return_value=mock_boss)
        reply = await start_reset(ctx)

    assert "ACME CORP" in reply
    assert is_reset_session(1001) is True


async def test_start_reset_no_company_uses_chat_id():
    ctx = _make_ctx(company="")
    mock_boss = {"company": "", "chat_id": 1001}

    with patch("src.tools.reset.db") as mock_db:
        mock_db.get_boss = AsyncMock(return_value=mock_boss)
        reply = await start_reset(ctx)

    assert "1001" in reply
    assert is_reset_session(1001) is True


# ---------------------------------------------------------------------------
# Step 1 → wrong company name → cancel
# ---------------------------------------------------------------------------

async def test_wrong_company_name_cancels():
    ctx = _make_ctx()
    _reset_sessions[1001] = {"step": 1, "company": "Acme Corp"}

    reply = await handle_reset_message("wrong name", ctx)
    assert "huỷ" in reply.lower()
    assert is_reset_session(1001) is False


async def test_correct_company_name_advances_to_step2():
    ctx = _make_ctx()
    _reset_sessions[1001] = {"step": 1, "company": "Acme Corp"}

    reply = await handle_reset_message("ACME CORP", ctx)
    assert "tôi chắc chắn" in reply
    assert _reset_sessions[1001]["step"] == 2


# ---------------------------------------------------------------------------
# Step 2 → wrong confirmation → cancel
# ---------------------------------------------------------------------------

async def test_wrong_confirmation_cancels():
    ctx = _make_ctx()
    _reset_sessions[1001] = {"step": 2, "company": "Acme Corp"}

    reply = await handle_reset_message("tôi không chắc", ctx)
    assert "huỷ" in reply.lower()
    assert is_reset_session(1001) is False


async def test_correct_confirmation_triggers_reset():
    ctx = _make_ctx()
    _reset_sessions[1001] = {"step": 2, "company": "Acme Corp"}

    mock_boss = {
        "company": "Acme Corp",
        "lark_base_token": "tok_abc",
        "lark_table_people": "tbl_ppl",
        "lark_table_tasks": "tbl_tasks",
        "lark_table_projects": "tbl_proj",
        "lark_table_ideas": "tbl_ideas",
        "lark_table_reminders": "tbl_rem",
        "lark_table_notes": "tbl_notes",
    }

    with patch("src.tools.reset.db") as mock_db, \
         patch("src.tools.reset.lark") as mock_lark:
        mock_db.get_boss = AsyncMock(return_value=mock_boss)
        mock_lark.search_records = AsyncMock(return_value=[
            {"record_id": "r1"}, {"record_id": "r2"},
        ])
        mock_lark.delete_record = AsyncMock()
        reply = await handle_reset_message("tôi chắc chắn", ctx)

    assert "hoàn tất" in reply.lower() or "reset" in reply.lower()
    assert is_reset_session(1001) is False


# ---------------------------------------------------------------------------
# handle_reset_message returns None when no active session
# ---------------------------------------------------------------------------

async def test_no_session_returns_none():
    ctx = _make_ctx()
    result = await handle_reset_message("anything", ctx)
    assert result is None
