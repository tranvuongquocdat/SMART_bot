"""
Web search via DuckDuckGo Instant Answer API.
"""
import httpx


async def web_search(query: str) -> str:
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get("https://api.duckduckgo.com/", params=params)
        resp.raise_for_status()
        data = resp.json()

    lines = []

    abstract = data.get("Abstract", "").strip()
    if abstract:
        source = data.get("AbstractSource", "")
        url = data.get("AbstractURL", "")
        lines.append(f"{abstract}")
        if source:
            lines.append(f"Nguồn: {source}" + (f" ({url})" if url else ""))

    related = data.get("RelatedTopics", [])
    if related:
        lines.append("\nChủ đề liên quan:")
        count = 0
        for item in related:
            if count >= 5:
                break
            if isinstance(item, dict):
                text = item.get("Text", "").strip()
                if text:
                    lines.append(f"- {text}")
                    count += 1

    if not lines:
        return f"Không tìm thấy kết quả nào cho '{query}'."

    return "\n".join(lines)
