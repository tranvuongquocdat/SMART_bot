"""bosses table — workspace owner + Lark workspace pointers + per-boss config."""
from __future__ import annotations

from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class BossRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM bosses WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def list_all(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM bosses ORDER BY created_at"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def create(
        self,
        chat_id: str,
        name: str,
        company: str = "",
        lark_base_token: Optional[str] = None,
        lark_table_people: Optional[str] = None,
        lark_table_tasks: Optional[str] = None,
        lark_table_projects: Optional[str] = None,
        lark_table_ideas: Optional[str] = None,
        lark_table_reminders: Optional[str] = None,
        lark_table_notes: Optional[str] = None,
        email: str = "",
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO bosses
                (chat_id, name, company, lark_base_token, lark_table_people,
                 lark_table_tasks, lark_table_projects, lark_table_ideas,
                 lark_table_reminders, lark_table_notes, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                name                 = excluded.name,
                company              = excluded.company,
                lark_base_token      = excluded.lark_base_token,
                lark_table_people    = excluded.lark_table_people,
                lark_table_tasks     = excluded.lark_table_tasks,
                lark_table_projects  = excluded.lark_table_projects,
                lark_table_ideas     = excluded.lark_table_ideas,
                lark_table_reminders = excluded.lark_table_reminders,
                lark_table_notes     = excluded.lark_table_notes,
                email                = excluded.email
            """,
            (chat_id, name, company, lark_base_token, lark_table_people,
             lark_table_tasks, lark_table_projects, lark_table_ideas,
             lark_table_reminders, lark_table_notes, email),
        )
        await self._db.commit()
