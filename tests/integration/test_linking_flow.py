"""LinkingService end-to-end + /start <token> handshake via InboundIngest.

We don't run a real bridge — we publish ``inbound.normalized`` directly with
the ``/start <token>`` payload and verify InboundIngest:
  - calls LinkingService.consume
  - inserts account_links row
  - sends an ack via outbound_service (post-hoc ``outbound.send``)
  - does NOT publish message.captured (handshake message swallowed)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.events.bus import InMemoryEventBus
from src.services.linking_service import LinkingService
from src.services.outbound_service import OutboundService


def _dm(bot_acc_id, sender_uid, text, msg_id):
    return InboundMessage(
        bot_account_id=bot_acc_id, provider="zalo", chat_id=sender_uid,
        chat_type="dm", provider_msg_id=msg_id, sender_provider_id=sender_uid,
        sender_name="Boss", text=text, mentions_bot=False,
        reply_to_provider_msg_id=None, media_kind="text", media_url=None,
        ts=datetime.now(timezone.utc))


async def _seed_zalo_bot_account(pool, label: str = "linktest-bot"):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status, display_name)
            VALUES ('zalo', $1, 'personal', 'platform', 'active', $1)
            RETURNING id
            """,
            label,
        )


async def _seed_active_assignment(pool, boss_id: int, bot_account_id: int):
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
            ON CONFLICT (boss_id, provider) DO UPDATE SET
              bot_account_id=EXCLUDED.bot_account_id, status='active'
            """,
            boss_id,
            bot_account_id,
        )


@pytest.mark.asyncio
async def test_generate_and_consume_links_account(db_pool, boss_user):
    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-1")
    svc = LinkingService(db_pool)
    token = await svc.generate(boss_user["id"], "zalo", bot_acc_id)
    assert token and isinstance(token, str)
    out = await svc.consume(token, "sender-99", bot_acc_id)
    assert out == boss_user["id"]
    async with db_pool.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='zalo' AND provider_user_id='sender-99'"
        )
        tok = await c.fetchrow("SELECT * FROM linking_tokens WHERE token=$1", token)
    assert link is not None
    assert link["boss_id"] == boss_user["id"]
    assert tok is None  # consumed


@pytest.mark.asyncio
async def test_consume_invalid_token_returns_none(db_pool, boss_user):
    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-2")
    svc = LinkingService(db_pool)
    out = await svc.consume("does-not-exist", "sender-x", bot_acc_id)
    assert out is None


@pytest.mark.asyncio
async def test_consume_wrong_bot_account_rejected(db_pool, boss_user):
    bot_acc_a = await _seed_zalo_bot_account(db_pool, "lt-3a")
    bot_acc_b = await _seed_zalo_bot_account(db_pool, "lt-3b")
    svc = LinkingService(db_pool)
    token = await svc.generate(boss_user["id"], "zalo", bot_acc_a)
    # Try to consume with a different bot_account.
    out = await svc.consume(token, "sender-y", bot_acc_b)
    assert out is None
    async with db_pool.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider_user_id='sender-y'"
        )
    assert link is None


@pytest.mark.asyncio
async def test_consume_expired_token_rejected(db_pool, boss_user):
    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-4")
    # Insert manually with past expires_at.
    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO linking_tokens (token, boss_id, provider, bot_account_id, expires_at)
            VALUES ('expired-tok', $1, 'zalo', $2, NOW() - INTERVAL '1 minute')
            """,
            boss_user["id"],
            bot_acc_id,
        )
    out = await LinkingService(db_pool).consume("expired-tok", "sender-z", bot_acc_id)
    assert out is None


@pytest.mark.asyncio
async def test_gc_expired_clears_old_tokens(db_pool, boss_user):
    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-5")
    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO linking_tokens (token, boss_id, provider, bot_account_id, expires_at)
            VALUES
              ('alive-1', $1, 'zalo', $2, NOW() + INTERVAL '5 minutes'),
              ('dead-1',  $1, 'zalo', $2, NOW() - INTERVAL '5 minutes'),
              ('dead-2',  $1, 'zalo', $2, NOW() - INTERVAL '1 hour')
            """,
            boss_user["id"],
            bot_acc_id,
        )
    n = await LinkingService(db_pool).gc_expired()
    assert n == 2
    async with db_pool.acquire() as c:
        rows = await c.fetch("SELECT token FROM linking_tokens")
    assert [r["token"] for r in rows] == ["alive-1"]


# --- end-to-end /start handshake via InboundIngest -----------------------------


@pytest.mark.asyncio
async def test_ingest_consumes_start_token_and_acks(db_pool, boss_user):
    bus = InMemoryEventBus()
    InboundIngest(db_pool, bus, OutboundService(db_pool, bus)).register()

    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-handshake")
    # NOTE: NO active assignment yet — handshake should still complete,
    # creating only the account_link. (Assignment is a separate concern.)
    token = await LinkingService(db_pool).generate(
        boss_user["id"], "zalo", bot_acc_id
    )

    sent: list[dict] = []
    captured: list[dict] = []
    bus.subscribe("outbound.send", lambda p: sent.append(p) or _noop())
    bus.subscribe("message.captured", lambda p: captured.append(p) or _noop())

    await bus.publish("inbound.normalized", {"message": _dm(
        bot_acc_id, "boss-uid-1", f"/start {token}", "handshake-1")})

    # Handshake should NOT publish message.captured (we swallow it).
    assert captured == []
    # We should have an outbound ack to the boss DM.
    assert len(sent) == 1
    assert sent[0]["chat_id"] == "boss-uid-1"
    assert "kết nối" in sent[0]["content"].lower() or "connected" in sent[0]["content"].lower() or "Đã" in sent[0]["content"]
    # And the link should now exist.
    async with db_pool.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='zalo' AND provider_user_id='boss-uid-1'"
        )
        tok = await c.fetchrow("SELECT * FROM linking_tokens WHERE token=$1", token)
    assert link is not None
    assert link["boss_id"] == boss_user["id"]
    assert tok is None  # consumed


@pytest.mark.asyncio
async def test_ingest_start_invalid_token_no_link(db_pool, boss_user):
    bus = InMemoryEventBus()
    InboundIngest(db_pool, bus, OutboundService(db_pool, bus)).register()
    bot_acc_id = await _seed_zalo_bot_account(db_pool, "lt-handshake-bad")

    sent: list[dict] = []
    captured: list[dict] = []
    bus.subscribe("outbound.send", lambda p: sent.append(p) or _noop())
    bus.subscribe("message.captured", lambda p: captured.append(p) or _noop())

    await bus.publish("inbound.normalized", {"message": _dm(
        bot_acc_id, "boss-uid-2", "/start completely-invalid-token", "handshake-bad")})

    assert sent == []  # no ack
    assert captured == []  # not captured either
    async with db_pool.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM account_links WHERE provider_user_id='boss-uid-2'"
        )
    assert n == 0


async def _noop():
    return None
