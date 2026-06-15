"""Chỉ thị ngôn ngữ trả lời của bot từ cài đặt users.language."""
from src.agents.agent_loop import _bot_language_directive


def test_vi_directive():
    d = _bot_language_directive("vi")
    assert d and "tiếng Việt" in d


def test_en_directive():
    d = _bot_language_directive("en")
    assert d and "English" in d


def test_auto_and_none_no_directive():
    assert _bot_language_directive("auto") is None
    assert _bot_language_directive(None) is None
    assert _bot_language_directive("") is None
