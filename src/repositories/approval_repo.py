"""pending_approvals + task_notifications — task-workflow state (approvals + notification ledger)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite


_NOTIFICATION_KIND_COL = {
    "assigned": "notified_assigned",
    "24h": "notified_24h",
    "2h":  "notified_2h",
}


def _notification_col(kind: str) -> str:
    col = _NOTIFICATION_KIND_COL.get(kind)
    if col is None:
        raise ValueError(f"Unknown notification kind: {kind!r}")
    return col


class ApprovalRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- pending_approvals ---------------------------------------------------

    async def create(
        self, boss_chat_id: str, requester_id: str,
        task_record_id: str, payload: str,
    ) -> int:
        expires = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        async with self._db.execute(
            """INSERT INTO pending_approvals
               (boss_chat_id, requester_id, task_record_id, payload, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (str(boss_chat_id), str(requester_id), task_record_id, payload, expires),
        ) as cur:
            row_id = cur.lastrowid
        await self._db.commit()
        return row_id

    async def get_pending(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending' "
            "ORDER BY created_at",
            (str(boss_chat_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def update_status(self, approval_id: int, status: str) -> None:
        await self._db.execute(
            "UPDATE pending_approvals SET status = ? WHERE id = ?",
            (status, approval_id),
        )
        await self._db.commit()

    # --- task_notifications --------------------------------------------------

    async def upsert_task_notification(
        self, task_record_id: str, boss_chat_id: str,
        assignee_chat_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """INSERT OR IGNORE INTO task_notifications
               (task_record_id, boss_chat_id, assignee_chat_id)
               VALUES (?, ?, ?)""",
            (task_record_id, str(boss_chat_id),
             str(assignee_chat_id) if assignee_chat_id else None),
        )
        await self._db.commit()

    async def mark_notification_sent(
        self, task_record_id: str, boss_chat_id: str, kind: str,
    ) -> None:
        col = _notification_col(kind)
        await self._db.execute(
            f"UPDATE task_notifications SET {col} = 1 "
            f"WHERE task_record_id = ? AND boss_chat_id = ?",
            (task_record_id, str(boss_chat_id)),
        )
        await self._db.commit()

    async def get_unnotified(self, boss_chat_id: str, kind: str) -> list[dict]:
        col = _notification_col(kind)
        async with self._db.execute(
            f"SELECT * FROM task_notifications WHERE boss_chat_id = ? AND {col} = 0",
            (str(boss_chat_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_unnotified_overdue(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM task_notifications "
            "WHERE boss_chat_id = ? AND notified_overdue = 0",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_overdue_notified(
        self, task_record_id: str, boss_chat_id: str,
    ) -> None:
        await self._db.execute(
            "UPDATE task_notifications "
            "SET notified_overdue = 1, notified_overdue_at = CURRENT_TIMESTAMP "
            "WHERE task_record_id = ? AND boss_chat_id = ?",
            (task_record_id, str(boss_chat_id)),
        )
        await self._db.commit()
