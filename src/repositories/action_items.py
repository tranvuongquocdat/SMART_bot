from datetime import datetime

import asyncpg

from src.domain.action_item import ActionItem, ActionItemStatus
from src.repositories.base import BossScopedRepo


def _row_to_action_item(r: asyncpg.Record) -> ActionItem:
    return ActionItem(
        id=r["id"],
        boss_id=r["boss_id"],
        group_note_id=r["group_note_id"],
        text=r["text"],
        assignee_name=r["assignee_name"],
        due_at=r["due_at"],
        status=r["status"],
        source=r["source"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class ActionItemsRepo(BossScopedRepo):
    async def get(self, action_id: int) -> ActionItem | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM action_items WHERE id=$1 AND boss_id=$2",
                action_id,
                self.ctx.boss_id,
            )
            return _row_to_action_item(row) if row else None

    async def list_open(self, group_note_id: int | None = None) -> list[ActionItem]:
        async with self.pool.acquire() as c:
            if group_note_id is None:
                rows = await c.fetch(
                    """
                    SELECT * FROM action_items
                    WHERE boss_id=$1 AND status='open'
                    ORDER BY due_at NULLS LAST, id
                    """,
                    self.ctx.boss_id,
                )
            else:
                rows = await c.fetch(
                    """
                    SELECT * FROM action_items
                    WHERE boss_id=$1 AND group_note_id=$2 AND status='open'
                    ORDER BY due_at NULLS LAST, id
                    """,
                    self.ctx.boss_id,
                    group_note_id,
                )
            return [_row_to_action_item(r) for r in rows]

    async def insert(
        self,
        group_note_id: int,
        text: str,
        source: str,
        assignee_name: str | None = None,
        due_at: datetime | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO action_items (boss_id, group_note_id, text, assignee_name,
                                          due_at, source)
                VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
                """,
                self.ctx.boss_id,
                group_note_id,
                text,
                assignee_name,
                due_at,
                source,
            )

    async def update_status(self, action_id: int, status: ActionItemStatus) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE action_items SET status=$2, updated_at=NOW()
                WHERE id=$1 AND boss_id=$3
                """,
                action_id,
                status.value,
                self.ctx.boss_id,
            )
