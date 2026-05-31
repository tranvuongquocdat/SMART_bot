from datetime import datetime

import asyncpg

from src.domain.media_cache import MediaCacheEntry
from src.repositories.base import BossScopedRepo


def _row_to_entry(r: asyncpg.Record) -> MediaCacheEntry:
    return MediaCacheEntry(
        id=r["id"],
        source_key=r["source_key"],
        source_kind=r["source_kind"],
        media_text=r["media_text"],
        title=r["title"],
        fetched_at=r["fetched_at"],
        expires_at=r["expires_at"],
    )


class MediaCacheRepo(BossScopedRepo):
    """Global cache — not boss-scoped (cross-boss share by URL hash)."""

    async def get(self, source_key: str, source_kind: str) -> MediaCacheEntry | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM media_cache
                WHERE source_key=$1 AND source_kind=$2
                  AND (expires_at IS NULL OR expires_at > NOW())
                """,
                source_key,
                source_kind,
            )
            return _row_to_entry(row) if row else None

    async def list_expired(self, limit: int = 100) -> list[MediaCacheEntry]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM media_cache
                WHERE expires_at IS NOT NULL AND expires_at <= NOW()
                LIMIT $1
                """,
                limit,
            )
            return [_row_to_entry(r) for r in rows]

    async def insert(
        self,
        source_key: str,
        source_kind: str,
        media_text: str,
        title: str | None = None,
        expires_at: datetime | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO media_cache (source_key, source_kind, media_text, title, expires_at)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (source_key, source_kind) DO UPDATE SET
                  media_text=EXCLUDED.media_text, title=EXCLUDED.title,
                  expires_at=EXCLUDED.expires_at, fetched_at=NOW()
                RETURNING id
                """,
                source_key,
                source_kind,
                media_text,
                title,
                expires_at,
            )
