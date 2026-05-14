"""fetch_url tool — pulls a compact summary of any URL.

Per-platform extraction order, each step degrades gracefully:

YouTube (youtube.com / youtu.be)
  1. youtube-transcript-api → real captions (vi → en → first available).
     Returns the full transcript text alongside oEmbed metadata.
  2. If transcript unavailable / IP-blocked / no captions → oEmbed only.

TikTok (tiktok.com)
  1. yt-dlp metadata extract → caption, uploader, duration, view count,
     thumbnail. No subtitle attempt (TikTok subs require curl_cffi
     impersonation which isn't reliable in our environment).
  2. If yt-dlp fails for any reason → oEmbed only.

Generic URL (news, blog, …)
  GET → strip <script>/<style> → return title + og:description + first
  ~1.5KB of body text.

No API keys, no auth. Network errors are caught and surfaced as a
human-readable single-line error string to the LLM, never a crash.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("services.url_fetch")

_TIMEOUT = 8.0
_MAX_BODY_CHARS = 1500
_MAX_TRANSCRIPT_CHARS = 10000  # cap for the sampled transcript handed to the LLM
_TRANSCRIPT_WINDOWS = 8        # evenly-spaced sampling windows across the video

_YT_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com")
_TT_HOSTS = ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "m.tiktok.com")


def _host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url, re.IGNORECASE)
    return (m.group(1) if m else "").lower()


def _matches(host: str, allowed: tuple[str, ...]) -> bool:
    return any(host == h or host.endswith("." + h) for h in allowed)


def _yt_video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video id from any standard URL shape."""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


async def _oembed(provider_url: str, target_url: str) -> dict | None:
    full = f"{provider_url}?url={quote_plus(target_url)}&format=json"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as cli:
            r = await cli.get(full, headers={"User-Agent": "smart-bot/1.0"})
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        logger.warning("oembed failed for %s", target_url, exc_info=True)
        return None


def _sample_evenly(text: str, target: int, windows: int = _TRANSCRIPT_WINDOWS) -> str:
    """Pick `windows` roughly-equal chunks evenly spaced through `text`,
    joined by ` […] ` markers. Total length ≤ ~target chars.

    For long YouTube transcripts we don't want to keep just the first N
    chars — that drops the entire back half of the video. Sampling
    evenly lets the LLM see beginning, middle, and end.
    """
    text = text or ""
    if len(text) <= target or windows < 2:
        return text[:target]
    window_size = max(1, target // windows)
    # Stride across the *gap* between window starts so the last window
    # ends near the end of the text.
    stride = max(window_size, (len(text) - window_size) // (windows - 1))
    chunks: list[str] = []
    for w in range(windows):
        start = w * stride
        end = start + window_size
        if start >= len(text):
            break
        # Snap to whitespace so we don't cut mid-word.
        while start > 0 and not text[start].isspace():
            start -= 1
        while end < len(text) and not text[end].isspace():
            end += 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return " […] ".join(chunks)


def _yt_transcript_sync(video_id: str) -> str | None:
    """Blocking transcript fetch — runs inside `asyncio.to_thread`.
    Returns concatenated text or None on any failure."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return None
    try:
        api = YouTubeTranscriptApi()
        # Prefer Vietnamese, then English, then any first transcript.
        for lang in (["vi"], ["en"], None):
            try:
                fetched = api.fetch(video_id, languages=lang) if lang else None
                if fetched is None:
                    listing = api.list(video_id)
                    first = next(iter(listing), None)
                    if first is None:
                        return None
                    fetched = first.fetch()
                text = " ".join(s.text for s in fetched.snippets if s.text)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    return _sample_evenly(text, _MAX_TRANSCRIPT_CHARS)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _tt_yt_dlp_sync(url: str) -> dict | None:
    """Blocking yt-dlp metadata extract. Returns a dict of useful fields or
    None on failure. Skipped if yt-dlp isn't installed."""
    try:
        import yt_dlp
    except Exception:
        return None
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": (info.get("title") or "").strip()[:200],
            "description": (info.get("description") or "").strip()[:400],
            "uploader": info.get("uploader") or info.get("uploader_id") or "",
            "duration_s": info.get("duration"),
            "view_count": info.get("view_count"),
            "thumbnail": info.get("thumbnail") or "",
        }
    except Exception:
        return None


def _strip_html(html: str) -> tuple[str, str, str]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = (title_m.group(1).strip() if title_m else "")[:200]

    desc_m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    ) or re.search(
        r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    desc = (desc_m.group(1).strip() if desc_m else "")[:400]

    body = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()[:_MAX_BODY_CHARS]
    return title, desc, body


async def fetch_url(url: str) -> str:
    url = (url or "").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return "Cần một URL hợp lệ (http/https) để fetch."

    host = _host_of(url)

    # ---- YouTube ----------------------------------------------------------
    if _matches(host, _YT_HOSTS):
        oembed = await _oembed("https://www.youtube.com/oembed", url)
        video_id = _yt_video_id(url)
        transcript = None
        if video_id:
            transcript = await asyncio.to_thread(_yt_transcript_sync, video_id)

        lines = ["[YouTube]"]
        if oembed:
            lines.append(f"Title: {oembed.get('title', '?')}")
            lines.append(f"Channel: {oembed.get('author_name', '?')}")
        else:
            lines.append(f"(oEmbed không trả về metadata cho {url})")
        if transcript:
            lines.append("")
            lines.append("Transcript (rút gọn):")
            lines.append(transcript)
        else:
            lines.append("Transcript: không lấy được (video không có caption hoặc IP đang bị YouTube hạn chế).")
        lines.append(f"URL: {url}")
        return "\n".join(lines)

    # ---- TikTok -----------------------------------------------------------
    if _matches(host, _TT_HOSTS):
        meta = await asyncio.to_thread(_tt_yt_dlp_sync, url)
        if not meta:
            # Fall back to oEmbed when yt-dlp can't reach the video.
            data = await _oembed("https://www.tiktok.com/oembed", url)
            if data:
                return (
                    f"[TikTok] {data.get('title', '?')}\n"
                    f"Author: {data.get('author_name', '?')}\n"
                    f"Thumbnail: {data.get('thumbnail_url', '')}\n"
                    f"URL: {url}"
                )
            return f"[TikTok] Không lấy được dữ liệu cho {url}."

        lines = ["[TikTok]", f"Caption: {meta.get('title', '?')}"]
        if meta.get("uploader"):
            lines.append(f"Uploader: @{meta['uploader']}")
        if meta.get("duration_s"):
            lines.append(f"Duration: {int(meta['duration_s'])}s")
        if meta.get("view_count"):
            lines.append(f"Views: {meta['view_count']:,}")
        if meta.get("description") and meta.get("description") != meta.get("title"):
            lines.append(f"Description: {meta['description']}")
        if meta.get("thumbnail"):
            lines.append(f"Thumbnail: {meta['thumbnail']}")
        lines.append(f"URL: {url}")
        return "\n".join(lines)

    # ---- Generic HTML -----------------------------------------------------
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cli:
            r = await cli.get(url, headers={"User-Agent": "Mozilla/5.0 smart-bot/1.0"})
    except Exception as e:
        return f"Không truy cập được URL: {e}"

    if r.status_code >= 400:
        return f"URL trả HTTP {r.status_code}: {url}"

    ct = (r.headers.get("content-type") or "").lower()
    if "html" not in ct and "text" not in ct:
        return f"URL không phải HTML/text ({ct or 'unknown'}): {url}"

    title, desc, body = _strip_html(r.text)
    out = [f"[URL] {url}"]
    if title:
        out.append(f"Title: {title}")
    if desc:
        out.append(f"Description: {desc}")
    if body:
        out.append(f"Body (rút gọn): {body}")
    return "\n".join(out) if len(out) > 1 else f"URL trả nội dung rỗng: {url}"
