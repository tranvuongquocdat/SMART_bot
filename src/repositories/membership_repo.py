"""memberships table + legacy people_map wrappers (delegate to memberships)."""
from __future__ import annotations

from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class MembershipRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_for_user(self, user_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE chat_id = ? AND status = 'active'",
            (str(user_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_for_boss(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE boss_chat_id = ?",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get(self, chat_id: str, boss_chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
            (str(chat_id), str(boss_chat_id)),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def upsert(
        self, chat_id: str, boss_chat_id: str, person_type: str, name: str,
        status: str = "active", request_info: Optional[str] = None,
        lark_record_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO memberships
                (chat_id, boss_chat_id, person_type, name, status,
                 request_info, lark_record_id, requested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, boss_chat_id) DO UPDATE SET
                person_type    = excluded.person_type,
                name           = excluded.name,
                status         = excluded.status,
                request_info   = COALESCE(excluded.request_info, request_info),
                lark_record_id = COALESCE(excluded.lark_record_id, lark_record_id),
                approved_at    = CASE WHEN excluded.status = 'active' THEN CURRENT_TIMESTAMP ELSE approved_at END
            """,
            (str(chat_id), str(boss_chat_id), person_type, name, status,
             request_info, lark_record_id),
        )
        await self._db.commit()

    async def delete(self, chat_id: str, boss_chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
            (str(chat_id), str(boss_chat_id)),
        )
        await self._db.commit()

    # --- Legacy people_map wrappers (Phase 2) --------------------------------

    async def get_person_legacy(self, chat_id: str) -> Optional[dict]:
        """Returns first active membership for this chat_id; legacy shape (`type` field)."""
        async with self._db.execute(
            "SELECT chat_id, boss_chat_id, person_type AS type, name FROM memberships "
            "WHERE chat_id = ? AND status = 'active' LIMIT 1",
            (str(chat_id),),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def delete_person_legacy(self, chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM memberships WHERE chat_id = ?", (str(chat_id),)
        )
        await self._db.commit()
