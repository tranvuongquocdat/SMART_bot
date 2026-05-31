import asyncpg

from src.domain.pin import Pin
from src.repositories.base import BossScopedRepo


def _row_to_pin(r: asyncpg.Record) -> Pin:
    return Pin(
        id=r["id"],
        boss_id=r["boss_id"],
        group_note_id=r["group_note_id"],
        message_id=r["message_id"],
        note=r["note"],
        pinned_by=r["pinned_by"],
        pinned_at=r["pinned_at"],
    )


class PinsRepo(BossScopedRepo):
    async def get(self, pin_id: int) -> Pin | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM pins WHERE id=$1 AND boss_id=$2",
                pin_id,
                self.ctx.boss_id,
            )
            return _row_to_pin(row) if row else None

    async def list_for_group(self, group_note_id: int) -> list[Pin]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM pins WHERE boss_id=$1 AND group_note_id=$2
                ORDER BY pinned_at DESC
                """,
                self.ctx.boss_id,
                group_note_id,
            )
            return [_row_to_pin(r) for r in rows]

    async def insert(
        self,
        group_note_id: int,
        message_id: int,
        pinned_by: int,
        note: str | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO pins (boss_id, group_note_id, message_id, note, pinned_by)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (group_note_id, message_id) DO UPDATE SET note=EXCLUDED.note
                RETURNING id
                """,
                self.ctx.boss_id,
                group_note_id,
                message_id,
                note,
                pinned_by,
            )

    async def delete(self, pin_id: int) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "DELETE FROM pins WHERE id=$1 AND boss_id=$2",
                pin_id,
                self.ctx.boss_id,
            )
