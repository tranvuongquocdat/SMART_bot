"""ReminderService — create / fetch_due / mark + recurring next.

Used by:
- Task D0 tools: set_reminder, cancel_reminder, list_reminders
- Task D4 ReminderFirer operation
- Task F1 (Batch F) APScheduler poll loop → fetch_due
"""

from datetime import datetime, timedelta

from src.repositories.base import BossContext
from src.repositories.reminders import RemindersRepo


_WEEKDAY_MAP = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _parse_weekly(spec: str) -> list[int]:
    """`weekly:mon,wed,fri` → [0, 2, 4]"""
    if not spec.startswith("weekly:"):
        return []
    out = []
    for d in spec[len("weekly:") :].split(","):
        d = d.strip().lower()[:3]
        if d in _WEEKDAY_MAP:
            out.append(_WEEKDAY_MAP[d])
    return sorted(set(out))


class ReminderService:
    def __init__(self, pool, bus):
        self.pool = pool
        self.bus = bus

    async def create(
        self,
        boss_id: int,
        text: str,
        due_at: datetime,
        scope: str,
        chat_id: str | None,
        recurring: str | None,
        created_by_op: str,
        provider: str | None = None,
    ) -> int:
        repo = RemindersRepo(self.pool, BossContext(boss_id, "boss"))
        rid = await repo.insert(
            text=text,
            due_at=due_at,
            scope=scope,
            created_by_op=created_by_op,
            provider=provider,
            chat_id=chat_id,
            recurring=recurring,
        )
        await self.bus.publish(
            "reminder.set",
            {
                "reminder_id": rid,
                "boss_id": boss_id,
                "due_at": due_at.isoformat(),
            },
        )
        return rid

    async def fetch_due(self, now: datetime, limit: int = 100):
        """Cross-boss fetch — superadmin only (used by APScheduler in Batch F)."""
        repo = RemindersRepo(self.pool, BossContext(0, "superadmin"))
        return await repo.list_due_globally(now, limit=limit)

    async def mark_fired(self, reminder_id: int) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE scheduled_reminders SET status='fired', fired_at=NOW() WHERE id=$1",
                reminder_id,
            )

    async def mark_failed(self, reminder_id: int, error: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE scheduled_reminders SET status='failed', last_error=$2 WHERE id=$1",
                reminder_id,
                error,
            )

    async def create_next(self, prev_row) -> int | None:
        """Schedule the next occurrence of a recurring reminder, return new id."""
        recurring = prev_row["recurring"]
        if not recurring:
            return None
        prev_due: datetime = prev_row["due_at"]
        if recurring == "daily":
            next_due = prev_due + timedelta(days=1)
        elif recurring.startswith("weekly:"):
            wdays = _parse_weekly(recurring)
            if not wdays:
                return None
            # find next weekday strictly greater than prev_due.weekday()
            cur = prev_due.weekday()
            cands = [(d - cur) % 7 or 7 for d in wdays]
            delta_days = min(cands)
            next_due = prev_due + timedelta(days=delta_days)
        else:
            return None
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO scheduled_reminders
                  (boss_id, text, due_at, scope, provider, chat_id, recurring,
                   created_by_op, status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pending')
                RETURNING id
                """,
                prev_row["boss_id"],
                prev_row["text"],
                next_due,
                prev_row["scope"],
                prev_row["provider"],
                prev_row["chat_id"],
                recurring,
                prev_row["created_by_op"],
            )
