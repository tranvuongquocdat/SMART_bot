"""ImageExtractor — HEIC convert → vision-LLM extract → content-hash cache.

Sticker filter: < 50KB or either dimension < 200 px is treated as a
sticker/icon and yields an empty result (avoids burning vision tokens on
meme/decor). Cache key is sha256 of the raw bytes; the same image
re-uploaded by any boss reuses the cached extraction.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
from typing import Any

from src.media.base import MediaExtractResult
from src.media.registry import media_adapter

log = logging.getLogger(__name__)

MIN_BYTES = 50_000
MIN_DIM = 200


@media_adapter(supports={"image"}, requires_caps={"vision"})
class ImageExtractor:
    def __init__(
        self,
        llm_gateway: Any | None = None,
        pool: Any | None = None,
        boss_id: int = 0,
    ):
        self.llm = llm_gateway
        self.pool = pool
        self.boss_id = boss_id

    async def extract(
        self,
        url: str | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> MediaExtractResult:
        # Lazy import — pillow_heif registers HEIC support globally on import.
        from PIL import Image  # type: ignore

        try:
            from pillow_heif import register_heif_opener  # type: ignore

            register_heif_opener()
        except ImportError:
            pass

        # Fetch bytes if only a URL was provided.
        if url and not content:
            import httpx

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                content = r.content
        if not content:
            return MediaExtractResult(media_text="")

        # Filter sticker/icon.
        if len(content) < MIN_BYTES:
            return MediaExtractResult(media_text="")
        try:
            img = Image.open(io.BytesIO(content))
        except Exception:
            log.warning("image open failed; not a valid image")
            return MediaExtractResult(media_text="")
        if img.size[0] < MIN_DIM or img.size[1] < MIN_DIM:
            return MediaExtractResult(media_text="")

        # Content-hash cache hit?
        h = hashlib.sha256(content).hexdigest()
        if self.pool is not None:
            from src.repositories.base import BossContext
            from src.repositories.media_cache import MediaCacheRepo

            cache = MediaCacheRepo(
                self.pool, BossContext(self.boss_id, "superadmin")
            )
            existing = await cache.get(h, "image")
            if existing:
                return MediaExtractResult(media_text=existing.media_text)

        # Need a vision-capable LLM gateway to actually extract.
        if self.llm is None:
            return MediaExtractResult(media_text="")

        # Re-encode to JPEG for a stable, cheap payload (HEIC → JPEG, etc).
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()

        from src.llm.base import ChatMessage, LLMRequest

        req = LLMRequest(
            feature="image_extract",
            boss_id=self.boss_id,
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {
                            "type": "text",
                            "text": (
                                "Mô tả ngắn ảnh này (1–3 câu) và trích text "
                                "nếu có (OCR). Bỏ qua sticker/meme."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            },
                        },
                    ],
                )
            ],
            required_caps={"vision"},
            routing_hints={"op": "image_extract"},
        )
        try:
            resp = await self.llm.complete(req)
        except Exception:
            log.exception("vision LLM call failed")
            return MediaExtractResult(media_text="")
        media_text = f"[image] {resp.content or ''}".strip()

        if self.pool is not None:
            from src.repositories.base import BossContext
            from src.repositories.media_cache import MediaCacheRepo

            cache = MediaCacheRepo(
                self.pool, BossContext(self.boss_id, "superadmin")
            )
            await cache.insert(h, "image", media_text, expires_at=None)
        return MediaExtractResult(media_text=media_text)
