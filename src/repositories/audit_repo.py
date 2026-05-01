"""audit_log table — append-only audit trail for boss-visible actions.

Wired but not actively written this phase — Phase 4's AuditService is the first caller.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite


class AuditRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def log(
        self, actor_internal_id: Optional[str], action: str,
        target_table: Optional[str] = None, target_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        cur = await self._db.execute(
            """INSERT INTO audit_log
               (actor_internal_id, action, target_table, target_id, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (actor_internal_id, action, target_table, target_id, payload_json),
        )
        await self._db.commit()
        return cur.lastrowid

    async def list_for_actor(
        self, actor_internal_id: str, limit: int = 50,
    ) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM audit_log
               WHERE actor_internal_id = ?
               ORDER BY ts DESC LIMIT ?""",
            (actor_internal_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
