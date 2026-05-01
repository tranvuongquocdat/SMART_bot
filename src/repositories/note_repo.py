"""notes table — personal / project / group notes."""
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

    async def upsert(
        self, boss_chat_id: str, note_type: str, ref_id: str, content: str,
    ) -> None:
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
