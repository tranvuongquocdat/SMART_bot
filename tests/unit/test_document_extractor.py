import pytest

from src.media.adapters.document import DocumentExtractor


@pytest.mark.asyncio
async def test_txt_extract():
    res = await DocumentExtractor().extract(content=b"hello\tworld", content_type="text/plain")
    assert "hello" in res.media_text


@pytest.mark.asyncio
async def test_unknown_kind_empty():
    res = await DocumentExtractor().extract(content=b"x", content_type="application/zip")
    assert res.media_text == ""


@pytest.mark.asyncio
async def test_kind_detected_from_url_extension():
    # content present but no content-type → detect 'txt' from .txt extension
    res = await DocumentExtractor().extract(content=b"abc", url="https://x/file.txt")
    assert "abc" in res.media_text
