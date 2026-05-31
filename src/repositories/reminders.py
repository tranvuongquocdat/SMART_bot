from datetime import datetime

import asyncpg

from src.domain.reminder import Reminder, ReminderStatus
from src.repositories.base import BossScopedRepo


def _row_to_reminder(r: asyncpg.Record) -> Reminder:
    return Reminder(
        id=r["id"],
        boss_id=r["boss_id"],
        text=r["text"],
        due_at=r["due_at"],
        scope=r["scope"],
        provider=r["provider"],
        chat_id=r["chat_id"],
        bot_account_id=r["bot_account_id"],
        recurring=r["recurring"],
        action_item_id=r["action_item_id"],
        status=r["status"],
        fired_at=r["fired_at"],
        last_error=r["last_error"],
        created_at=r["created_at"],
        created_by_op=r["created_by_op"],
    )


class RemindersRepo(BossScopedRepo):
    async def get(self, reminder_id: int) -> Reminder | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM scheduled_reminders WHERE id=$1 AND boss_id=$2",
                reminder_id,
                self.ctx.boss_id,
            )
            return _row_to_reminder(row) if row else None

    async def list_pending(self) -> list[Reminder]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM scheduled_reminders
                WHERE boss_id=$1 AND status='pending'
                ORDER BY due_at
                """,
                self.ctx.boss_id,
            )
            return [_row_to_reminder(r) for r in rows]

    async def list_due_globally(self, now: datetime, limit: int = 100) -> list[Reminder]:
        """Cross-boss query for scheduler worker."""
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM scheduled_reminders
                WHERE status='pending' AND due_at <= $1
                ORDER BY due_at LIMIT $2
                """,
                now,
                limit,
            )
            return [_row_to_reminder(r) for r in rows]

    async def insert(
        self,
        text: str,
        due_at: datetime,
        scope: str,
        created_by_op: str,
        provider: str | None = None,
        chat_id: str | None = None,
        bot_account_id: int | None = None,
        recurring: str | None = None,
        action_item_id: int | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, provider,
                                                 chat_id, bot_account_id, recurring,
                                                 action_item_id, created_by_op)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
                """,
                self.ctx.boss_id,
                text,
                due_at,
                scope,
                provider,
                chat_id,
                bot_account_id,
                recurring,
                action_item_id,
                created_by_op,
            )

    async def mark_fired(self, reminder_id: int, now: datetime) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE scheduled_reminders
                SET status=$2, fired_at=$3
                WHERE id=$1
                """,
                reminder_id,
                ReminderStatus.FIRED.value,
                now,
            )

    async def mark_error(self, reminder_id: int, error: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE scheduled_reminders SET status='error', last_error=$2 WHERE id=$1
                """,
                reminder_id,
                error,
            )
