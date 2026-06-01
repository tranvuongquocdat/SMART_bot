"""reminder_firer job — publishes ``reminder.due`` for rows past due.

The actual fire-once semantics live in ``src.agents.reminder_firer``; this
job is only a producer. We cap the per-tick scan at 50 rows to avoid a
burst storming the bus on first boot after downtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    now = datetime.now(timezone.utc)
    async with app_state.db_pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, boss_id FROM scheduled_reminders
            WHERE status='pending' AND due_at <= $1
            ORDER BY due_at
            LIMIT 50
            """,
            now,
        )
    for r in rows:
        await app_state.bus.publish(
            "reminder.due",
            {"reminder_id": r["id"], "boss_id": r["boss_id"]},
        )
