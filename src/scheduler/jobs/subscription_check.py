"""subscription_check job — flips users.subscription_status past expiry.

Transitions:
  - ``active`` → ``expired_grace`` once expiry passes.
  - ``expired_grace`` → ``expired`` after a 30-day grace window.
  - ``expired_grace`` users are degraded to trial plan limits so they keep
    the app at trial capacity instead of being fully blocked.

This is a no-op for trial/expired/canceled users.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    async with app_state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE users SET subscription_status='expired_grace'
            WHERE subscription_status='active'
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < NOW()
            """
        )
        await c.execute(
            """
            UPDATE users SET subscription_status='expired'
            WHERE subscription_status='expired_grace'
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < NOW() - INTERVAL '30 days'
            """
        )
        # Degrade expired_grace users to trial plan limits so they still
        # get trial-level access instead of being fully blocked.
        trial = await c.fetchrow(
            "SELECT id, limits_json FROM plans WHERE name='trial'"
        )
        if trial:
            limits = trial["limits_json"]
            if isinstance(limits, str):
                import json as _json
                limits = _json.loads(limits)
            cap = float(limits.get("cost_cap_usd_daily") or 0.5)
            await c.execute(
                """
                UPDATE users SET
                    plan_id             = $1,
                    plan_overrides_json = '{}'::jsonb,
                    cost_cap_usd_daily  = $2
                WHERE subscription_status = 'expired_grace'
                  AND (plan_id IS NULL OR plan_id != $1)
                """,
                trial["id"],
                cap,
            )
            log.info("subscription_check: ran expired_grace degrade to trial limits")
