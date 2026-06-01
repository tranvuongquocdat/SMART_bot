"""bot_account_health job — detect dead Zalo bridge subprocesses.

Scans ``app_state.zalo._procs``; if a subprocess has terminated we flip the
``bot_accounts.status`` to ``logged_out`` and publish
``bot_account.status_changed`` so downstream watchers (UI, admin alerts)
can react.
"""

from __future__ import annotations

import logging
from typing import Any

from src.infra.metrics import active_sessions

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    zalo = getattr(app_state, "zalo", None)
    if zalo is None:
        return
    procs: dict[int, Any] = getattr(zalo, "_procs", {})
    alive = 0
    for bot_acc_id, proc in list(procs.items()):
        if proc.returncode is None:
            alive += 1
            continue  # still alive
        async with app_state.db_pool.acquire() as c:
            await c.execute(
                "UPDATE bot_accounts SET status='logged_out' WHERE id=$1",
                bot_acc_id,
            )
        await app_state.bus.publish(
            "bot_account.status_changed",
            {
                "bot_account_id": bot_acc_id,
                "to": "logged_out",
                "reason": "process_died",
            },
        )
        procs.pop(bot_acc_id, None)
    try:
        active_sessions.labels(channel="zalo").set(alive)
    except Exception:
        log.exception("metrics: active_sessions set failed")
