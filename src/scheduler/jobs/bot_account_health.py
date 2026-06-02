"""bot_account_health job — detect dead channel bridges.

Asks each registered adapter for its ``health_check()`` map
``{bot_account_id: is_alive}``; any entry flipping to dead triggers
a ``bot_accounts.status='logged_out'`` update and
``bot_account.status_changed`` publish so downstream watchers (UI,
admin alerts) react.
"""

from __future__ import annotations

import logging
from typing import Any

from src.infra.metrics import active_sessions

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    registry = getattr(app_state, "channel_registry", None)
    if registry is None:
        return
    for adapter in registry.adapters():
        provider = adapter.provider
        try:
            health = await adapter.health_check()
        except Exception:
            log.exception("health_check failed for provider=%s", provider)
            continue
        alive = 0
        for bot_acc_id, is_alive in list(health.items()):
            if is_alive:
                alive += 1
                continue
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
            # Tell the adapter to drop its bookkeeping for this dead session.
            procs = getattr(adapter, "_procs", None)
            if isinstance(procs, dict):
                procs.pop(bot_acc_id, None)
        try:
            active_sessions.labels(channel=provider).set(alive)
        except Exception:
            log.exception("metrics: active_sessions set failed")
