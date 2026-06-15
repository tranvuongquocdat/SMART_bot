"""Tests for POST /api/v1/admin/channels/{provider}/link-token — handshake token."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-linktoken"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _seed_active_assignment(clean_db, boss_id, provider="zalo"):
    async def _():
        async with clean_db.acquire() as c:
            acc_id = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind,
                   ownership, owner_boss_id, status, max_assigned_bosses)
                VALUES ($1, $2, 'Acc phụ', 'personal', 'boss_owned', $3, 'active', 1)
                RETURNING id
                """,
                provider, f"{provider}-lt-1", boss_id,
            )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, $2, $3, 'boss_owned', 'active')
                """,
                boss_id, provider, acc_id,
            )
            return acc_id

    return asyncio.get_event_loop().run_until_complete(_())


def test_link_token_requires_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/channels/zalo/link-token", json={})
    assert r.status_code == 403


def test_link_token_409_when_not_connected(client, logged_in_boss):
    r = client.post(
        "/api/v1/admin/channels/zalo/link-token", json={}, headers=_csrf(client)
    )
    assert r.status_code == 409


def test_link_token_happy_path(client, logged_in_boss, clean_db):
    _seed_active_assignment(clean_db, logged_in_boss.boss_id, "zalo")
    r = client.post(
        "/api/v1/admin/channels/zalo/link-token", json={}, headers=_csrf(client)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["token"], str) and len(body["token"]) > 10
    assert body["bot_name"]

    # token thật sự nằm trong linking_tokens
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT boss_id FROM linking_tokens WHERE token=$1", body["token"]
            )

    assert asyncio.get_event_loop().run_until_complete(_check()) == logged_in_boss.boss_id
