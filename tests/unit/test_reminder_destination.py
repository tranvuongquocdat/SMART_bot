"""Pure destination logic: target → source_group → boss."""
from src.agent.reminder_agent import _destination_for


def test_target_wins():
    row = {"target_chat_id": "user-xyz", "source_chat_id": "group-abc", "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "user-xyz"
    assert cc_boss is True


def test_source_group_when_no_target():
    row = {"target_chat_id": None, "source_chat_id": "group-abc", "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "group-abc"
    assert cc_boss is False


def test_boss_when_no_target_no_source():
    row = {"target_chat_id": None, "source_chat_id": None, "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "b1"
    assert cc_boss is False
