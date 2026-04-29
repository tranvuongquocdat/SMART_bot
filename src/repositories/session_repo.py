"""sessions + onboarding_state — short-lived per-user state (TTL or onboarding-flow)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite


class SessionRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- sessions (TTL key/value) --------------------------------------------

    async def set(
        self, user_id: str, key: str, value: str, ttl_minutes: int = 30,
    ) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO sessions (user_id, key, value, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (str(user_id), key, value, expires),
        )
        await self._db.commit()

    async def get(self, user_id: str, key: str) -> Optional[str]:
        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT value FROM sessions WHERE user_id = ? AND key = ? AND expires_at > ?",
            (str(user_id), key, now),
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else None

    async def delete(self, user_id: str, key: str) -> None:
        await self._db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND key = ?",
            (str(user_id), key),
        )
        await self._db.commit()

    # --- onboarding_state ----------------------------------------------------

    async def get_onboarding_state(self, chat_id: str) -> dict:
        async with self._db.execute(
            "SELECT state_json FROM onboarding_state WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["state_json"])
        except Exception:
            return {}

    async def save_onboarding_state(self, chat_id: str, state: dict) -> None:
        await self._db.execute(
            """INSERT INTO onboarding_state (chat_id, state_json, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(chat_id) DO UPDATE SET
                   state_json = excluded.state_json,
                   updated_at = CURRENT_TIMESTAMP""",
            (str(chat_id), json.dumps(state, ensure_ascii=False)),
        )
        await self._db.commit()

    async def clear_onboarding_state(self, chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM onboarding_state WHERE chat_id = ?", (str(chat_id),)
        )
        await self._db.commit()
