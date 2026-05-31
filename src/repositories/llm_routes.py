import json

import asyncpg

from src.domain.model import LLMRoute
from src.repositories.base import BossScopedRepo


def _row_to_route(r: asyncpg.Record) -> LLMRoute:
    chain = r["fallback_chain"]
    if isinstance(chain, str):
        chain = json.loads(chain)
    return LLMRoute(
        id=r["id"],
        feature=r["feature"],
        condition_cel=r["condition_cel"],
        target_tier=r["target_tier"],
        fallback_chain=chain or [],
        weight=r["weight"],
        is_active=r["is_active"],
        notes=r["notes"],
        updated_at=r["updated_at"],
    )


class LLMRoutesRepo(BossScopedRepo):
    async def get(self, route_id: int) -> LLMRoute | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM llm_routes WHERE id=$1", route_id)
            return _row_to_route(row) if row else None

    async def list_active_for_feature(self, feature: str) -> list[LLMRoute]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM llm_routes
                WHERE feature=$1 AND is_active=TRUE
                ORDER BY weight DESC
                """,
                feature,
            )
            return [_row_to_route(r) for r in rows]

    async def list(self) -> list[LLMRoute]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM llm_routes ORDER BY feature, weight DESC")
            return [_row_to_route(r) for r in rows]

    async def insert(
        self,
        feature: str,
        target_tier: str,
        fallback_chain: list[dict],
        condition_cel: str | None = None,
        weight: int = 100,
        notes: str | None = None,
    ) -> int:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO llm_routes (feature, condition_cel, target_tier, fallback_chain,
                                        weight, notes)
                VALUES ($1,$2,$3,$4::jsonb,$5,$6) RETURNING id
                """,
                feature,
                condition_cel,
                target_tier,
                json.dumps(fallback_chain),
                weight,
                notes,
            )
