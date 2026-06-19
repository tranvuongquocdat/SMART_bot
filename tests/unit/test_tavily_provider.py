import httpx
import pytest

from src.search.tavily import TavilyProvider


@pytest.mark.asyncio
async def test_tavily_parses_results(monkeypatch):
    payload = {"results": [{"title": "T", "url": "https://u", "content": "body", "score": 0.9}]}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    res = await TavilyProvider(api_key="k").search("hello", max_results=3)
    assert res[0].title == "T"
    assert res[0].url == "https://u"
    assert "body" in res[0].content
