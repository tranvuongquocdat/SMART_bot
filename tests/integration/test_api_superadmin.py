"""Tests for /api/v1/superadmin/* endpoints."""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def seed_bot_account(clean_db):
    """Insert a bot_accounts row and return its id."""
    async def _seed():
        async with clean_db.acquire() as c:
            bid = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                "zalo", "za_test_001", "Trợ lý Test", "personal", "platform", "active",
            )
            return int(bid)

    bid = asyncio.get_event_loop().run_until_complete(_seed())
    return type("BotAcc", (), {"id": bid})()


# ---------------------------------------------------------------------------
# Tests: /api/v1/superadmin/model-slots
# ---------------------------------------------------------------------------

def test_model_slots_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/model-slots")
    assert r.status_code == 403


def test_model_slots_returns_three_slots(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/model-slots")
    assert r.status_code == 200
    slots = r.json()
    assert {s["slot"] for s in slots} == {"smart", "fast", "vision"}
    for s in slots:
        assert "model" in s
        assert "provider" in s
        assert s["status"] in ("active", "fallback", "missing")


# ---------------------------------------------------------------------------
# Tests: /api/v1/superadmin/bot-accounts
# ---------------------------------------------------------------------------

def test_bot_accounts_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/bot-accounts")
    assert r.status_code == 403


def test_bot_accounts_returns_list_with_stats(client, logged_in_superadmin, seed_bot_account):
    r = client.get("/api/v1/superadmin/bot-accounts?range=7d")
    assert r.status_code == 200
    accounts = r.json()
    # At least the seeded bot_account plus possibly the web test bot
    assert len(accounts) >= 1
    # Find our seeded zalo account
    zalo_accounts = [a for a in accounts if a["channel"] == "zalo"]
    assert len(zalo_accounts) >= 1
    acc = zalo_accounts[0]
    assert "id" in acc
    assert acc["channel"] in ("zalo", "telegram", "lark", "web")
    assert "messages_in" in acc
    assert "messages_out" in acc
    assert acc["status"] in ("online", "warn", "offline")
