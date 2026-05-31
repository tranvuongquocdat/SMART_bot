from src.llm.base import ChatMessage
from src.llm.cache_hint import mark_cache_breakpoint


def test_no_hint_no_op():
    msgs = [ChatMessage(role="system", content="hello")]
    out = mark_cache_breakpoint(msgs, None)
    assert all(not m.cache_breakpoint for m in out)


def test_after_system_marks_system_message():
    msgs = [
        ChatMessage(role="system", content="rules"),
        ChatMessage(role="user", content="hi"),
    ]
    out = mark_cache_breakpoint(msgs, "after_system")
    assert out[0].cache_breakpoint is True
    assert out[1].cache_breakpoint is False


def test_after_semantic_memory_marks_user_message():
    msgs = [
        ChatMessage(role="system", content="rules"),
        ChatMessage(role="user", content="mem"),
        ChatMessage(role="user", content="actual"),
    ]
    out = mark_cache_breakpoint(msgs, "after_semantic_memory")
    # Marks the first user message within first 4 messages
    assert out[1].cache_breakpoint is True
