"""notes table — personal / project / group / idea notes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class NoteRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(
        self, boss_chat_id: str, note_type: str, ref_id: str,
    ) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
            (str(boss_chat_id), note_type, ref_id),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def get_by_id(self, note_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def upsert(
        self, boss_chat_id: str, note_type: str, ref_id: str, content: str,
    ) -> int:
        """Upsert and return the row id."""
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        await self._db.execute(
            """
            INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(boss_chat_id, type, ref_id) DO UPDATE SET
                content    = excluded.content,
                updated_at = excluded.updated_at
            """,
            (str(boss_chat_id), note_type, ref_id, content, now),
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT id FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
            (str(boss_chat_id), note_type, ref_id),
        ) as cur:
            row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def set_lark_record_id(self, note_id: int, lark_record_id: str) -> None:
        await self._db.execute(
            "UPDATE notes SET lark_record_id = ? WHERE id = ?",
            (lark_record_id, note_id),
        )
        await self._db.commit()

    async def find_by_lark_id(self, boss_chat_id: str, lark_record_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id = ?",
            (str(boss_chat_id), lark_record_id),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def list_unsynced(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id IS NULL",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_with_lark_id(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id IS NOT NULL",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def delete_by_id(self, note_id: int) -> None:
        await self._db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await self._db.commit()

    async def update_content_by_id(self, note_id: int, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        await self._db.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, note_id),
        )
        await self._db.commit()
