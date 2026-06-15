"""ArtifactCollector — gom file/link từ tin nhắn vào group_artifacts.

Subscribe ``message.captured``: tin nhắn có media → artifact theo media_kind;
text chứa URL → artifact kind 'link'. Chỉ ghi cho nhóm đã được theo dõi
(có row group_notes).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

_MEDIA_KIND_MAP = {
    "image": "image",
    "photo": "image",
    "video": "video",
    "file": "doc",
    "doc": "doc",
    "audio": "doc",
}


def _link_name(url: str) -> str:
    """Tên hiển thị cho link: domain + path rút gọn."""
    try:
        p = urlparse(url)
        name = p.netloc + (p.path if len(p.path) > 1 else "")
        return name[:120]
    except ValueError:
        return url[:120]


def register(bus, pool) -> None:
    async def handle(payload: dict) -> None:
        boss_id = payload.get("boss_id")
        provider = payload.get("provider")
        chat_id = payload.get("chat_id")
        message_id = payload.get("message_id")
        if not boss_id or not provider or not chat_id:
            return
        if payload.get("chat_type") != "group":
            return

        async with pool.acquire() as c:
            group = await c.fetchrow(
                """
                SELECT id FROM group_notes
                WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
                """,
                boss_id,
                provider,
                chat_id,
            )
            if group is None:
                return  # nhóm chưa được theo dõi

            msg = await c.fetchrow(
                "SELECT text, media_kind, media_url FROM messages WHERE id=$1",
                message_id,
            )
            if msg is None:
                return

            artifacts: list[tuple[str, str, str | None]] = []  # (kind, name, url)

            media_url = msg["media_url"]
            media_kind = (msg["media_kind"] or "").lower()
            if media_url and media_kind in _MEDIA_KIND_MAP:
                artifacts.append(
                    (_MEDIA_KIND_MAP[media_kind], _link_name(media_url), media_url)
                )

            for url in _URL_RE.findall(msg["text"] or ""):
                if url == media_url:
                    continue
                artifacts.append(("link", _link_name(url), url))

            for kind, name, url in artifacts[:10]:
                # Dedup: cùng nhóm + cùng url thì bỏ qua
                exists = await c.fetchval(
                    "SELECT 1 FROM group_artifacts WHERE group_id=$1 AND url=$2",
                    group["id"],
                    url,
                )
                if exists:
                    continue
                await c.execute(
                    """
                    INSERT INTO group_artifacts (group_id, kind, name, url, source_message_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    group["id"],
                    kind,
                    name,
                    url,
                    message_id,
                )

    async def safe_handle(payload: dict) -> None:
        try:
            await handle(payload)
        except Exception:
            log.exception("artifact_collector failed")

    bus.subscribe("message.captured", safe_handle)
