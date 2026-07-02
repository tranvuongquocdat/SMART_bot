"""BotAccountStatusSync: event bridge/health job → persist bot_accounts.status.

Không có subscriber này, bridge báo 'disconnected fatal' (session Zalo chết)
mà DB vẫn 'active' → trang Channels lừa boss là mọi thứ ổn.
"""

from __future__ import annotations

import asyncio

import pytest

from src.events.bus import InMemoryEventBus
from src.services.bot_account_status import BotAccountStatusSync


async def _acc(pool, status="active"):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO bot_accounts (provider, provider_user_id, account_kind, "
            "ownership, status) VALUES ('zalo', $1, 'personal', 'platform', $2) "
            "RETURNING id",
            f"status-sync-{status}",
            status,
        )


async def _status(pool, acc_id):
    async with pool.acquire() as c:
        return await c.fetchrow(
            "SELECT status, status_reason FROM bot_accounts WHERE id=$1", acc_id
        )


@pytest.mark.asyncio
async def test_logged_out_persisted(clean_db):
    acc = await _acc(clean_db)
    bus = InMemoryEventBus()
    BotAccountStatusSync(clean_db).register(bus)

    await bus.publish(
        "bot_account.status_changed",
        {"bot_account_id": acc, "to": "logged_out", "reason": "session expired"},
    )
    await asyncio.sleep(0)
    row = await _status(clean_db, acc)
    assert row["status"] == "logged_out"
    assert row["status_reason"] == "session expired"


@pytest.mark.asyncio
async def test_recovery_back_to_active(clean_db):
    acc = await _acc(clean_db, status="rate_limited")
    bus = InMemoryEventBus()
    BotAccountStatusSync(clean_db).register(bus)

    await bus.publish(
        "bot_account.status_changed",
        {"bot_account_id": acc, "to": "active", "reason": None},
    )
    await asyncio.sleep(0)
    assert (await _status(clean_db, acc))["status"] == "active"


@pytest.mark.asyncio
async def test_unknown_status_ignored(clean_db):
    acc = await _acc(clean_db)
    bus = InMemoryEventBus()
    BotAccountStatusSync(clean_db).register(bus)

    await bus.publish(
        "bot_account.status_changed",
        {"bot_account_id": acc, "to": "exploded", "reason": "x"},
    )
    await bus.publish("bot_account.status_changed", {"to": "logged_out"})
    await asyncio.sleep(0)
    assert (await _status(clean_db, acc))["status"] == "active"
