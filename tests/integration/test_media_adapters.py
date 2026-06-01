"""Integration tests for media adapters.

Image adapter is exercised with a fake LLM gateway (we don't burn vision
tokens in CI); URL fetching is mocked via ``respx``-style monkeypatching
of httpx where possible. Document adapters run against fixtures that are
generated at module import time so the repo stays small.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import src.media  # noqa: F401 — register adapters
from src.media.base import MediaExtractResult
from src.media.registry import _detect_from_url, find_adapter

FIXTURES = Path(__file__).parent.parent / "fixtures" / "media"


# --- registry --------------------------------------------------------------


def test_detect_url_kind():
    assert _detect_from_url("https://youtu.be/abc") == "youtube"
    assert _detect_from_url("https://www.youtube.com/watch?v=x") == "youtube"
    assert _detect_from_url("https://tiktok.com/@a/video/1") == "tiktok"
    assert _detect_from_url("https://example.com/page") == "url"


def test_find_adapter_by_kind():
    a = find_adapter(media_kind="url")
    assert a.__class__.__name__ == "WebExtractor"
    a2 = find_adapter(media_kind="pdf")
    assert a2.__class__.__name__ == "DocumentExtractor"
    a3 = find_adapter(media_kind="image")
    assert a3.__class__.__name__ == "ImageExtractor"


def test_find_adapter_unknown_kind_raises():
    with pytest.raises(LookupError):
        find_adapter(media_kind="quantumfax")


def test_find_adapter_from_url_only():
    a = find_adapter(url="https://youtube.com/x")
    assert a.__class__.__name__ == "WebExtractor"


# --- document ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_txt():
    a = find_adapter(media_kind="txt")
    result = await a.extract(
        content=b"Hello plain text fixture.\nLine two.\n",
        content_type="text/plain",
    )
    assert "Hello plain text fixture" in result.media_text
    assert "Line two" in result.media_text


@pytest.mark.asyncio
async def test_document_docx():
    a = find_adapter(media_kind="docx")
    data = (FIXTURES / "sample.docx").read_bytes()
    result = await a.extract(
        content=data,
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )
    assert "Hello world from docx fixture" in result.media_text


@pytest.mark.asyncio
async def test_document_xlsx():
    a = find_adapter(media_kind="xlsx")
    data = (FIXTURES / "sample.xlsx").read_bytes()
    result = await a.extract(
        content=data,
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    assert "apple" in result.media_text
    assert "banana" in result.media_text
    assert "Sheet1" in result.media_text


@pytest.mark.asyncio
async def test_document_pdf_blank():
    a = find_adapter(media_kind="pdf")
    data = (FIXTURES / "sample.pdf").read_bytes()
    result = await a.extract(content=data, content_type="application/pdf")
    # Blank PDF has no text but extract must not crash + extras carries pages.
    assert result.media_text == ""
    assert result.extra.get("pages") == 1


@pytest.mark.asyncio
async def test_document_detect_by_extension():
    """When content_type is missing, dispatch falls back to URL extension."""
    a = find_adapter(media_kind="txt")
    result = await a.extract(
        url="https://example.com/foo.txt",
        content=b"abc",
    )
    assert result.media_text == "abc"


# --- web --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_generic_url(monkeypatch: pytest.MonkeyPatch):
    a = find_adapter(media_kind="url")

    html = (
        "<html><head><title>Demo Title</title></head>"
        "<body><article><p>This is body text used by trafilatura.</p>"
        "<p>It has at least two paragraphs to satisfy thresholds.</p>"
        "</article></body></html>"
    )

    class _Resp:
        def __init__(self, text: str):
            self.text = text
            self.status_code = 200

        def raise_for_status(self) -> None:  # noqa: D401
            return None

    class _Client:
        def __init__(self, *a: Any, **kw: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a: Any):
            return None

        async def get(self, url: str):
            return _Resp(html)

    monkeypatch.setattr("src.media.adapters.web.httpx.AsyncClient", _Client)
    result = await a.extract(url="https://example.com/post")
    assert "Demo Title" == result.title
    # trafilatura may or may not catch tiny HTML; ensure no crash and title set.


# --- image ------------------------------------------------------------------


class _FakeLLM:
    def __init__(self, text: str = "A red noise image, no readable text."):
        self.text = text
        self.calls: list[Any] = []

    async def complete(self, req: Any) -> Any:
        self.calls.append(req)
        return SimpleNamespace(content=self.text, status="ok", tool_calls=None)


@pytest.mark.asyncio
async def test_image_sticker_filtered():
    """Tiny image bypasses vision-LLM and returns empty."""
    a = find_adapter(media_kind="image", llm_gateway=_FakeLLM(), pool=None)
    tiny = (FIXTURES / "sticker.jpg").read_bytes()
    result = await a.extract(content=tiny)
    assert result.media_text == ""


@pytest.mark.asyncio
async def test_image_extract_then_cache(db_pool, boss_user):
    """First call invokes vision LLM; second call hits media_cache."""
    async with db_pool.acquire() as c:
        await c.execute("DELETE FROM media_cache")
    big = (FIXTURES / "sample.jpg").read_bytes()
    llm = _FakeLLM(text="Noise field.")
    a = find_adapter(
        media_kind="image",
        llm_gateway=llm,
        pool=db_pool,
        boss_id=boss_user["id"],
    )
    r1 = await a.extract(content=big)
    assert "Noise field" in r1.media_text
    assert len(llm.calls) == 1

    # Second extract: cache hits, no LLM call.
    a2 = find_adapter(
        media_kind="image",
        llm_gateway=llm,
        pool=db_pool,
        boss_id=boss_user["id"],
    )
    r2 = await a2.extract(content=big)
    assert r2.media_text == r1.media_text
    assert len(llm.calls) == 1  # unchanged


@pytest.mark.asyncio
async def test_image_no_llm_returns_empty():
    """Without a vision gateway the adapter degrades to empty (not crash)."""
    big = (FIXTURES / "sample.jpg").read_bytes()
    a = find_adapter(media_kind="image", llm_gateway=None, pool=None)
    result = await a.extract(content=big)
    assert result.media_text == ""


# --- contract sanity --------------------------------------------------------


def test_extract_result_dataclass_defaults():
    r = MediaExtractResult(media_text="x")
    assert r.title is None
    assert r.extra == {}
