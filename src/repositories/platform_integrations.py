"""Superadmin-managed integration provider config + usage (e.g. Tavily search).

Platform-level (not per-boss): one encrypted key + configurable unit cost +
health status per provider; usage recorded as a daily rollup per (provider, boss)
for cost charts. API keys reuse the LLM Fernet cipher.
"""

from __future__ import annotations

import datetime as dt
import json

from src.llm.api_keys import _fernet


class PlatformIntegrationsRepo:
    def __init__(self, pool):
        self.pool = pool

    async def set_config(
        self, provider: str, *, api_key: str | None = None, unit_cost_usd: float | None = None
    ) -> None:
        enc = _fernet.encrypt(api_key.encode()).decode() if api_key else None
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO platform_integrations(provider, api_key_enc, unit_cost_usd, updated_at)
                VALUES($1, $2, COALESCE($3::numeric, 0), now())
                ON CONFLICT (provider) DO UPDATE SET
                  api_key_enc   = COALESCE($2, platform_integrations.api_key_enc),
                  unit_cost_usd = COALESCE($3::numeric, platform_integrations.unit_cost_usd),
                  updated_at    = now()
                """,
                provider, enc, unit_cost_usd,
            )

    async def get(self, provider: str) -> dict | None:
        async with self.pool.acquire() as c:
            r = await c.fetchrow(
                """
                SELECT provider, unit_cost_usd, status,
                       (api_key_enc IS NOT NULL) AS has_key, updated_at
                FROM platform_integrations WHERE provider=$1
                """,
                provider,
            )
        if not r:
            return None
        status = r["status"]
        if isinstance(status, str):
            status = json.loads(status or "{}")
        return {
            "provider": r["provider"],
            "unit_cost_usd": float(r["unit_cost_usd"]),
            "status": status or {},
            "has_key": r["has_key"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }

    async def get_api_key(self, provider: str) -> str | None:
        async with self.pool.acquire() as c:
            enc = await c.fetchval(
                "SELECT api_key_enc FROM platform_integrations WHERE provider=$1", provider
            )
        return _fernet.decrypt(enc.encode()).decode() if enc else None

    async def set_status(self, provider: str, ok: bool, message: str) -> None:
        status = json.dumps(
            {"ok": ok, "message": message, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        )
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE platform_integrations SET status=$2::jsonb WHERE provider=$1",
                provider, status,
            )

    async def record_usage(self, provider: str, *, boss_id: int, cost_usd: float) -> None:
        today = dt.date.today()
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO integration_usage(provider, boss_id, day, count, cost_usd)
                VALUES($1, $2, $3, 1, $4)
                ON CONFLICT (provider, boss_id, day) DO UPDATE SET
                  count    = integration_usage.count + 1,
                  cost_usd = integration_usage.cost_usd + $4
                """,
                provider, boss_id, today, cost_usd,
            )

    async def usage_totals(self, provider: str) -> dict:
        async with self.pool.acquire() as c:
            r = await c.fetchrow(
                "SELECT COALESCE(SUM(count),0) AS count, COALESCE(SUM(cost_usd),0) AS cost "
                "FROM integration_usage WHERE provider=$1",
                provider,
            )
        return {"count": int(r["count"]), "cost": float(r["cost"])}

    async def usage_daily(self, provider: str, days: int = 30) -> list[dict]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT day, SUM(count) AS count, SUM(cost_usd) AS cost
                FROM integration_usage
                WHERE provider=$1 AND day >= current_date - $2::int
                GROUP BY day ORDER BY day DESC
                """,
                provider, days,
            )
        return [
            {"date": r["day"].isoformat(), "count": int(r["count"]), "cost_usd": float(r["cost"])}
            for r in rows
        ]
