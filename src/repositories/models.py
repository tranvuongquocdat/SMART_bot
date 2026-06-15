import json

import asyncpg

from src.domain.model import Model
from src.repositories.base import BossScopedRepo


def _row_to_model(r: asyncpg.Record) -> Model:
    caps = r["capabilities"]
    if isinstance(caps, str):
        caps = json.loads(caps)
    return Model(
        id=r["id"],
        name=r["name"],
        provider=r["provider"],
        endpoint_kind=r["endpoint_kind"],
        base_url=r["base_url"],
        tier=r["tier"],
        ctx_max=r["ctx_max"],
        capabilities=caps or [],
        cost_per_1m_input_usd=r["cost_per_1m_input_usd"],
        cost_per_1m_output_usd=r["cost_per_1m_output_usd"],
        is_platform_default=r["is_platform_default"],
        is_active=r["is_active"],
        notes=r["notes"],
        owner_boss_id=r["owner_boss_id"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class ModelsRepo(BossScopedRepo):
    async def get(self, model_id: int) -> Model | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM models WHERE id=$1", model_id)
            return _row_to_model(row) if row else None

    async def list(self, active_only: bool = True) -> list[Model]:
        async with self.pool.acquire() as c:
            q = "SELECT * FROM models"
            if active_only:
                q += " WHERE is_active=TRUE"
            q += " ORDER BY tier, provider, name"
            rows = await c.fetch(q)
            return [_row_to_model(r) for r in rows]

    async def platform_default(self, tier: str) -> Model | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM models
                WHERE tier=$1 AND is_platform_default=TRUE AND is_active=TRUE
                LIMIT 1
                """,
                tier,
            )
            return _row_to_model(row) if row else None

    async def list_for_boss(self, boss_id: int, active_only: bool = True) -> "list[Model]":
        """Model nền tảng + model riêng của boss (không thấy model của boss khác)."""
        async with self.pool.acquire() as c:
            q = "SELECT * FROM models WHERE (owner_boss_id IS NULL OR owner_boss_id=$1)"
            if active_only:
                q += " AND is_active=TRUE"
            q += " ORDER BY owner_boss_id NULLS FIRST, tier, provider, name"
            rows = await c.fetch(q, boss_id)
            return [_row_to_model(r) for r in rows]

    async def insert(
        self,
        name: str,
        provider: str,
        endpoint_kind: str,
        base_url: str | None,
        tier: str,
        ctx_max: int,
        capabilities: "list[str]",
        cost_in: float | None,
        cost_out: float | None,
        is_platform_default: bool = False,
        notes: str | None = None,
        owner_boss_id: int | None = None,
    ) -> int:
        if owner_boss_id is None:
            assert self.ctx.user_role == "superadmin"
        else:
            assert owner_boss_id == self.ctx.boss_id or self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                                    capabilities, cost_per_1m_input_usd,
                                    cost_per_1m_output_usd, is_platform_default, notes,
                                    owner_boss_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12) RETURNING id
                """,
                name,
                provider,
                endpoint_kind,
                base_url,
                tier,
                ctx_max,
                json.dumps(capabilities),
                cost_in,
                cost_out,
                is_platform_default,
                notes,
                owner_boss_id,
            )
