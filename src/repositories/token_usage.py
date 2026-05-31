from datetime import datetime
from decimal import Decimal

from src.repositories.base import BossScopedRepo


class TokenUsageRepo(BossScopedRepo):
    async def insert(
        self,
        feature: str,
        operation: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
        latency_ms: int,
        status: str,
        tokens_cached: int = 0,
        cost_saved_cache_usd: Decimal = Decimal("0"),
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        gen_ai_system: str | None = None,
        gen_ai_request_model: str | None = None,
        gen_ai_response_model: str | None = None,
        gen_ai_operation_name: str | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO token_usage (boss_id, feature, operation, provider, model,
                                         tokens_in, tokens_out, tokens_cached,
                                         cost_usd, cost_saved_cache_usd, latency_ms,
                                         trace_id, span_id, parent_span_id,
                                         gen_ai_system, gen_ai_request_model,
                                         gen_ai_response_model, gen_ai_operation_name, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                RETURNING id
                """,
                self.ctx.boss_id,
                feature,
                operation,
                provider,
                model,
                tokens_in,
                tokens_out,
                tokens_cached,
                cost_usd,
                cost_saved_cache_usd,
                latency_ms,
                trace_id,
                span_id,
                parent_span_id,
                gen_ai_system,
                gen_ai_request_model,
                gen_ai_response_model,
                gen_ai_operation_name,
                status,
            )

    async def daily_cost(self, day: datetime) -> Decimal:
        async with self.pool.acquire() as c:
            v = await c.fetchval(
                """
                SELECT COALESCE(SUM(cost_usd),0) FROM token_usage
                WHERE boss_id=$1 AND called_at::date = $2::date
                """,
                self.ctx.boss_id,
                day,
            )
            return v or Decimal("0")

    async def list_recent(self, limit: int = 100) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM token_usage WHERE boss_id=$1
                ORDER BY called_at DESC LIMIT $2
                """,
                self.ctx.boss_id,
                limit,
            )
            return [dict(r) for r in rows]
