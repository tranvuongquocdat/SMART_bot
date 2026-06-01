"""subscription_check job — flips users.subscription_status past expiry.

Two transitions:
  - ``active`` → ``expired_grace`` once expiry passes.
  - ``expired_grace`` → ``expired`` after a 30-day grace window.

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
