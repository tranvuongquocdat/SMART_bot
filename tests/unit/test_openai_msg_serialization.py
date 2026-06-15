"""Assistant turns carrying tool_calls must serialize per OpenAI spec."""
from src.llm.base import ChatMessage, ToolCall
from src.llm.clients.openai_compat import OpenAICompatibleClient


def test_assistant_with_tool_calls_serialized():
    m = ChatMessage(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="call_1", name="set_reminder", arguments={"khi": "3pm"})],
    )
    d = OpenAICompatibleClient._to_openai_msg(m)
    assert d["content"] is None
    assert d["tool_calls"][0]["id"] == "call_1"
    assert d["tool_calls"][0]["function"]["name"] == "set_reminder"
    assert '"khi"' in d["tool_calls"][0]["function"]["arguments"]


def test_tool_result_keeps_call_id():
    m = ChatMessage(role="tool", content="ok", tool_call_id="call_1")
    d = OpenAICompatibleClient._to_openai_msg(m)
    assert d == {"role": "tool", "content": "ok", "tool_call_id": "call_1"}


def test_plain_assistant_unchanged():
    m = ChatMessage(role="assistant", content="xin chào")
    d = OpenAICompatibleClient._to_openai_msg(m)
    assert d == {"role": "assistant", "content": "xin chào"}
