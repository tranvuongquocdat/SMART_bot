"""Tests for get_effective_limits() and check_over_limit()."""
from __future__ import annotations

import asyncio

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _set_boss_plan(clean_db, boss_id, plan_name, overrides="{}"):
    async def _():
        async with clean_db.acquire() as c:
            plan_id = await c.fetchval("SELECT id FROM plans WHERE name=$1", plan_name)
            await c.execute(
                "UPDATE users SET plan_id=$2, plan_overrides_json=$3::jsonb WHERE id=$1",
                boss_id,
                plan_id,
                overrides,
            )

    _run(_())


# ---------------------------------------------------------------------------
# get_effective_limits
# ---------------------------------------------------------------------------


def test_effective_limits_from_starter_plan(clean_db, logged_in_boss):
    from src.services.subscription import get_effective_limits

    _set_boss_plan(clean_db, logged_in_boss.boss_id, "starter")
    limits = _run(get_effective_limits(clean_db, logged_in_boss.boss_id))

    assert limits.max_active_groups == 5
    assert limits.max_active_tools == 10
    assert limits.max_active_channels == 1
    assert limits.mcp_slots == 0
    assert limits.cost_cap_usd_daily == 2.0


def test_effective_limits_override_wins(clean_db, logged_in_boss):
    from src.services.subscription import get_effective_limits

    _set_boss_plan(
        clean_db,
        logged_in_boss.boss_id,
        "starter",
        overrides='{"max_active_groups": 50}',
    )
    limits = _run(get_effective_limits(clean_db, logged_in_boss.boss_id))

    assert limits.max_active_groups == 50  # override
    assert limits.max_active_tools == 10  # from plan


def test_effective_limits_null_is_unlimited(clean_db, logged_in_boss):
    from src.services.subscription import get_effective_limits

    _set_boss_plan(clean_db, logged_in_boss.boss_id, "custom")
    limits = _run(get_effective_limits(clean_db, logged_in_boss.boss_id))

    assert limits.max_active_groups is None
    assert limits.max_active_tools is None
    assert limits.mcp_slots is None


def test_effective_limits_no_plan_returns_none(clean_db, logged_in_boss):
    """Boss with no plan_id returns all-None limits (treated as unlimited)."""
    from src.services.subscription import get_effective_limits

    _run(
        _exec(
            clean_db,
            "UPDATE users SET plan_id=NULL WHERE id=$1",
            logged_in_boss.boss_id,
        )
    )
    limits = _run(get_effective_limits(clean_db, logged_in_boss.boss_id))
    assert limits.max_active_groups is None


def _exec(pool, sql, *args):
    async def _():
        async with pool.acquire() as c:
            await c.execute(sql, *args)

    return _()


# ---------------------------------------------------------------------------
# check_over_limit
# ---------------------------------------------------------------------------


def test_check_over_limit_clean_boss(clean_db, logged_in_boss):
    """Newly created boss with pro plan and nothing active is not over limit."""
    from src.services.subscription import check_over_limit

    _set_boss_plan(clean_db, logged_in_boss.boss_id, "pro")
    over = _run(check_over_limit(clean_db, logged_in_boss.boss_id))

    assert over.groups == 0
    assert over.tools == 0
    assert over.channels == 0
    assert over.mcp == 0
    assert not over.any_over


def test_check_over_limit_detects_group_excess(clean_db, logged_in_boss):
    """If boss has more active groups than plan allows, over.groups > 0."""
    from src.services.subscription import check_over_limit

    # Set trial plan: max 2 groups
    _set_boss_plan(clean_db, logged_in_boss.boss_id, "trial")

    # Insert 3 active groups
    async def _seed_groups():
        async with clean_db.acquire() as c:
            for i in range(3):
                await c.execute(
                    "INSERT INTO group_notes (boss_id, provider, chat_id, group_name, is_active) "
                    "VALUES ($1, 'telegram', $2, $3, TRUE)",
                    logged_in_boss.boss_id,
                    f"chat_{i}",
                    f"Group {i}",
                )

    _run(_seed_groups())
    over = _run(check_over_limit(clean_db, logged_in_boss.boss_id))

    assert over.groups == 1  # 3 active, limit 2 → over by 1
    assert over.any_over


def test_check_over_limit_null_limit_never_over(clean_db, logged_in_boss):
    """Custom plan (null limits) is never over-limit regardless of count."""
    from src.services.subscription import check_over_limit

    _set_boss_plan(clean_db, logged_in_boss.boss_id, "custom")

    async def _seed():
        async with clean_db.acquire() as c:
            for i in range(100):
                await c.execute(
                    "INSERT INTO group_notes (boss_id, provider, chat_id, is_active) "
                    "VALUES ($1, 'telegram', $2, TRUE)",
                    logged_in_boss.boss_id,
                    f"chat_{i}",
                )

    _run(_seed())
    over = _run(check_over_limit(clean_db, logged_in_boss.boss_id))

    assert over.groups == 0
    assert not over.any_over
