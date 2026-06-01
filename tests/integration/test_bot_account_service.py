"""BotAccountService lifecycle — auto_assign, accept, decline, disable,
switch_mode, capacity enforcement.

Adapter is a stub: we only care that ``start_inbound`` and ``stop_inbound``
are called at the right transition points; the bridge subprocess is not
launched.
"""

from __future__ import annotations

import pytest

from src.events.bus import InMemoryEventBus
from src.services.bot_account_service import (
    BotAccountService,
    InvalidOwnershipError,
    NoCapacityError,
)
from src.services.bot_account_session import encrypt_credentials


class _StubAdapter:
    def __init__(self):
        self.started: list[int] = []
        self.stopped: list[int] = []

    async def start_inbound(self, bot_acc):
        self.started.append(bot_acc.id)

    async def stop_inbound(self, bot_acc):
        self.stopped.append(bot_acc.id)


async def _seed_platform_bot_account(pool, label: str, max_assigned: int = 5):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status,
               display_name, max_assigned_bosses)
            VALUES ('zalo', $1, 'personal', 'platform', 'active', $1, $2)
            RETURNING id
            """,
            label,
            max_assigned,
        )


async def _seed_boss_owned_bot_account(pool, label: str, owner_boss_id: int):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status,
               owner_boss_id, display_name)
            VALUES ('zalo', $1, 'personal', 'boss_owned', 'active', $2, $1)
            RETURNING id
            """,
            label,
            owner_boss_id,
        )


@pytest.mark.asyncio
async def test_auto_assign_picks_a_platform_account(db_pool, boss_user):
    bus = InMemoryEventBus()
    adapter = _StubAdapter()
    svc = BotAccountService(db_pool, bus, {"zalo": adapter})
    bot_acc_id = await _seed_platform_bot_account(db_pool, "p1")
    chosen = await svc.auto_assign(boss_user["id"], "zalo")
    assert chosen == bot_acc_id
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM bot_account_assignments WHERE boss_id=$1 AND provider='zalo'",
            boss_user["id"],
        )
    assert row["status"] == "pending_accept"
    assert row["assignment_kind"] == "platform_assigned"


@pytest.mark.asyncio
async def test_auto_assign_no_capacity(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    with pytest.raises(NoCapacityError):
        await svc.auto_assign(boss_user["id"], "zalo")


@pytest.mark.asyncio
async def test_auto_assign_respects_max_capacity(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    bot_acc_id = await _seed_platform_bot_account(db_pool, "p2", max_assigned=1)
    # Saturate with a second user.
    async with db_pool.acquire() as c:
        other = await c.fetchval(
            "INSERT INTO users (email,name,role) VALUES ('o@x.com','o','boss') RETURNING id"
        )
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
            """,
            other,
            bot_acc_id,
        )
    with pytest.raises(NoCapacityError):
        await svc.auto_assign(boss_user["id"], "zalo")


@pytest.mark.asyncio
async def test_auto_assign_then_accept_starts_inbound(db_pool, boss_user):
    bus = InMemoryEventBus()
    adapter = _StubAdapter()
    svc = BotAccountService(db_pool, bus, {"zalo": adapter})
    bot_acc_id = await _seed_platform_bot_account(db_pool, "p3")
    await svc.auto_assign(boss_user["id"], "zalo")
    result = await svc.accept(boss_user["id"], "zalo")
    assert result == bot_acc_id
    assert bot_acc_id in adapter.started
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status, accepted_at FROM bot_account_assignments "
            "WHERE boss_id=$1 AND provider='zalo'",
            boss_user["id"],
        )
    assert row["status"] == "active"
    assert row["accepted_at"] is not None


@pytest.mark.asyncio
async def test_decline_marks_revoked(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    await _seed_platform_bot_account(db_pool, "p4")
    await svc.auto_assign(boss_user["id"], "zalo")
    await svc.decline(boss_user["id"], "zalo", reason="changed mind")
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status FROM bot_account_assignments WHERE boss_id=$1 AND provider='zalo'",
            boss_user["id"],
        )
    assert row["status"] == "revoked"


@pytest.mark.asyncio
async def test_assign_boss_owned_rejects_wrong_owner(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    # Owned by a DIFFERENT boss.
    async with db_pool.acquire() as c:
        other = await c.fetchval(
            "INSERT INTO users (email,name,role) VALUES ('o2@x.com','o2','boss') RETURNING id"
        )
    bot_acc_id = await _seed_boss_owned_bot_account(db_pool, "owned-1", other)
    with pytest.raises(InvalidOwnershipError):
        await svc.assign_boss_owned(boss_user["id"], "zalo", bot_acc_id)


@pytest.mark.asyncio
async def test_assign_boss_owned_then_accept(db_pool, boss_user):
    bus = InMemoryEventBus()
    adapter = _StubAdapter()
    svc = BotAccountService(db_pool, bus, {"zalo": adapter})
    bot_acc_id = await _seed_boss_owned_bot_account(db_pool, "owned-2", boss_user["id"])
    await svc.assign_boss_owned(boss_user["id"], "zalo", bot_acc_id)
    await svc.accept(boss_user["id"], "zalo")
    assert bot_acc_id in adapter.started


@pytest.mark.asyncio
async def test_disable_boss_owned_pauses_and_audits(db_pool, boss_user):
    bus = InMemoryEventBus()
    adapter = _StubAdapter()
    svc = BotAccountService(db_pool, bus, {"zalo": adapter})
    bot_acc_id = await _seed_boss_owned_bot_account(db_pool, "owned-3", boss_user["id"])
    await svc.disable_boss_owned(
        bot_acc_id, reason="user request", by_user_id=boss_user["id"]
    )
    async with db_pool.acquire() as c:
        row = await c.fetchrow("SELECT status, status_reason FROM bot_accounts WHERE id=$1", bot_acc_id)
        audit = await c.fetchrow(
            "SELECT * FROM admin_audit_log WHERE target_kind='bot_account' AND target_id=$1",
            str(bot_acc_id),
        )
    assert row["status"] == "paused"
    assert row["status_reason"] == "user request"
    assert audit is not None
    assert audit["action"] == "disable_boss_owned_bot_acc"
    assert bot_acc_id in adapter.stopped


@pytest.mark.asyncio
async def test_disable_rejects_platform_account(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    bot_acc_id = await _seed_platform_bot_account(db_pool, "p-disabled-test")
    with pytest.raises(InvalidOwnershipError):
        await svc.disable_boss_owned(
            bot_acc_id, reason="x", by_user_id=boss_user["id"]
        )


@pytest.mark.asyncio
async def test_switch_mode_revokes_current(db_pool, boss_user):
    bus = InMemoryEventBus()
    svc = BotAccountService(db_pool, bus, {"zalo": _StubAdapter()})
    bot_acc_id = await _seed_platform_bot_account(db_pool, "p5")
    await svc.auto_assign(boss_user["id"], "zalo")
    await svc.accept(boss_user["id"], "zalo")

    events: list[dict] = []
    bus.subscribe(
        "bot_account.mode_switch_requested",
        lambda p: events.append(p) or _noop(),
    )
    await svc.switch_mode(boss_user["id"], "zalo", "boss_owned")
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status FROM bot_account_assignments WHERE boss_id=$1 AND provider='zalo'",
            boss_user["id"],
        )
    assert row["status"] == "revoked"
    assert len(events) == 1
    assert events[0]["from_kind"] == "platform_assigned"
    assert events[0]["to_kind"] == "boss_owned"
    assert events[0]["previous_bot_account_id"] == bot_acc_id


@pytest.mark.asyncio
async def test_credentials_fernet_roundtrip():
    blob = encrypt_credentials({"cookie": "x", "imei": "y", "userAgent": "z"})
    out = __import__("src.services.bot_account_session", fromlist=["decrypt_credentials"]).decrypt_credentials(blob)
    assert out == {"cookie": "x", "imei": "y", "userAgent": "z"}


async def _noop():
    return None
