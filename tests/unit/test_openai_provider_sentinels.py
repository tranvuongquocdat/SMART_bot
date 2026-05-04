"""OpenAILLMClient parses sentinels into chat.completions content parts."""
from pathlib import Path

from src.infrastructure.llm.openai import _inject_file_parts


def test_no_sentinel_passthrough():
    msg = {"role": "user", "content": "plain hello"}
    out = _inject_file_parts(msg)
    assert out.get("content") == "plain hello"


def test_assistant_with_string_passthrough():
    msg = {"role": "assistant", "content": "OK đã ghi note rồi anh"}
    out = _inject_file_parts(msg)
    assert out["content"] == "OK đã ghi note rồi anh"


def test_openai_file_sentinel_becomes_file_part():
    msg = {
        "role": "user",
        "content": "Tóm tắt giúp\n[OPENAI_FILE: file_id=file-xx mime=application/pdf filename=a.pdf]",
    }
    out = _inject_file_parts(msg)
    assert out["content"] == [
        {"type": "text", "text": "Tóm tắt giúp"},
        {"type": "file", "file": {"file_id": "file-xx"}},
    ]


def test_local_image_sentinel_becomes_image_url(tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(b"\xff\xd8\xffhello")
    msg = {
        "role": "user",
        "content": f"đọc giúp\n[LOCAL_IMAGE: path={img} mime=image/jpeg]",
    }
    out = _inject_file_parts(msg)
    parts = out["content"]
    assert parts[0] == {"type": "text", "text": "đọc giúp"}
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_local_image_missing_falls_back_to_text():
    msg = {
        "role": "user",
        "content": "[LOCAL_IMAGE: path=/tmp/does-not-exist-xyz.jpg mime=image/jpeg]",
    }
    out = _inject_file_parts(msg)
    assert out["content"] == [{"type": "text", "text": "[Ảnh đã hết hạn]"}]


def test_non_string_content_passthrough():
    msg = {"role": "tool", "content": "raw tool output"}
    msg2 = {"role": "user", "content": [{"type": "text", "text": "already parts"}]}
    assert _inject_file_parts(msg) == msg
    assert _inject_file_parts(msg2) == msg2


def test_non_dict_message_passthrough():
    # OpenAI returns ChatCompletionMessage Pydantic instances after a tool
    # round; secretary_agent appends them to the messages list as-is.
    class FakePydanticMsg:
        role = "assistant"
        content = "OK đã ghi"
    obj = FakePydanticMsg()
    assert _inject_file_parts(obj) is obj
