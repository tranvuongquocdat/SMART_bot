"""Integration tests for APScheduler jobs.

Hits the real Postgres via ``db_pool`` fixture; jobs are invoked directly
(no AsyncIOScheduler in the loop) so they're deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from src.events.bus import InMemoryEventBus
from src.scheduler.jobs.bot_account_health import job as health_job
from src.scheduler.jobs.reminder_firer import job as remind_job
from src.scheduler.jobs.subscription_check import job as sub_job


class _State:
    def __init__(self, db_pool, bus, channel_registry=None):
        self.db_pool = db_pool
        self.bus = bus
        self.channel_registry = channel_registry


def _make_registry(adapter):
    from src.channels.registry import ChannelRegistry
    r = ChannelRegistry()
    r.register(adapter)
    return r


@pytest.mark.asyncio
async def test_reminder_firer_job_publishes_due_only(db_pool, boss_user):
    """Job publishes one reminder.due per row whose due_at <= now."""
    boss_id = boss_user["id"]
    now = datetime.now(tz=timezone.utc)
    async with db_pool.acquire() as c:
        # truncate so we get a clean state regardless of prior test residue
        await c.execute("TRUNCATE scheduled_reminders RESTART IDENTITY")
        due_id = await c.fetchval(
            """
            INSERT INTO scheduled_reminders
              (boss_id, text, due_at, scope, provider, chat_id, status,
               created_by_op)
            VALUES ($1,'past',$2,'dm','zalo','c1','pending','t')
            RETURNING id
            """,
            boss_id,
            now - timedelta(minutes=1),
        )
        future_id = await c.fetchval(
            """
            INSERT INTO scheduled_reminders
              (boss_id, text, due_at, scope, provider, chat_id, status,
               created_by_op)
            VALUES ($1,'future',$2,'dm','zalo','c1','pending','t')
            RETURNING id
            """,
            boss_id,
            now + timedelta(hours=1),
        )

    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    seen: list[dict] = []

    async def collect(p: dict) -> None:
        seen.append(p)

    bus.subscribe("reminder.due", collect)
    await remind_job(state)

    ids = [s["reminder_id"] for s in seen]
    assert due_id in ids
    assert future_id not in ids


@pytest.mark.asyncio
async def test_bot_account_health_marks_dead_process(db_pool, boss_user):
    """A subprocess whose returncode is non-None gets flipped to logged_out."""
    async with db_pool.acquire() as c:
        bot_id = await c.fetchval(
            """
            INSERT INTO bot_accounts (provider, provider_user_id, account_kind,
                                       ownership, owner_boss_id, status)
            VALUES ('zalo','uid-1','user','boss_owned',$1,'active')
            RETURNING id
            """,
            boss_user["id"],
        )

    bus = InMemoryEventBus()
    procs: dict[int, Any] = {bot_id: SimpleNamespace(returncode=1)}

    async def _health():
        return {b: (p.returncode is None) for b, p in procs.items()}

    fake_adapter = SimpleNamespace(
        provider="zalo", health_check=_health, _procs=procs
    )
    state = _State(db_pool, bus, channel_registry=_make_registry(fake_adapter))

    events: list[dict] = []

    async def collect(p: dict) -> None:
        events.append(p)

    bus.subscribe("bot_account.status_changed", collect)
    await health_job(state)

    assert any(
        e["bot_account_id"] == bot_id and e["to"] == "logged_out"
        for e in events
    )
    async with db_pool.acquire() as c:
        st = await c.fetchval(
            "SELECT status FROM bot_accounts WHERE id=$1", bot_id
        )
    assert st == "logged_out"
    assert bot_id not in procs


@pytest.mark.asyncio
async def test_bot_account_health_skips_alive(db_pool, boss_user):
    async with db_pool.acquire() as c:
        bot_id = await c.fetchval(
            """
            INSERT INTO bot_accounts (provider, provider_user_id, account_kind,
                                       ownership, owner_boss_id, status)
            VALUES ('zalo','uid-2','user','boss_owned',$1,'active')
            RETURNING id
            """,
            boss_user["id"],
        )

    bus = InMemoryEventBus()
    procs: dict[int, Any] = {bot_id: SimpleNamespace(returncode=None)}

    async def _health():
        return {b: (p.returncode is None) for b, p in procs.items()}

    fake_adapter = SimpleNamespace(
        provider="zalo", health_check=_health, _procs=procs
    )
    state = _State(db_pool, bus, channel_registry=_make_registry(fake_adapter))
    await health_job(state)

    async with db_pool.acquire() as c:
        st = await c.fetchval(
            "SELECT status FROM bot_accounts WHERE id=$1", bot_id
        )
    assert st == "active"
    assert bot_id in procs


@pytest.mark.asyncio
async def test_subscription_check_flips_expired(db_pool):
    async with db_pool.acquire() as c:
        expired_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role, subscription_status,
                               subscription_expiry)
            VALUES ('e@x','E','boss','active', NOW() - INTERVAL '1 day')
            RETURNING id
            """
        )
        grace_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role, subscription_status,
                               subscription_expiry)
            VALUES ('g@x','G','boss','expired_grace', NOW() - INTERVAL '40 days')
            RETURNING id
            """
        )
        active_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role, subscription_status,
                               subscription_expiry)
            VALUES ('a@x','A','boss','active', NOW() + INTERVAL '30 days')
            RETURNING id
            """
        )

    state = _State(db_pool, InMemoryEventBus())
    await sub_job(state)

    async with db_pool.acquire() as c:
        rows = {
            r["id"]: r["subscription_status"]
            for r in await c.fetch(
                "SELECT id, subscription_status FROM users WHERE id = ANY($1)",
                [expired_id, grace_id, active_id],
            )
        }
    assert rows[expired_id] == "expired_grace"
    assert rows[grace_id] == "expired"
    assert rows[active_id] == "active"
