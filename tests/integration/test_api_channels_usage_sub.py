"""Integration tests for channels, usage, and subscription API endpoints.

  GET    /api/v1/admin/channels
  POST   /api/v1/admin/channels/{provider}/connect   (stub)
  DELETE /api/v1/admin/channels/{provider}
  GET    /api/v1/admin/usage?range=30d
  GET    /api/v1/admin/subscription
"""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-cus"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


def _seed_channel(clean_db, boss_id: int, provider: str = "zalo") -> str:
    """Insert a bot_account + assignment, return the provider string."""

    async def _async():
        async with clean_db.acquire() as c:
            # Insert bot_account; use ON CONFLICT so re-runs stay clean
            bot_id = await c.fetchval(
                """
                INSERT INTO bot_accounts (provider, provider_user_id, display_name,
                                          account_kind, ownership, status)
                VALUES ($1, $2, $3, 'personal', 'platform', 'active')
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING id
                """,
                provider,
                f"{provider}-bot-seed-001",
                f"{provider.capitalize()} Test Bot",
            )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, $2, $3, 'dedicated', 'active')
                ON CONFLICT (boss_id, provider) DO NOTHING
                """,
                boss_id,
                provider,
                bot_id,
            )

    asyncio.get_event_loop().run_until_complete(_async())
    return provider


def _seed_token_usage(clean_db, boss_id: int) -> None:
    """Insert token_usage rows for the boss."""

    async def _async():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO token_usage
                  (boss_id, feature, operation, provider, model,
                   tokens_in, tokens_out, tokens_cached,
                   cost_usd, cost_saved_cache_usd, latency_ms, status)
                VALUES
                  ($1, 'chat', 'reply', 'openai', 'gpt-4o-mini',
                   100, 200, 0, 0.001, 0, 500, 'ok'),
                  ($1, 'summary', 'summarise', 'groq', 'llama-3.3-70b',
                   50, 80, 0, 0.0002, 0, 300, 'ok')
                """,
                boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_async())


# ---------------------------------------------------------------------------
# GET /api/v1/admin/channels
# ---------------------------------------------------------------------------

def test_list_channels_unauthenticated(client):
    r = client.get("/api/v1/admin/channels")
    assert r.status_code == 401


def test_list_channels_returns_own(client, logged_in_boss, clean_db):
    _seed_channel(clean_db, logged_in_boss.boss_id, "zalo")
    r = client.get("/api/v1/admin/channels")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    providers = [x["provider"] for x in body]
    assert "zalo" in providers
    item = next(x for x in body if x["provider"] == "zalo")
    assert item["status_dot"] in ("ok", "warn", "err", "idle")
    assert "connected_at" in item


# ---------------------------------------------------------------------------
# POST /api/v1/admin/channels/{provider}/connect
# ---------------------------------------------------------------------------

def test_connect_channel_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/channels/zalo/connect", json={})
    assert r.status_code == 403


def test_connect_channel_stub_response(client, logged_in_boss):
    headers = _csrf(client)
    r = client.post("/api/v1/admin/channels/zalo/connect", json={}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "zalo"
    assert body["message"] == "not_implemented"
    assert "redirect_url" in body


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/channels/{provider}
# ---------------------------------------------------------------------------

def test_disconnect_channel_no_csrf(client, logged_in_boss, clean_db):
    _seed_channel(clean_db, logged_in_boss.boss_id, "zalo")
    r = client.delete("/api/v1/admin/channels/zalo")
    assert r.status_code == 403


def test_disconnect_channel_happy_path(client, logged_in_boss, clean_db):
    _seed_channel(clean_db, logged_in_boss.boss_id, "zalo")
    headers = _csrf(client)
    r = client.delete("/api/v1/admin/channels/zalo", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    assert body["provider"] == "zalo"

    # Confirm it's gone
    r2 = client.get("/api/v1/admin/channels")
    providers = [x["provider"] for x in r2.json()]
    assert "zalo" not in providers


# ---------------------------------------------------------------------------
# GET /api/v1/admin/usage
# ---------------------------------------------------------------------------

def test_usage_unauthenticated(client):
    r = client.get("/api/v1/admin/usage")
    assert r.status_code == 401


def test_usage_returns_totals_and_daily(client, logged_in_boss, clean_db):
    _seed_token_usage(clean_db, logged_in_boss.boss_id)
    r = client.get("/api/v1/admin/usage?range=30d")
    assert r.status_code == 200
    body = r.json()
    assert body["range_days"] == 30
    totals = body["totals"]
    assert totals["tokens"] >= 430  # 100+200 + 50+80
    assert totals["cost_usd"] > 0
    assert isinstance(body["daily"], list)
    assert len(body["daily"]) >= 1
    row = body["daily"][0]
    assert "date" in row
    assert "tokens" in row
    assert "cost_usd" in row


# ---------------------------------------------------------------------------
# GET /api/v1/admin/subscription
# ---------------------------------------------------------------------------

def test_subscription_unauthenticated(client):
    r = client.get("/api/v1/admin/subscription")
    assert r.status_code == 401


def test_subscription_returns_plan(client, logged_in_boss):
    r = client.get("/api/v1/admin/subscription")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "plan" in body
    assert "billing_email" in body
    assert "cost_cap_usd_daily" in body
    assert isinstance(body["plan"], str)
