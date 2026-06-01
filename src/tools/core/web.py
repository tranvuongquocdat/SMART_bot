"""Web tool — fetch_url (MVP: direct HTTP fetch + naive HTML→text strip)."""

import re

import httpx

from src.tools.base import ToolResult
from src.tools.registry import tool

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TITLE_RE = re.compile(
    r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL
)
_WS_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> tuple[str, str]:
    title_m = _TITLE_RE.search(html)
    title = (title_m.group(1).strip() if title_m else "") or ""
    body = _SCRIPT_RE.sub("", html)
    body = _TAG_RE.sub(" ", body)
    body = _WS_RE.sub(" ", body).strip()
    return title, body


@tool(
    name="fetch_url",
    description="Fetch + extract URL → text + title. MVP: HTML strip; YouTube/file ext sẽ thêm sau.",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    feature="url_summarize",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=30,
)
async def fetch_url(ctx, url: str) -> ToolResult:
    # Try media-registry first (Batch E will add YouTube/PDF/etc.).
    try:
        from src.media.registry import find_adapter  # type: ignore[import-not-found]

        adapter = find_adapter(url=url)
        result = await adapter.extract(url=url)
        return ToolResult(
            content={"title": result.title, "text": result.media_text[:20000]}
        )
    except Exception:
        pass

    # MVP fallback — plain HTTP GET, naive HTML→text.
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=20.0
        ) as client:
            resp = await client.get(url)
        ct = resp.headers.get("content-type", "").lower()
        if "html" in ct or "<html" in resp.text[:200].lower():
            title, text = _html_to_text(resp.text)
        else:
            title, text = "", resp.text
        return ToolResult(content={"title": title, "text": text[:20000]})
    except Exception as e:
        return ToolResult(content=None, error=f"fetch_failed: {e}")
