"""messages + outbound_messages — chat history + bot-initiated DM log."""
from __future__ import annotations

from typing import Optional

import aiosqlite


class MessageRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- messages ------------------------------------------------------------

    async def save(
        self, chat_id: str, role: str, content: str, sender_id: Optional[str] = None,
    ) -> int:
        cur = await self._db.execute(
            "INSERT INTO messages (chat_id, sender_id, role, content) VALUES (?, ?, ?, ?)",
            (str(chat_id), sender_id, role, content),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_recent(self, chat_id: str, limit: int = 8) -> list[dict]:
        async with self._db.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (str(chat_id), limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- outbound_messages ---------------------------------------------------

    async def log_outbound_dm(
        self, boss_chat_id: str, to_chat_id: str, to_name: str, content: str,
        trigger_type: str = "manual", task_id: str = "", project: str = "",
        workspace_id: str = "",
    ) -> None:
        await self._db.execute(
            """INSERT INTO outbound_messages
               (boss_chat_id, workspace_id, to_chat_id, to_name, content,
                trigger_type, task_id, project)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(boss_chat_id), workspace_id, str(to_chat_id), to_name, content,
             trigger_type, task_id or "", project or ""),
        )
        await self._db.commit()

    async def get_outbound_log(
        self, boss_chat_id: str, to_chat_id: Optional[str] = None,
        trigger_type: Optional[str] = None, limit: int = 50,
    ) -> list[dict]:
        conditions = ["boss_chat_id = ?"]
        params: list = [str(boss_chat_id)]
        if to_chat_id:
            conditions.append("to_chat_id = ?")
            params.append(str(to_chat_id))
        if trigger_type:
            conditions.append("trigger_type = ?")
            params.append(trigger_type)
        where = " AND ".join(conditions)
        async with self._db.execute(
            f"SELECT * FROM outbound_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
