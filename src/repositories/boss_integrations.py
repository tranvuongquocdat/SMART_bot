import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class BossIntegration:
    id: int
    boss_id: int
    plugin_id: str
    enabled: bool
    settings_json: dict[str, Any]
    connected_at: datetime
    # auth_blob_enc excluded — accessed only by plugin runtime


def _row_to_integration(r: asyncpg.Record) -> BossIntegration:
    settings = r["settings_json"]
    if isinstance(settings, str):
        settings = json.loads(settings)
    return BossIntegration(
        id=r["id"],
        boss_id=r["boss_id"],
        plugin_id=r["plugin_id"],
        enabled=r["enabled"],
        settings_json=settings or {},
        connected_at=r["connected_at"],
    )


class BossIntegrationsRepo(BossScopedRepo):
    async def get(self, plugin_id: str) -> BossIntegration | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM boss_integrations
                WHERE boss_id=$1 AND plugin_id=$2
                """,
                self.ctx.boss_id,
                plugin_id,
            )
            return _row_to_integration(row) if row else None

    async def list_all(self) -> list[BossIntegration]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM boss_integrations WHERE boss_id=$1 ORDER BY plugin_id",
                self.ctx.boss_id,
            )
            return [_row_to_integration(r) for r in rows]

    async def upsert(
        self,
        plugin_id: str,
        auth_blob_enc: bytes | None,
        settings: dict | None = None,
        enabled: bool = True,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO boss_integrations (boss_id, plugin_id, enabled, auth_blob_enc,
                                               settings_json)
                VALUES ($1,$2,$3,$4,$5::jsonb)
                ON CONFLICT (boss_id, plugin_id) DO UPDATE SET
                  enabled=EXCLUDED.enabled,
                  auth_blob_enc=EXCLUDED.auth_blob_enc,
                  settings_json=EXCLUDED.settings_json
                RETURNING id
                """,
                self.ctx.boss_id,
                plugin_id,
                enabled,
                auth_blob_enc,
                json.dumps(settings or {}),
            )

    async def get_auth_blob(self, plugin_id: str) -> bytes | None:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                SELECT auth_blob_enc FROM boss_integrations
                WHERE boss_id=$1 AND plugin_id=$2
                """,
                self.ctx.boss_id,
                plugin_id,
            )
