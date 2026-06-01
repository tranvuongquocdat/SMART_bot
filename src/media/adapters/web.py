"""WebExtractor — generic URL via trafilatura, YouTube via yt-dlp.

For generic URLs we cap extracted body at 50KB to keep prompts cheap. For
YouTube we prefer auto-generated subtitles (vi/en) and fall back to the
video description when subs are missing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
import trafilatura

from src.media.base import MediaExtractResult
from src.media.registry import media_adapter

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 50_000


@media_adapter(supports={"url", "youtube", "tiktok"})
class WebExtractor:
    async def extract(
        self,
        url: str | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> MediaExtractResult:
        if not url:
            return MediaExtractResult(media_text="")
        if "youtube.com" in url or "youtu.be" in url:
            return await self._youtube(url)
        return await self._generic(url)

    async def _generic(self, url: str) -> MediaExtractResult:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            html = r.text
        extracted = trafilatura.extract(html, include_comments=False) or ""
        title = _extract_title(html)
        if len(extracted.encode("utf-8")) > MAX_BODY_BYTES:
            extracted = extracted.encode("utf-8")[:MAX_BODY_BYTES].decode(
                "utf-8", errors="ignore"
            )
        return MediaExtractResult(media_text=extracted, title=title)

    async def _youtube(self, url: str) -> MediaExtractResult:
        # yt-dlp is sync; running it inline is fine for MVP — the scheduler
        # calls media extraction off the inbound hot path.
        try:
            import yt_dlp  # type: ignore
        except ImportError:
            return MediaExtractResult(media_text="")

        opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["vi", "en"],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            log.exception("yt-dlp extract failed url=%s", url)
            return MediaExtractResult(media_text="")
        subtitle = _pick_subtitle(info)
        title = info.get("title") or ""
        body = subtitle or info.get("description") or ""
        text = (f"{title}\n\n{body}").strip()
        if len(text.encode("utf-8")) > MAX_BODY_BYTES:
            text = text.encode("utf-8")[:MAX_BODY_BYTES].decode(
                "utf-8", errors="ignore"
            )
        return MediaExtractResult(
            media_text=text,
            title=title or None,
            extra={"video_id": info.get("id")},
        )


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _extract_title(html: str) -> str | None:
    m = _TITLE_RE.search(html or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None


def _pick_subtitle(info: dict[str, Any]) -> str | None:
    """Pick first available auto-sub for vi → en. yt-dlp returns urls;
    we don't dereference them in MVP — just signal we 'have subs' via
    the description path for now to avoid extra http calls in tests."""
    subs = (info.get("automatic_captions") or {}) | (info.get("subtitles") or {})
    for lang in ("vi", "en"):
        entries = subs.get(lang)
        if entries:
            # entries[0] is a dict with 'url' & 'ext'; we don't fetch it
            # here to avoid a 2nd round-trip. Future: fetch + parse SRT/VTT.
            return None
    return None
