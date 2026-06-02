import asyncio

import pytest

from src.channels.web import normalizer as web_normalizer
from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo
from src.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_normalizer_dm_inserts_message_and_publishes_captured(clean_db):
    users = WebUsersRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)

    bus = InMemoryEventBus()
    web_normalizer.register(bus, clean_db)

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": boss_uid,
            "chat_id": f"dm:{boss_uid}",
            "chat_type": "dm",
            "text": "hi bot",
            "mention_bot": False,
            "provider_msg_id": "msg-1",
            "sender_name": "Boss",
        },
    )
    await asyncio.sleep(0)

    assert len(captured) == 1
    ev = captured[0]
    assert ev["provider"] == "web"
    assert ev["boss_id"] == boss_id
    assert ev["chat_type"] == "dm"
    assert ev["sender_is_boss"] is True
    assert ev["text"] == "hi bot"


@pytest.mark.asyncio
async def test_normalizer_group_resolves_boss_via_member(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)
    u2 = await users.create(name="UserX", is_boss=False)
    gid = await groups.create(name="team", member_ids=[boss_uid, u2])

    bus = InMemoryEventBus()
    web_normalizer.register(bus, clean_db)

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": u2,
            "chat_id": gid,
            "chat_type": "group",
            "text": "fyi",
            "mention_bot": True,
            "provider_msg_id": "g-msg-1",
            "sender_name": "UserX",
        },
    )
    await asyncio.sleep(0)

    assert len(captured) == 1
    assert captured[0]["chat_type"] == "group"
    assert captured[0]["boss_id"] == boss_id
    assert captured[0]["mentions_bot"] is True
    assert captured[0]["sender_is_boss"] is False
