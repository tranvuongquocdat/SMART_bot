"""Regression: tool descriptions must not contradict the secretary prompt's
stub-Person rule. Phrases that imply Chat ID is required, or that the
assignee must already exist, are forbidden."""
from src.agent.tool_definitions import TOOL_DEFINITIONS


def _tool(name: str) -> dict:
    for t in TOOL_DEFINITIONS:
        if t["function"]["name"] == name:
            return t["function"]
    raise AssertionError(f"tool {name!r} not found")


def test_create_task_assignee_does_not_require_existing_person():
    desc = _tool("create_task")["parameters"]["properties"]["assignee"]["description"]
    assert "dùng đúng tên trong danh sách nhân sự" not in desc


def test_create_task_assignee_mentions_add_people_fallback():
    desc = _tool("create_task")["parameters"]["properties"]["assignee"]["description"]
    assert "add_people" in desc


def test_create_reminder_does_not_require_chat_id():
    desc = _tool("create_reminder")["description"]
    assert "danh sách tên có Chat ID" not in desc


def test_create_reminder_mentions_add_people_fallback():
    desc = _tool("create_reminder")["description"]
    assert "add_people" in desc


def test_add_people_chat_id_is_channel_agnostic():
    desc = _tool("add_people")["parameters"]["properties"]["chat_id"]["description"]
    assert "Chat ID Telegram (nếu biết)" not in desc
    assert "bỏ trống" in desc
