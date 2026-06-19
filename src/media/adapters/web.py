"""WebExtractor — generic URL via trafilatura, YouTube via yt-dlp.

For generic URLs we cap extracted body at 50KB to keep prompts cheap. For
YouTube we prefer auto-generated subtitles (vi/en) and fall back to the
video description when subs are missing.
"""

from __future__ import annotations

import logging
import re

import httpx
import trafilatura

from src.media.base import MediaExtractResult
from src.media.registry import media_adapter

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 50_000

# Nhiều site (Wikipedia, báo) trả 403 nếu request không có User-Agent trình duyệt.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


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
        if "tiktok.com" in url:
            return await self._tiktok(url)
        return await self._generic(url)

    async def _generic(self, url: str) -> MediaExtractResult:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers={"User-Agent": BROWSER_UA}
        ) as c:
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
        title, vid, desc = _yt_meta(url)
        vid = vid or _yt_video_id(url)
        transcript = _yt_transcript(vid) if vid else ""
        body = transcript or desc  # transcript ưu tiên, fallback description
        text = (f"{title}\n\n{body}").strip()
        if len(text.encode("utf-8")) > MAX_BODY_BYTES:
            text = text.encode("utf-8")[:MAX_BODY_BYTES].decode("utf-8", errors="ignore")
        return MediaExtractResult(media_text=text, title=title or None, extra={"video_id": vid})

    async def _tiktok(self, url: str) -> MediaExtractResult:
        # Best-effort: title + description (yt-dlp metadata). Transcript đầy đủ cần
        # ASR (phase sau) — TikTok hiếm khi expose phụ đề. KHÔNG dùng trafilatura.
        title, _vid, desc = _yt_meta(url)
        text = (f"{title}\n\n{desc}").strip()
        return MediaExtractResult(media_text=text, title=title or None)


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _extract_title(html: str) -> str | None:
    m = _TITLE_RE.search(html or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None


def _yt_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def _yt_transcript(video_id: str) -> str:
    """Transcript thật (vi→en, cả auto-sub) qua youtube-transcript-api 1.x
    (instance .fetch → .to_raw_data). Rỗng nếu không có / bị chặn IP."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["vi", "en"])
        return " ".join(s["text"] for s in fetched.to_raw_data() if s.get("text")).strip()
    except Exception:
        log.info("yt transcript unavailable/blocked vid=%s", video_id)
        return ""


def _yt_meta(url: str) -> tuple[str, str | None, str]:
    """(title, video_id, description) qua yt-dlp; degrade rỗng nếu lỗi."""
    try:
        import yt_dlp  # type: ignore

        with yt_dlp.YoutubeDL({"skip_download": True, "quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return (info.get("title") or "", info.get("id"), info.get("description") or "")
    except Exception:
        log.exception("yt-dlp meta failed url=%s", url)
        return ("", _yt_video_id(url), "")
