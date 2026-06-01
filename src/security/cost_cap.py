"""Per-boss daily LLM cost cap check.

Sums ``token_usage.cost_usd`` over the trailing 24h, compares to
``users.cost_cap_usd_daily``. Returns a tuple ``(allowed, used, cap)`` so
callers can log structured warnings.

When exhausted the LLM gateway degrades smart→fast (best effort) instead of
hard rejecting — keeps user-visible features alive while signaling the issue
via metrics + logs.
"""

from __future__ import annotations

from typing import Any


async def check_cost_cap(pool: Any, boss_id: int) -> tuple[bool, float, float]:
    """Return (allowed, used_today_usd, cap_usd) for the given boss."""
    async with pool.acquire() as c:
        used = await c.fetchval(
            """
            SELECT COALESCE(SUM(cost_usd), 0) FROM token_usage
            WHERE boss_id=$1 AND called_at > NOW() - INTERVAL '24 hours'
            """,
            boss_id,
        )
        cap = await c.fetchval(
            "SELECT cost_cap_usd_daily FROM users WHERE id=$1", boss_id
        )
    used_f = float(used or 0)
    cap_f = float(cap or 0)
    # cap=0 disables the check (treat as "no cap"); otherwise enforce strictly.
    allowed = cap_f <= 0 or used_f < cap_f
    return allowed, used_f, cap_f
