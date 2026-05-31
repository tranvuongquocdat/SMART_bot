import json
from typing import Any

from src.repositories.base import BossScopedRepo


class AdminAuditLogRepo(BossScopedRepo):
    async def insert(
        self,
        action: str,
        target_kind: str | None = None,
        target_id: str | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO admin_audit_log (actor_user_id, action, target_kind, target_id,
                                             reason, payload_json)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb) RETURNING id
                """,
                self.ctx.boss_id,
                action,
                target_kind,
                target_id,
                reason,
                json.dumps(payload) if payload else None,
            )

    async def list_recent(self, limit: int = 100) -> list[dict]:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT $1",
                limit,
            )
            return [dict(r) for r in rows]
