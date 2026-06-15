"""Tests for superadmin usage analytics + per-bot-account message history."""
from __future__ import annotations

import asyncio


def _seed_usage(clean_db, boss_id, cost=0.5, tokens_in=100, tokens_out=50):
    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO token_usage
                  (boss_id, feature, operation, provider, model,
                   tokens_in, tokens_out, cost_usd, latency_ms, status)
                VALUES ($1, 'dm_responder', 'dm_responder', 'openai', 'gpt-test',
                        $2, $3, $4, 120, 'ok')
                """,
                boss_id, tokens_in, tokens_out, cost,
            )

    asyncio.get_event_loop().run_until_complete(_())


def _seed_account_with_message(clean_db, boss_id) -> int:
    async def _():
        async with clean_db.acquire() as c:
            acc_id = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ('zalo', 'zalo-usage-1', 'Zalo Pool', 'personal', 'platform', 'active')
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET status='active'
                RETURNING id
                """
            )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
                ON CONFLICT (boss_id, provider) DO UPDATE SET bot_account_id=$2, status='active'
                """,
                boss_id, acc_id,
            )
            await c.execute(
                """
                INSERT INTO messages
                  (boss_id, provider, chat_id, chat_type, sender_name, text, ts)
                VALUES ($1, 'zalo', 'z-chat-1', 'group', 'Anh Tân', 'tin nhắn test', NOW())
                """,
                boss_id,
            )
            return acc_id

    return asyncio.get_event_loop().run_until_complete(_())


def test_usage_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/usage")
    assert r.status_code in (401, 403)


def test_usage_returns_platform_totals(client, logged_in_superadmin, clean_db):
    _seed_usage(clean_db, logged_in_superadmin.boss_id, cost=1.25)
    r = client.get("/api/v1/superadmin/usage?range=7d")
    assert r.status_code == 200
    body = r.json()
    assert body["range_days"] == 7
    assert body["totals"]["cost_usd"] >= 1.25
    assert body["totals"]["tokens"] >= 150
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_boss"], list)
    assert len(body["by_boss"]) >= 1
    assert "email" in body["by_boss"][0]


def test_bot_account_messages_returns_rows(client, logged_in_superadmin, clean_db):
    acc_id = _seed_account_with_message(clean_db, logged_in_superadmin.boss_id)
    r = client.get(f"/api/v1/superadmin/bot-accounts/{acc_id}/messages")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["text"] == "tin nhắn test"
    assert body[0]["sender_name"] == "Anh Tân"


def test_bot_account_messages_404(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/bot-accounts/999999/messages")
    assert r.status_code == 404
