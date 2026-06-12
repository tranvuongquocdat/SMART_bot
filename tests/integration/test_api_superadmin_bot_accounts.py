"""Tests for SP2-9 bot-accounts CRUD endpoints:
  POST   /api/v1/superadmin/bot-accounts
  PATCH  /api/v1/superadmin/bot-accounts/:id
  DELETE /api/v1/superadmin/bot-accounts/:id
  GET    /api/v1/superadmin/bot-accounts/:id/messages
"""
from __future__ import annotations

import asyncio

import pytest

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-bot-accounts"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_bot_account(clean_db):
    """Insert a bot_accounts row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            bid = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ($1, $2, $3, $4, $5, 'active')
                RETURNING id
                """,
                "zalo",
                "za_crud_001",
                "Bot CRUD Test",
                "personal",
                "platform",
            )
            return int(bid)

    bid = asyncio.get_event_loop().run_until_complete(_async())
    return type("BotAcc", (), {"id": bid})()


# ---------------------------------------------------------------------------
# POST /bot-accounts
# ---------------------------------------------------------------------------

def test_create_bot_account_requires_superadmin(client, logged_in_boss):
    r = client.post(
        "/api/v1/superadmin/bot-accounts",
        json={"provider": "zalo", "label": "Test Bot", "handle": "za_new"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_create_bot_account_success(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/bot-accounts",
        json={
            "provider": "telegram",
            "label": "My Telegram Bot",
            "handle": "@mybot",
            "account_kind": "official",
            "ownership": "platform",
        },
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert isinstance(data["id"], int)


# ---------------------------------------------------------------------------
# PATCH /bot-accounts/:id
# ---------------------------------------------------------------------------

def test_patch_bot_account_requires_superadmin(client, logged_in_boss, seed_bot_account):
    r = client.patch(
        f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}",
        json={"label": "Updated"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_patch_bot_account_success(client, logged_in_superadmin, seed_bot_account):
    r = client.patch(
        f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}",
        json={"label": "Renamed Bot", "ownership": "platform"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["id"] == seed_bot_account.id


def test_patch_bot_account_not_found(client, logged_in_superadmin):
    r = client.patch(
        "/api/v1/superadmin/bot-accounts/999999",
        json={"label": "Ghost"},
        headers=_csrf(client),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /bot-accounts/:id
# ---------------------------------------------------------------------------

def test_delete_bot_account_requires_superadmin(client, logged_in_boss, seed_bot_account):
    r = client.delete(
        f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}",
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_delete_bot_account_success(client, logged_in_superadmin, seed_bot_account):
    r = client.delete(
        f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}",
        headers=_csrf(client),
    )
    assert r.status_code == 204


def test_delete_bot_account_not_found(client, logged_in_superadmin):
    r = client.delete(
        "/api/v1/superadmin/bot-accounts/999999",
        headers=_csrf(client),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /bot-accounts/:id/messages
# ---------------------------------------------------------------------------

def test_messages_requires_superadmin(client, logged_in_boss, seed_bot_account):
    r = client.get(f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}/messages")
    assert r.status_code == 403


def test_messages_returns_empty_list(client, logged_in_superadmin, seed_bot_account):
    r = client.get(f"/api/v1/superadmin/bot-accounts/{seed_bot_account.id}/messages")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_messages_not_found(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/bot-accounts/999999/messages")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Detail + QR login + thống kê theo ngày
# ---------------------------------------------------------------------------


def _seed_zalo_account(clean_db) -> int:
    import asyncio

    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ('zalo', 'z-stat-1', 'Stat Bot', 'personal', 'platform', 'active')
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET status='active'
                RETURNING id
                """
            )

    return asyncio.get_event_loop().run_until_complete(_())


def test_detail_returns_assignments_and_credentials_flag(client, logged_in_superadmin, clean_db):
    acc_id = _seed_zalo_account(clean_db)
    r = client.get(f"/api/v1/superadmin/bot-accounts/{acc_id}/detail")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "zalo"
    assert body["has_credentials"] is False
    assert isinstance(body["assignments"], list)


def test_qr_login_rejects_non_zalo(client, logged_in_superadmin, clean_db):
    import asyncio

    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ('telegram', 'tg-stat-1', 'TG Bot', 'personal', 'platform', 'active')
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET status='active'
                RETURNING id
                """
            )

    tg_id = asyncio.get_event_loop().run_until_complete(_())
    from src.web.security import CSRF_COOKIE

    client.cookies.set(CSRF_COOKIE, "csrf-bot-qr")
    r = client.post(
        f"/api/v1/superadmin/bot-accounts/{tg_id}/qr-login",
        json={},
        headers={"X-CSRF-Token": "csrf-bot-qr"},
    )
    assert r.status_code == 422


def test_qr_login_status_unknown(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/bot-accounts/qr-login/deadbeef")
    assert r.status_code == 404


def test_daily_stats_full_series(client, logged_in_superadmin, clean_db):
    import asyncio

    acc_id = _seed_zalo_account(clean_db)

    async def _seed_msgs():
        async with clean_db.acquire() as c:
            boss_id = await c.fetchval(
                """
                INSERT INTO users (email, name, role) VALUES ('stat-boss@t.local', 'B', 'boss')
                ON CONFLICT (email) DO UPDATE SET role='boss' RETURNING id
                """
            )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
                ON CONFLICT (boss_id, provider) DO UPDATE SET bot_account_id=$2, status='active'
                """,
                boss_id,
                acc_id,
            )
            await c.execute(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type,
                                      sender_provider_id, sender_name, text, ts)
                VALUES
                  ($1,'zalo','g1','group','u1','A','hôm nay', NOW()),
                  ($1,'zalo','g1','group','u1','A','hôm qua', NOW() - INTERVAL '1 day'),
                  ($1,'zalo','g1','group','u2','B','hôm qua 2', NOW() - INTERVAL '1 day')
                """,
                boss_id,
            )
            await c.execute(
                """
                INSERT INTO outbound_messages (boss_id, provider, chat_id, content, trigger, status)
                VALUES ($1, 'zalo', 'g1', 'reply', 'group', 'sent')
                """,
                boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_seed_msgs())

    r = client.get(f"/api/v1/superadmin/bot-accounts/{acc_id}/stats/daily?days=7")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 7  # đủ ngày kể cả ngày 0 tin
    today = rows[0]
    yesterday = rows[1]
    assert today["received"] == 1 and today["sent"] == 1
    assert yesterday["received"] == 2 and yesterday["sent"] == 0
