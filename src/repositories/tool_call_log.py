from src.repositories.base import BossScopedRepo


class ToolCallLogRepo(BossScopedRepo):
    async def insert(
        self,
        trace_id: str,
        span_id: str,
        tool_name: str,
        args_hash: str,
        status: str,
        latency_ms: int,
        parent_span_id: str | None = None,
        error: str | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO tool_call_log (trace_id, span_id, parent_span_id, boss_id,
                                           tool_name, args_hash, status, latency_ms, error)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id
                """,
                trace_id,
                span_id,
                parent_span_id,
                self.ctx.boss_id,
                tool_name,
                args_hash,
                status,
                latency_ms,
                error,
            )

    async def list_for_trace(self, trace_id: str) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM tool_call_log
                WHERE trace_id=$1 AND boss_id=$2
                ORDER BY called_at
                """,
                trace_id,
                self.ctx.boss_id,
            )
            return [dict(r) for r in rows]

    async def list_recent(self, limit: int = 100) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM tool_call_log WHERE boss_id=$1
                ORDER BY called_at DESC LIMIT $2
                """,
                self.ctx.boss_id,
                limit,
            )
            return [dict(r) for r in rows]
