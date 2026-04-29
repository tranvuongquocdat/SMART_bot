"""scheduled_reviews — cron-driven LLM review jobs per boss."""
from __future__ import annotations

import aiosqlite


_REVIEW_ALLOWED_COLS = frozenset({
    "cron_time", "content_type", "custom_prompt", "enabled", "timezone",
})


class ReviewRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_for_owner(self, owner_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM scheduled_reviews WHERE owner_id = ? ORDER BY cron_time",
            (str(owner_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def create(
        self, owner_id: str, cron_time: str, content_type: str,
        custom_prompt: str | None = None,
    ) -> int:
        async with self._db.execute(
            """INSERT INTO scheduled_reviews (owner_id, cron_time, content_type, custom_prompt)
               VALUES (?, ?, ?, ?)""",
            (str(owner_id), cron_time, content_type, custom_prompt),
        ) as cur:
            await self._db.commit()
            return cur.lastrowid

    async def update(
        self, review_id: int, owner_id: str | None = None, **kwargs,
    ) -> bool:
        invalid = set(kwargs) - _REVIEW_ALLOWED_COLS
        if invalid:
            raise ValueError(f"Invalid column(s) for scheduled_reviews: {invalid}")
        if not kwargs:
            return False
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        if owner_id is not None:
            async with self._db.execute(
                f"UPDATE scheduled_reviews SET {sets} WHERE id = ? AND owner_id = ?",
                (*kwargs.values(), review_id, str(owner_id)),
            ) as cur:
                await self._db.commit()
                return cur.rowcount > 0
        await self._db.execute(
            f"UPDATE scheduled_reviews SET {sets} WHERE id = ?",
            (*kwargs.values(), review_id),
        )
        await self._db.commit()
        return True

    async def delete(self, review_id: int, owner_id: str | None = None) -> bool:
        if owner_id is not None:
            async with self._db.execute(
                "DELETE FROM scheduled_reviews WHERE id = ? AND owner_id = ?",
                (review_id, str(owner_id)),
            ) as cur:
                await self._db.commit()
                return cur.rowcount > 0
        await self._db.execute(
            "DELETE FROM scheduled_reviews WHERE id = ?", (review_id,)
        )
        await self._db.commit()
        return True

    async def list_all_enabled(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM scheduled_reviews WHERE enabled = 1"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
