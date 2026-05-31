from src.repositories.base import BossScopedRepo


class OutboundMessagesRepo(BossScopedRepo):
    async def insert(
        self,
        provider: str,
        chat_id: str,
        content: str,
        trigger: str,
        status: str,
        reply_to_message_id: int | None = None,
        error: str | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO outbound_messages (boss_id, provider, chat_id, reply_to_message_id,
                                               content, trigger, status, error)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
                """,
                self.ctx.boss_id,
                provider,
                chat_id,
                reply_to_message_id,
                content,
                trigger,
                status,
                error,
            )

    async def list_recent(self, chat_id: str, limit: int = 20) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM outbound_messages
                WHERE boss_id=$1 AND chat_id=$2
                ORDER BY sent_at DESC LIMIT $3
                """,
                self.ctx.boss_id,
                chat_id,
                limit,
            )
            return [dict(r) for r in rows]
