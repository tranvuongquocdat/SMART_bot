import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.events.bus import InMemoryEventBus


async def _boss_with_link(pool, email, provider, uid, bot_acc_id):
    async with pool.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1,$2,'boss') RETURNING id",
            email, email,
        )
        await c.execute(
            "INSERT INTO account_links (boss_id, provider, provider_user_id) VALUES ($1,$2,$3)",
            boss, provider, uid,
        )
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1,$2,$3,'boss_owned','active')
            """,
            boss, provider, bot_acc_id,
        )
    return boss


async def _bot_acc(pool, owner_boss_id=None):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts (provider, provider_user_id, account_kind, ownership, owner_boss_id)
            VALUES ('zalo', $1, 'personal', $2, $3) RETURNING id
            """,
            f"botuid-{owner_boss_id}", "boss_owned" if owner_boss_id else "platform", owner_boss_id,
        )


def _msg(**kw):
    base = dict(
        bot_account_id=0, provider="zalo", chat_id="g1", chat_type="group",
        provider_msg_id="m1", sender_provider_id="U_BOSS", sender_name="Boss",
        text="hello", mentions_bot=False, reply_to_provider_msg_id=None,
        media_kind="text", media_url=None, ts=datetime.now(tz=timezone.utc),
    )
    base.update(kw)
    return InboundMessage(**base)


@pytest.mark.asyncio
async def test_group_dropped_until_boss_speaks_then_captures(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    boss = await _boss_with_link(clean_db, "gb@x.test", "zalo", "U_BOSS", acc)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    # 1) Người lạ nói trước khi boss nói -> drop
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_OTHER", provider_msg_id="m0", text="spam?")})
    await asyncio.sleep(0)
    assert captured == []

    # 2) Boss nói -> track + captured (sender_is_boss True)
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_BOSS", provider_msg_id="m1", text="hi team")})
    await asyncio.sleep(0)
    assert len(captured) == 1
    assert captured[0]["boss_id"] == boss
    assert captured[0]["sender_is_boss"] is True

    # 3) Người lạ nói SAU khi đã track -> captured (sender_is_boss False)
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_OTHER", provider_msg_id="m2", text="fyi")})
    await asyncio.sleep(0)
    assert len(captured) == 2
    assert captured[1]["sender_is_boss"] is False


@pytest.mark.asyncio
async def test_dm_from_boss_captured_stranger_dropped(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    boss = await _boss_with_link(clean_db, "db@x.test", "zalo", "U_BOSS", acc)
    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_BOSS", sender_provider_id="U_BOSS",
        provider_msg_id="d1", text="nhắc tôi 3h")})
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_X", sender_provider_id="U_X",
        provider_msg_id="d2", text="ai đó")})
    await asyncio.sleep(0)
    assert [c["sender_is_boss"] for c in captured] == [True]
    assert captured[0]["boss_id"] == boss


@pytest.mark.asyncio
async def test_start_handshake_links_and_does_not_persist(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    # boss tồn tại + assignment active, NHƯNG chưa có account_links
    async with clean_db.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ('hs@x.test','hs','boss') RETURNING id")
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id, assignment_kind, status)"
            " VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
    from src.services.linking_service import LinkingService
    token = await LinkingService(clean_db).generate(boss, "zalo", acc)

    sent: list[dict] = []

    class _OB:
        async def send(self, **kw):
            sent.append(kw)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus, outbound_service=_OB()).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_NEW", sender_provider_id="U_NEW",
        provider_msg_id="h1", text=f"/start {token}")})
    await asyncio.sleep(0)

    assert captured == []  # handshake không persist
    assert len(sent) == 1  # có ack
    async with clean_db.acquire() as c:
        link = await c.fetchval(
            "SELECT boss_id FROM account_links WHERE provider='zalo' AND provider_user_id='U_NEW'")
    assert link == boss
