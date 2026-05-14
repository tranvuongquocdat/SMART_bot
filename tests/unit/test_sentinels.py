"""Sentinel parsing for inline file references in messages.content."""
from src.utils.sentinels import parse_sentinels, strip_sentinels, SentinelRef


def test_strip_returns_empty_string_unchanged():
    assert strip_sentinels("") == ""


def test_strip_no_sentinel_returns_text():
    assert strip_sentinels("hello world") == "hello world"


def test_strip_removes_whole_line_sentinel():
    text = "Tóm tắt giúp\n[OPENAI_FILE: file_id=file-x mime=application/pdf filename=a.pdf]"
    assert strip_sentinels(text) == "Tóm tắt giúp"


def test_strip_keeps_inline_lookalike():
    text = "Anh thấy chuỗi [OPENAI_FILE: file_id=x] trong log không?"
    assert strip_sentinels(text) == text


def test_strip_collapses_blank_lines():
    text = "Line A\n[LOCAL_IMAGE: path=/x mime=image/jpeg]\n\nLine B"
    assert strip_sentinels(text) == "Line A\n\nLine B"


def test_parse_no_sentinel():
    cleaned, refs = parse_sentinels("plain text")
    assert cleaned == "plain text"
    assert refs == []


def test_parse_openai_file_sentinel():
    text = "Câu hỏi\n[OPENAI_FILE: file_id=file-abc mime=application/pdf filename=invoice.pdf]"
    cleaned, refs = parse_sentinels(text)
    assert cleaned == "Câu hỏi"
    assert len(refs) == 1
    assert refs[0] == SentinelRef(
        kind="OPENAI_FILE",
        fields={"file_id": "file-abc", "mime": "application/pdf", "filename": "invoice.pdf"},
    )


def test_parse_local_image_sentinel():
    text = "[LOCAL_IMAGE: path=data/inbound/abc/1_p.jpg mime=image/jpeg]"
    cleaned, refs = parse_sentinels(text)
    assert cleaned == ""
    assert refs == [SentinelRef(
        kind="LOCAL_IMAGE",
        fields={"path": "data/inbound/abc/1_p.jpg", "mime": "image/jpeg"},
    )]


def test_parse_multiple_sentinels():
    text = (
        "So sánh 2 file\n"
        "[OPENAI_FILE: file_id=file-1 mime=application/pdf filename=a.pdf]\n"
        "[OPENAI_FILE: file_id=file-2 mime=application/pdf filename=b.pdf]"
    )
    cleaned, refs = parse_sentinels(text)
    assert cleaned == "So sánh 2 file"
    assert len(refs) == 2
    assert refs[0].fields["file_id"] == "file-1"
    assert refs[1].fields["file_id"] == "file-2"
