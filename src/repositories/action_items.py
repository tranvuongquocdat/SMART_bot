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

    async def update_status(
        self, action_id: int, status: ActionItemStatus | str
    ) -> None:
        value = status.value if isinstance(status, ActionItemStatus) else status
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE action_items SET status=$2, updated_at=NOW()
                WHERE id=$1 AND boss_id=$3
                """,
                action_id,
                value,
                self.ctx.boss_id,
            )

    async def list_all(
        self,
        group_id: str | None = None,
        status: str = "open",
    ) -> list[ActionItem]:
        """List action items filtered by status and optional chat_id.

        When ``group_id`` is a provider chat_id (as exposed to tools), we join
        through group_notes to resolve group_note_id.
        """
        async with self.pool.acquire() as c:
            if group_id is None:
                rows = await c.fetch(
                    """
                    SELECT * FROM action_items
                    WHERE boss_id=$1 AND status=$2
                    ORDER BY due_at NULLS LAST, id
                    """,
                    self.ctx.boss_id,
                    status,
                )
            else:
                rows = await c.fetch(
                    """
                    SELECT ai.* FROM action_items ai
                    JOIN group_notes gn ON gn.id = ai.group_note_id
                    WHERE ai.boss_id=$1 AND ai.status=$2 AND gn.chat_id=$3
                    ORDER BY ai.due_at NULLS LAST, ai.id
                    """,
                    self.ctx.boss_id,
                    status,
                    group_id,
                )
            return [_row_to_action_item(r) for r in rows]
