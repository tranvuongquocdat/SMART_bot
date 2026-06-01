"""Cache-hit-ratio gauge updater.

Rolls up ``SUM(tokens_cached) / SUM(tokens_in)`` over the trailing 1h per
(feature, model) and pushes it onto the Prometheus gauge so dashboards can
chart how well prompt caching is working without scanning ``token_usage``
each scrape.

Runs every 60s.
"""

from __future__ import annotations

import logging
from typing import Any

from src.infra.metrics import cache_hit_ratio

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    if getattr(app_state, "db_pool", None) is None:
        return
    try:
        async with app_state.db_pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT feature, model,
                       SUM(tokens_cached)::FLOAT / NULLIF(SUM(tokens_in), 0) AS ratio
                FROM token_usage
                WHERE called_at > NOW() - INTERVAL '1 hour'
                GROUP BY feature, model
                """
            )
        for r in rows:
            ratio = float(r["ratio"] or 0.0)
            cache_hit_ratio.labels(feature=r["feature"], model=r["model"]).set(ratio)
    except Exception:
        log.exception("cache_hit_ratio job failed")
