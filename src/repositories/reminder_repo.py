"""reminders table — pending DMs with optional target."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite


class ReminderRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self, boss_chat_id: str, content: str, remind_at: datetime,
        target_chat_id: Optional[str] = None, target_name: str = "",
    ) -> int:
        remind_at_str = remind_at.isoformat(sep=" ", timespec="seconds")
        cur = await self._db.execute(
            "INSERT INTO reminders (boss_chat_id, target_chat_id, target_name, content, remind_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(boss_chat_id), target_chat_id, target_name, content, remind_at_str),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_due(self, now: Optional[datetime] = None) -> list[dict]:
        if now is None:
            now = datetime.now(timezone.utc)
        now_str = now.isoformat(sep=" ", timespec="seconds")
        async with self._db.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ? ORDER BY remind_at",
            (now_str,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_done(self, reminder_id: int) -> None:
        await self._db.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?", (reminder_id,)
        )
        await self._db.commit()

    async def list_for_boss(
        self, boss_chat_id: str, status: str = "pending", limit: int = 50,
    ) -> list[dict]:
        lim = max(1, min(limit, 200))
        if status == "all":
            async with self._db.execute(
                """SELECT * FROM reminders
                   WHERE boss_chat_id = ?
                   ORDER BY remind_at ASC LIMIT ?""",
                (str(boss_chat_id), lim),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self._db.execute(
                """SELECT * FROM reminders
                   WHERE boss_chat_id = ? AND status = ?
                   ORDER BY remind_at ASC LIMIT ?""",
                (str(boss_chat_id), status, lim),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update(
        self, reminder_id: int, boss_chat_id: str, *,
        content: Optional[str] = None, remind_at: Optional[datetime] = None,
        update_target: bool = False, target_chat_id: Optional[str] = None,
        target_name: str = "",
    ) -> bool:
        sets: list[str] = []
        params: list = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if remind_at is not None:
            sets.append("remind_at = ?")
            params.append(remind_at.isoformat(sep=" ", timespec="seconds"))
        if update_target:
            sets.append("target_chat_id = ?")
            params.append(target_chat_id)
            sets.append("target_name = ?")
            params.append(target_name)
        if not sets:
            return False
        params.extend([reminder_id, str(boss_chat_id)])
        sql = f"UPDATE reminders SET {', '.join(sets)} WHERE id = ? AND boss_chat_id = ?"
        cur = await self._db.execute(sql, params)
        await self._db.commit()
        return cur.rowcount > 0

    async def delete(self, reminder_id: int, boss_chat_id: str) -> bool:
        cur = await self._db.execute(
            "DELETE FROM reminders WHERE id = ? AND boss_chat_id = ?",
            (reminder_id, str(boss_chat_id)),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def sync_from_lark(self, sqlite_id: int, content: str, status: str) -> None:
        await self._db.execute(
            "UPDATE reminders SET content = ?, status = ? WHERE id = ?",
            (content, status, sqlite_id),
        )
        await self._db.commit()
