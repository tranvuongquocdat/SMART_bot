import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class AgentTrigger:
    id: int
    op_name: str
    event_name: str
    debounce_json: dict[str, Any] | None
    threshold_json: dict[str, Any] | None
    enabled: bool
    updated_at: datetime


def _row_to_trigger(r: asyncpg.Record) -> AgentTrigger:
    debounce = r["debounce_json"]
    threshold = r["threshold_json"]
    if isinstance(debounce, str):
        debounce = json.loads(debounce)
    if isinstance(threshold, str):
        threshold = json.loads(threshold)
    return AgentTrigger(
        id=r["id"],
        op_name=r["op_name"],
        event_name=r["event_name"],
        debounce_json=debounce,
        threshold_json=threshold,
        enabled=r["enabled"],
        updated_at=r["updated_at"],
    )


class AgentTriggersRepo(BossScopedRepo):
    async def list_for_op(self, op_name: str) -> list[AgentTrigger]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM agent_triggers WHERE op_name=$1 AND enabled=TRUE",
                op_name,
            )
            return [_row_to_trigger(r) for r in rows]

    async def list_all(self) -> list[AgentTrigger]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM agent_triggers ORDER BY op_name, event_name"
            )
            return [_row_to_trigger(r) for r in rows]

    async def upsert(
        self,
        op_name: str,
        event_name: str,
        debounce: dict | None,
        threshold: dict | None,
        enabled: bool = True,
    ) -> int:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            # No unique key in schema; delete+insert idempotent on (op_name, event_name)
            await c.execute(
                "DELETE FROM agent_triggers WHERE op_name=$1 AND event_name=$2",
                op_name,
                event_name,
            )
            return await c.fetchval(
                """
                INSERT INTO agent_triggers (op_name, event_name, debounce_json,
                                            threshold_json, enabled)
                VALUES ($1,$2,$3::jsonb,$4::jsonb,$5) RETURNING id
                """,
                op_name,
                event_name,
                json.dumps(debounce) if debounce else None,
                json.dumps(threshold) if threshold else None,
                enabled,
            )
