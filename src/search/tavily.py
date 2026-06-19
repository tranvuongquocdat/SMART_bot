"""Tavily search provider (REST via httpx — no extra SDK)."""

from __future__ import annotations

import httpx

from src.search.base import SearchResult

_ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        body = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(_ENDPOINT, json=body)
            r.raise_for_status()
            data = r.json()
        out: list[SearchResult] = []
        for it in data.get("results", []):
            content = it.get("content") or ""
            out.append(
                SearchResult(
                    title=it.get("title") or "",
                    url=it.get("url") or "",
                    snippet=content[:300],
                    content=content,
                )
            )
        return out
