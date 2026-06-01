"""APScheduler runner — wires periodic jobs against ``app.state``.

Job inventory (MVP):
  - ``reminder_firer``       — every 30s, scan ``scheduled_reminders`` for
                               due rows and publish ``reminder.due``.
  - ``bot_account_health``   — every 60s, sweep Zalo adapter ``_procs`` for
                               dead subprocesses and publish
                               ``bot_account.status_changed``.
  - ``subscription_check``   — daily 02:00 Asia/Ho_Chi_Minh, flip
                               ``users.subscription_status`` past expiry.

Jobstore is in-memory (MVP). For multi-replica deploys swap to PG-backed.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

log = logging.getLogger(__name__)

DEFAULT_TZ = "Asia/Ho_Chi_Minh"


def make_scheduler(app_state: Any) -> AsyncIOScheduler:
    """Build (but do not start) the AsyncIOScheduler bound to ``app_state``."""
    from src.scheduler.jobs.bot_account_health import job as health_job
    from src.scheduler.jobs.reminder_firer import job as remind_job
    from src.scheduler.jobs.subscription_check import job as sub_job

    sched = AsyncIOScheduler(timezone=DEFAULT_TZ)

    async def _remind() -> None:
        try:
            await remind_job(app_state)
        except Exception:
            log.exception("reminder_firer job crashed")

    async def _health() -> None:
        try:
            await health_job(app_state)
        except Exception:
            log.exception("bot_account_health job crashed")

    async def _sub() -> None:
        try:
            await sub_job(app_state)
        except Exception:
            log.exception("subscription_check job crashed")

    sched.add_job(_remind, "interval", seconds=30, id="reminder_firer")
    sched.add_job(_health, "interval", seconds=60, id="bot_account_health")
    sched.add_job(_sub, "cron", hour=2, id="subscription_check")
    return sched
