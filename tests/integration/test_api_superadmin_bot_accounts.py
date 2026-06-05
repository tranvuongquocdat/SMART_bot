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
