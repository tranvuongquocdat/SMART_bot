import asyncpg

from src.domain.message import Message, NewMessage
from src.repositories.base import BossScopedRepo


def _row_to_message(r: asyncpg.Record) -> Message:
    return Message(
        id=r["id"],
        boss_id=r["boss_id"],
        provider=r["provider"],
        chat_id=r["chat_id"],
        chat_type=r["chat_type"],
        provider_msg_id=r["provider_msg_id"],
        reply_to_msg_id=r["reply_to_msg_id"],
        sender_provider_id=r["sender_provider_id"],
        sender_name=r["sender_name"],
        text=r["text"],
        media_kind=r["media_kind"],
        media_url=r["media_url"],
        media_text=r["media_text"],
        ts=r["ts"],
        ingested_at=r["ingested_at"],
    )


class MessagesRepo(BossScopedRepo):
    async def insert(self, m: NewMessage) -> int | None:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id,
                                      sender_provider_id, sender_name, text, media_kind,
                                      media_url, media_text, ts)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (provider, chat_id, provider_msg_id) DO NOTHING
                RETURNING id
                """,
                self.ctx.boss_id,
                m.provider,
                m.chat_id,
                m.chat_type,
                m.provider_msg_id,
                m.sender_provider_id,
                m.sender_name,
                m.text,
                m.media_kind,
                m.media_url,
                m.media_text,
                m.ts,
            )

    async def get(self, message_id: int) -> Message | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM messages WHERE id=$1 AND boss_id=$2",
                message_id,
                self.ctx.boss_id,
            )
            return _row_to_message(row) if row else None

    async def list_recent(self, chat_id: str, limit: int = 20) -> list[Message]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1 AND chat_id=$2
                ORDER BY ts DESC LIMIT $3
                """,
                self.ctx.boss_id,
                chat_id,
                limit,
            )
            return [_row_to_message(r) for r in rows]

    async def fts_search(
        self,
        query: str,
        chat_id: str | None = None,
        limit: int = 20,
    ) -> list[Message]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1
                  AND ($2::TEXT IS NULL OR chat_id=$2)
                  AND fts @@ plainto_tsquery('simple', unaccent($3))
                ORDER BY ts DESC LIMIT $4
                """,
                self.ctx.boss_id,
                chat_id,
                query,
                limit,
            )
            return [_row_to_message(r) for r in rows]

    async def fts_exact(
        self,
        fragment: str,
        chat_id: str | None = None,
        limit: int = 5,
    ) -> list[Message]:
        """Phrase-like FTS lookup using phraseto_tsquery for exact-quote matching."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1
                  AND ($2::TEXT IS NULL OR chat_id=$2)
                  AND fts @@ phraseto_tsquery('simple', unaccent($3))
                ORDER BY ts DESC LIMIT $4
                """,
                self.ctx.boss_id,
                chat_id,
                fragment,
                limit,
            )
            return [_row_to_message(r) for r in rows]

    async def context_around(
        self, message_id: int, n: int = 3
    ) -> tuple[list[Message], list[Message]]:
        """Return n messages before and n after a given message in same chat."""
        async with self.pool.acquire() as c:
            anchor = await c.fetchrow(
                "SELECT chat_id, ts FROM messages WHERE id=$1 AND boss_id=$2",
                message_id,
                self.ctx.boss_id,
            )
            if not anchor:
                return [], []
            before_rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1 AND chat_id=$2 AND ts < $3
                ORDER BY ts DESC LIMIT $4
                """,
                self.ctx.boss_id,
                anchor["chat_id"],
                anchor["ts"],
                n,
            )
            after_rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1 AND chat_id=$2 AND ts > $3
                ORDER BY ts ASC LIMIT $4
                """,
                self.ctx.boss_id,
                anchor["chat_id"],
                anchor["ts"],
                n,
            )
        before = [_row_to_message(r) for r in reversed(before_rows)]
        after = [_row_to_message(r) for r in after_rows]
        return before, after

    async def fetch_after_id(
        self, chat_id: str, after_id: int, limit: int = 200
    ) -> list[Message]:
        """Fetch messages with id > after_id in a single chat (for note delta)."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM messages
                WHERE boss_id=$1 AND chat_id=$2 AND id > $3
                ORDER BY id ASC LIMIT $4
                """,
                self.ctx.boss_id,
                chat_id,
                after_id,
                limit,
            )
            return [_row_to_message(r) for r in rows]

    async def distinct_senders(self, chat_id: str, days: int = 30) -> list[str]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT DISTINCT sender_provider_id FROM messages
                WHERE boss_id=$1 AND chat_id=$2
                  AND ts >= NOW() - ($3 || ' days')::INTERVAL
                  AND sender_provider_id IS NOT NULL
                """,
                self.ctx.boss_id,
                chat_id,
                days,
            )
            return [r["sender_provider_id"] for r in rows]
