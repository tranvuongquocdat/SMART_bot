"""Web tool — fetch_url: route any URL through the media layer.

Detect kind from URL/content-type, fetch raw bytes for documents/images,
and delegate extraction to the registered media adapters (trafilatura for
web, yt-dlp/transcript for YouTube, pypdf/docx/openpyxl for documents,
vision-LLM for images). Returns clean text + title, or a useful error.
"""

from __future__ import annotations

import httpx

import src.media  # noqa: F401  (importing registers all media adapters)
from src.media.adapters.web import MAX_BODY_BYTES
from src.media.registry import find_adapter
from src.tools.base import ToolResult
from src.tools.registry import tool

_DOC_EXT = ("pdf", "docx", "xlsx", "txt")
_IMG_EXT = ("jpg", "jpeg", "png", "webp", "heic", "gif")


def _needs_bytes(url: str, content_type: str) -> str | None:
    """Return media_kind ('pdf'/'docx'/'xlsx'/'txt'/'image') when this URL is a
    document/image whose adapter needs raw bytes; else None (web/youtube/tiktok)."""
    u = url.lower().split("?", 1)[0]
    ext = u.rsplit(".", 1)[-1] if "." in u.rsplit("/", 1)[-1] else ""
    ct = (content_type or "").lower()
    if ct.startswith("image/") or ext in _IMG_EXT:
        return "image"
    if ext in _DOC_EXT:
        return ext
    if "pdf" in ct:
        return "pdf"
    if "wordprocessingml" in ct or "msword" in ct:
        return "docx"
    if "spreadsheetml" in ct or "ms-excel" in ct:
        return "xlsx"
    if ct.startswith("text/plain"):
        return "txt"
    return None


async def _probe_content_type(url: str) -> str:
    """Cheap HEAD to learn content-type (many doc/image URLs have no extension).
    Returns "" on any failure — detection then falls back to URL extension."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as c:
            r = await c.head(url)
            return r.headers.get("content-type", "")
    except Exception:
        return ""


@tool(
    name="fetch_url",
    description=(
        "Đọc nội dung 1 URL → text + title. Hỗ trợ web/báo, YouTube (transcript), "
        "TikTok (best-effort), PDF/DOCX/XLSX, ảnh. Dùng khi user đưa link hoặc cần "
        "đọc nội dung của một link."
    ),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    feature="url_summarize",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=40,
)
async def fetch_url(ctx, url: str) -> ToolResult:
    try:
        content_type = await _probe_content_type(url)
        kind = _needs_bytes(url, content_type)

        if kind in _DOC_EXT:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
                r = await c.get(url)
                r.raise_for_status()
            adapter = find_adapter(media_kind=kind)
            result = await adapter.extract(
                content=r.content, content_type=content_type or None, url=url
            )
        elif kind == "image":
            adapter = find_adapter(
                media_kind="image", llm_gateway=ctx.llm, pool=ctx.pool, boss_id=ctx.boss_id
            )
            result = await adapter.extract(url=url)  # ImageExtractor fetches bytes itself
        else:
            adapter = find_adapter(url=url)  # url / youtube / tiktok
            result = await adapter.extract(url=url)

        text = (result.media_text or "")[:MAX_BODY_BYTES]
        if not text.strip():
            return ToolResult(
                content=None,
                error="empty_content: không trích được nội dung từ link (có thể cần đăng nhập / là video không phụ đề)",
            )
        return ToolResult(content={"title": result.title or "", "text": text})
    except httpx.HTTPStatusError as e:
        return ToolResult(content=None, error=f"http_{e.response.status_code}: không tải được link")
    except Exception as e:  # noqa: BLE001
        return ToolResult(content=None, error=f"fetch_failed: {e}")
