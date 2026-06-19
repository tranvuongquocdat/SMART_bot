import pytest

from src.search.base import SearchResult
from src.tools.core import search_web


class _Ctx:
    boss_id = 1
    boss_role = "boss"
    pool = None
    llm = None


@pytest.mark.asyncio
async def test_web_search_returns_results(monkeypatch):
    class _P:
        async def search(self, q, *, max_results=5):
            return [SearchResult(title="A", url="https://a", snippet="s", content="c")]

    async def _fake_provider(ctx):
        return _P()

    monkeypatch.setattr(search_web, "_get_provider", _fake_provider)
    res = await search_web.web_search(_Ctx(), "tin tức")
    assert res.error is None
    assert res.content[0]["url"] == "https://a"


@pytest.mark.asyncio
async def test_web_search_no_key(monkeypatch):
    async def _none(ctx):
        return None

    monkeypatch.setattr(search_web, "_get_provider", _none)
    res = await search_web.web_search(_Ctx(), "x")
    assert res.content is None
    assert "cấu hình" in (res.error or "")
