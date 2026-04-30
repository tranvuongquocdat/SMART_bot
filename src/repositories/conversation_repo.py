"""conversation + group_map — chat-side identity (provider mapping + group registry)."""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class ConversationRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- conversation (provider mapping) -------------------------------------

    async def resolve_or_create_conversation(
        self, provider: str, external_chat_id: str, chat_type: str, title: str = "",
    ) -> str:
        async with self._db.execute(
            "SELECT internal_chat_id FROM conversation WHERE provider = ? AND external_chat_id = ?",
            (provider, str(external_chat_id)),
        ) as cur:
            row = await cur.fetchone()
        if row:
            if title:
                await self._db.execute(
                    """UPDATE conversation
                       SET title = COALESCE(NULLIF(?, ''), title)
                       WHERE internal_chat_id = ?""",
                    (title, row["internal_chat_id"]),
                )
                await self._db.commit()
            return row["internal_chat_id"]
        internal_chat_id = str(uuid.uuid4())
        try:
            await self._db.execute(
                """INSERT INTO conversation
                   (internal_chat_id, provider, external_chat_id, chat_type, title, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (internal_chat_id, provider, str(external_chat_id), chat_type, title or "",
                 int(time.time() * 1000)),
            )
            await self._db.commit()
            return internal_chat_id
        except sqlite3.IntegrityError:
            async with self._db.execute(
                "SELECT internal_chat_id FROM conversation WHERE provider = ? AND external_chat_id = ?",
                (provider, str(external_chat_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise
            return row["internal_chat_id"]

    async def lookup_external_for_conversation(
        self, internal_chat_id: str,
    ) -> Optional[tuple[str, str]]:
        async with self._db.execute(
            "SELECT provider, external_chat_id FROM conversation WHERE internal_chat_id = ?",
            (str(internal_chat_id),),
        ) as cur:
            row = await cur.fetchone()
        return (row["provider"], row["external_chat_id"]) if row else None

    async def get_kind(self, internal_chat_id: str) -> str:
        async with self._db.execute(
            "SELECT chat_type FROM conversation WHERE internal_chat_id = ?",
            (str(internal_chat_id),),
        ) as cur:
            row = await cur.fetchone()
        return (row["chat_type"] if row else "") or ""

    # --- group_map ------------------------------------------------------------

    async def get_group(self, group_chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM group_map WHERE group_chat_id = ?", (str(group_chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def add_group(
        self, group_chat_id: str, boss_chat_id: str, group_name: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO group_map (group_chat_id, boss_chat_id, group_name, project_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(group_chat_id) DO UPDATE SET
                boss_chat_id = excluded.boss_chat_id,
                group_name   = excluded.group_name,
                project_id   = excluded.project_id
            """,
            (str(group_chat_id), str(boss_chat_id), group_name, project_id),
        )
        await self._db.commit()
