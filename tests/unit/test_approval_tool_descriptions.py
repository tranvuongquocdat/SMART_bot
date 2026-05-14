"""Approval-tool descriptions must communicate the gate to the LLM."""
from src.agent.tool_definitions import TOOL_DEFINITIONS


def _desc(name: str) -> str:
    for t in TOOL_DEFINITIONS:
        fn = t.get("function", {})
        if fn.get("name") == name:
            return fn.get("description", "")
    raise AssertionError(f"tool {name} not in TOOL_DEFINITIONS")


def test_approve_join_description_mentions_pending_and_boss():
    d = _desc("approve_join").lower()
    assert "pending" in d
    assert "only" in d or "must" in d


def test_reject_join_description_mentions_pending_and_boss():
    d = _desc("reject_join").lower()
    assert "pending" in d


def test_approve_task_change_description_mentions_pending():
    d = _desc("approve_task_change").lower()
    assert "pending" in d


def test_reject_task_change_description_mentions_pending():
    d = _desc("reject_task_change").lower()
    assert "pending" in d
