import pytest

from src.tools.core import web as web_tool


class _FakeCtx:
    def __init__(self):
        self.boss_id = 1
        self.boss_role = "boss"
        self.pool = None
        self.llm = None


@pytest.mark.asyncio
async def test_fetch_url_generic_uses_adapter(monkeypatch):
    from src.media.base import MediaExtractResult

    class _FakeWeb:
        async def extract(self, url=None, content=None, content_type=None):
            return MediaExtractResult(media_text="hello body", title="T")

    # No file extension / no doc content-type → routed to url adapter.
    monkeypatch.setattr(web_tool, "find_adapter", lambda **kw: _FakeWeb())

    async def _no_head(url):
        return ""

    monkeypatch.setattr(web_tool, "_probe_content_type", _no_head)
    res = await web_tool.fetch_url(_FakeCtx(), "https://example.com/a")
    assert res.error is None
    assert res.content["title"] == "T"
    assert "hello body" in res.content["text"]


@pytest.mark.asyncio
async def test_fetch_url_empty_is_error(monkeypatch):
    from src.media.base import MediaExtractResult

    class _Empty:
        async def extract(self, **kw):
            return MediaExtractResult(media_text="")

    monkeypatch.setattr(web_tool, "find_adapter", lambda **kw: _Empty())

    async def _no_head(url):
        return ""

    monkeypatch.setattr(web_tool, "_probe_content_type", _no_head)
    res = await web_tool.fetch_url(_FakeCtx(), "https://example.com/empty")
    assert res.content is None
    assert res.error and "empty" in res.error


@pytest.mark.asyncio
async def test_fetch_url_reports_error(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(web_tool, "find_adapter", _boom)

    async def _no_head(url):
        return ""

    monkeypatch.setattr(web_tool, "_probe_content_type", _no_head)
    res = await web_tool.fetch_url(_FakeCtx(), "https://x.test")
    assert res.content is None
    assert res.error and "boom" in res.error


def test_needs_bytes_detects_kind():
    assert web_tool._needs_bytes("https://x/y.pdf", "") == "pdf"
    assert web_tool._needs_bytes("https://x/y", "application/pdf") == "pdf"
    assert web_tool._needs_bytes("https://x/pic.jpg", "") == "image"
    assert web_tool._needs_bytes("https://x/a", "image/png") == "image"
    assert web_tool._needs_bytes("https://x/article", "text/html") is None
