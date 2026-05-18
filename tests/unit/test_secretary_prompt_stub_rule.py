"""Regression: secretary prompt must teach the LLM how to handle people who
have never DM'd the bot (no Chat ID). Without this rule the LLM refuses or
routes around assignment for unknown names."""
from src.agent.secretary_agent import SECRETARY_PROMPT


def test_prompt_contains_stub_section_heading():
    assert "## Người chưa onboard" in SECRETARY_PROMPT


def test_prompt_states_chat_id_is_optional():
    assert "không nhất thiết" in SECRETARY_PROMPT and "Chat ID" in SECRETARY_PROMPT


def test_prompt_has_four_step_resolution_flow():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 2000]
    for marker in ("1.", "2.", "3.", "4."):
        assert marker in block, f"missing step marker {marker!r}"


def test_prompt_covers_duplicate_name_disambiguation():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 2000]
    assert "trùng nhiều" in block.lower()


def test_prompt_covers_fuzzy_match_confirmation():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 2000]
    assert "fuzzy" in block.lower() or "gần đúng" in block


def test_prompt_covers_bulk_team_add():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 2000]
    assert "danh sách" in block.lower() and "add_people" in block
