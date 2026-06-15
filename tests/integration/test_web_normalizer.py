"""Web inbound qua InboundIngest (wrapper chung) — boss-spoke gating.

Web không còn normalizer riêng: route publish ``inbound.normalized`` và
InboundIngest resolve boss + lọc nhóm giống mọi kênh khác.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebUsersRepo
from src.events.bus import InMemoryEventBus


async def _web_bot_acc(pool):
    async with pool.acquire() as c:
        return await c.fetchval(
            "SELECT id FROM bot_accounts WHERE provider='web' AND status='active' LIMIT 1"
        )


def _wmsg(acc, **kw):
    base = dict(
        bot_account_id=acc, provider="web", chat_id="g1", chat_type="group",
        provider_msg_id="m1", sender_provider_id="u", sender_name="x", text="hi",
        mentions_bot=False, reply_to_provider_msg_id=None, media_kind="text",
        media_url=None, ts=datetime.now(tz=timezone.utc))
    base.update(kw)
    return InboundMessage(**base)


@pytest.mark.asyncio
async def test_web_dm_from_boss_captured(clean_db):
    users = WebUsersRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)
    acc = await _web_bot_acc(clean_db)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _wmsg(
        acc, chat_type="dm", chat_id=f"dm:{boss_uid}", sender_provider_id=boss_uid,
        provider_msg_id="d1", text="hi bot")})
    await asyncio.sleep(0)

    assert len(captured) == 1
    ev = captured[0]
    assert ev["provider"] == "web"
    assert ev["boss_id"] == boss_id
    assert ev["chat_type"] == "dm"
    assert ev["sender_is_boss"] is True
    assert ev["text"] == "hi bot"


@pytest.mark.asyncio
async def test_web_group_requires_boss_to_speak(clean_db):
    users = WebUsersRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)
    acc = await _web_bot_acc(clean_db)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    # người lạ nói trước -> drop
    await bus.publish("inbound.normalized", {"message": _wmsg(
        acc, chat_id="gw", sender_provider_id="stranger", provider_msg_id="w0")})
    await asyncio.sleep(0)
    assert captured == []

    # boss nói -> track + captured
    await bus.publish("inbound.normalized", {"message": _wmsg(
        acc, chat_id="gw", sender_provider_id=boss_uid, provider_msg_id="w1",
        mentions_bot=True)})
    await asyncio.sleep(0)
    assert len(captured) == 1
    assert captured[0]["boss_id"] == boss_id
    assert captured[0]["mentions_bot"] is True
    assert captured[0]["sender_is_boss"] is True
