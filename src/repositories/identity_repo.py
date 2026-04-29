"""external_identity + seen_contacts — person-side identity (provider mapping + passive index)."""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class IdentityRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- external_identity ----------------------------------------------------

    async def resolve_or_create_person(
        self, provider: str, external_id: str, name: str = "", username: str = "",
    ) -> str:
        """Return internal_id (UUID) for (provider, external_id). Race-safe via UNIQUE."""
        async with self._db.execute(
            "SELECT internal_id FROM external_identity WHERE provider = ? AND external_id = ?",
            (provider, str(external_id)),
        ) as cur:
            row = await cur.fetchone()
        if row:
            if name or username:
                await self._db.execute(
                    """UPDATE external_identity
                       SET name = COALESCE(NULLIF(?, ''), name),
                           username = COALESCE(NULLIF(?, ''), username)
                       WHERE internal_id = ?""",
                    (name, username, row["internal_id"]),
                )
                await self._db.commit()
            return row["internal_id"]
        internal_id = str(uuid.uuid4())
        try:
            await self._db.execute(
                """INSERT INTO external_identity
                   (internal_id, provider, external_id, name, username, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (internal_id, provider, str(external_id), name or "", username or "",
                 int(time.time() * 1000)),
            )
            await self._db.commit()
            return internal_id
        except sqlite3.IntegrityError:
            async with self._db.execute(
                "SELECT internal_id FROM external_identity WHERE provider = ? AND external_id = ?",
                (provider, str(external_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise
            return row["internal_id"]

    async def lookup_external_for_person(self, internal_id: str) -> Optional[tuple[str, str]]:
        async with self._db.execute(
            "SELECT provider, external_id FROM external_identity WHERE internal_id = ?",
            (str(internal_id),),
        ) as cur:
            row = await cur.fetchone()
        return (row["provider"], row["external_id"]) if row else None

    # --- seen_contacts --------------------------------------------------------

    async def upsert_seen_contact(
        self, chat_id: str, display_name: str = "", username: str = "",
        last_seen_chat: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO seen_contacts (chat_id, display_name, username, last_seen_chat)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                display_name   = COALESCE(NULLIF(excluded.display_name, ''), seen_contacts.display_name),
                username       = COALESCE(NULLIF(excluded.username, ''), seen_contacts.username),
                last_seen_at   = CURRENT_TIMESTAMP,
                last_seen_chat = COALESCE(excluded.last_seen_chat, seen_contacts.last_seen_chat),
                seen_count     = seen_contacts.seen_count + 1
            """,
            (str(chat_id), display_name or "", username or "", last_seen_chat),
        )
        await self._db.commit()

    async def get_seen_contact(self, chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM seen_contacts WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def search_seen_contacts(self, query: str, limit: int = 20) -> list[dict]:
        like = f"%{query.lower()}%"
        async with self._db.execute(
            """SELECT * FROM seen_contacts
               WHERE lower(display_name) LIKE ? OR lower(username) LIKE ?
               ORDER BY last_seen_at DESC LIMIT ?""",
            (like, like, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_unlinked_seen_contacts(
        self, lark_people_chat_ids: set[str], days: int = 30, limit: int = 30,
    ) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM seen_contacts
               WHERE last_seen_at >= datetime('now', ? )
               ORDER BY last_seen_at DESC LIMIT ?""",
            (f"-{days} days", limit * 3),
        ) as cur:
            rows = await cur.fetchall()
        filtered: list[dict] = []
        for r in rows:
            d = dict(r)
            if d["chat_id"] not in lark_people_chat_ids:
                filtered.append(d)
                if len(filtered) >= limit:
                    break
        return filtered
