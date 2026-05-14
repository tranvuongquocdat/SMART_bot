"""fetch_url tool — pulls a compact summary of any URL.

Behaviour:
- YouTube / youtu.be → hit YouTube oEmbed JSON → title + channel + thumbnail.
- TikTok               → hit TikTok oEmbed JSON → title + author + thumbnail.
- Anything else        → GET the URL, strip HTML, return <title> + meta
                         description + first ~1.5KB of body text.

No auth, no scraping libraries — just `httpx` + a tiny regex strip. Bots
that previously had to disclaim "chưa thể mở link YouTube" now have a real
tool to call.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("services.url_fetch")

_TIMEOUT = 8.0
_MAX_BODY_CHARS = 1500

_YT_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com")
_TT_HOSTS = ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "m.tiktok.com")


def _host_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url, re.IGNORECASE)
    return (m.group(1) if m else "").lower()


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


def _strip_html(html: str) -> tuple[str, str, str]:
    """Return (title, description, body_text). Very simple — no lxml, no bs4."""
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

    # Drop scripts/styles, then strip tags.
    body = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()[:_MAX_BODY_CHARS]
    return title, desc, body


async def fetch_url(url: str) -> str:
    """Public entry point — returns a compact human-readable summary."""
    url = (url or "").strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return "Cần một URL hợp lệ (http/https) để fetch."

    host = _host_of(url)

    # YouTube path
    if any(h == host or host.endswith("." + h.split(".", 1)[-1]) for h in _YT_HOSTS):
        data = await _oembed("https://www.youtube.com/oembed", url)
        if data:
            return (
                f"[YouTube] {data.get('title', '?')}\n"
                f"Channel: {data.get('author_name', '?')}\n"
                f"Thumbnail: {data.get('thumbnail_url', '')}\n"
                f"URL: {url}"
            )
        return f"[YouTube] Không lấy được oEmbed cho {url} (video có thể bị giới hạn/region-locked)."

    # TikTok path
    if any(h == host or host.endswith("." + h.split(".", 1)[-1]) for h in _TT_HOSTS):
        data = await _oembed("https://www.tiktok.com/oembed", url)
        if data:
            return (
                f"[TikTok] {data.get('title', '?')}\n"
                f"Author: {data.get('author_name', '?')}\n"
                f"Thumbnail: {data.get('thumbnail_url', '')}\n"
                f"URL: {url}"
            )
        return f"[TikTok] Không lấy được oEmbed cho {url}."

    # Generic HTML fetch
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
