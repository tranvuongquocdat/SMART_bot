"""Web search via DuckDuckGo HTML (no API key required).

Uses the `ddgs` library (HTML scrape) instead of DuckDuckGo Instant Answer
API — the latter only returns Wikipedia-style abstracts for well-known
entities, which is empty for ~99% of real queries.
"""
from __future__ import annotations

import asyncio

from ddgs import DDGS


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """Blocking call inside a thread (ddgs is sync only)."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def web_search(query: str, max_results: int = 5) -> str:
    if not query.strip():
        return "Cần truy vấn để tìm kiếm."

    try:
        results = await asyncio.to_thread(_search_sync, query, max_results)
    except Exception as exc:
        return f"Lỗi tìm kiếm: {exc}"

    if not results:
        return f"Không tìm thấy kết quả nào cho '{query}'."

    lines = [f"Kết quả cho '{query}':"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        url = r.get("href", "").strip()
        # Truncate body so the LLM gets useful signal without burning tokens.
        snippet = body[:280] + "…" if len(body) > 280 else body
        lines.append(f"\n{i}. {title}\n   {snippet}\n   {url}")

    return "\n".join(lines)
