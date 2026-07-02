"""Consent notice (PDPL): 1 tin thông báo ghi nhận khi bot bắt đầu capture nhóm.

Spec 2026-07-02-zalo-automation §5: gửi đúng 1 lần mỗi (provider, chat_id) —
nhiều tin liên tiếp / boss thứ hai track sau đều KHÔNG gửi lại; kênh 'web'
(sandbox nội bộ của boss) không gửi.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.events.bus import InMemoryEventBus


class _CaptureOutbound:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, **kw):
        self.sent.append(kw)
        return 1


async def _bot_acc(pool, provider="zalo"):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO bot_accounts (provider, provider_user_id, account_kind, ownership) "
            "VALUES ($1, $2, 'personal', 'platform') RETURNING id",
            provider, f"consent-bot-{provider}",
        )


async def _boss_with_link(pool, email, provider, uid, bot_acc_id):
    async with pool.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1, 'Sếp Minh', 'boss') RETURNING id",
            email,
        )
        await c.execute(
            "INSERT INTO account_links (boss_id, provider, provider_user_id) VALUES ($1,$2,$3)",
            boss, provider, uid,
        )
        await c.execute(
            "INSERT INTO bot_account_assignments "
            "(boss_id, provider, bot_account_id, assignment_kind, status) "
            "VALUES ($1,$2,$3,'boss_owned','active')",
            boss, provider, bot_acc_id,
        )
    return boss


def _msg(**kw):
    base = dict(
        bot_account_id=0, provider="zalo", chat_id="g-consent", chat_type="group",
        provider_msg_id="m1", sender_provider_id="U_BOSS", sender_name="Boss",
        text="chào team", mentions_bot=False, reply_to_provider_msg_id=None,
        media_kind="text", media_url=None, ts=datetime.now(tz=timezone.utc),
    )
    base.update(kw)
    return InboundMessage(**base)


@pytest.mark.asyncio
async def test_consent_sent_once_on_first_capture(clean_db):
    acc = await _bot_acc(clean_db)
    boss = await _boss_with_link(clean_db, "c1@x.test", "zalo", "U_BOSS", acc)
    bus = InMemoryEventBus()
    outbound = _CaptureOutbound()
    InboundIngest(clean_db, bus, outbound_service=outbound).register()

    # boss nói lần đầu → track + consent 1 tin vào đúng nhóm
    await bus.publish("inbound.normalized", {"message": _msg(bot_account_id=acc)})
    await asyncio.sleep(0)
    consents = [s for s in outbound.sent if "Tin nhắn trong nhóm sẽ được ghi nhận" in s["content"]]
    assert len(consents) == 1
    assert consents[0]["chat_id"] == "g-consent"
    assert consents[0]["provider"] == "zalo"
    assert consents[0]["boss_id"] == boss
    assert consents[0]["trigger"] == "system"
    assert "Sếp Minh" in consents[0]["content"]

    # các tin sau (kể cả người khác nói) → KHÔNG gửi lại
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m2", sender_provider_id="U_OTHER", text="dạ")})
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m3", text="triển khai nhé")})
    await asyncio.sleep(0)
    consents = [s for s in outbound.sent if "Tin nhắn trong nhóm sẽ được ghi nhận" in s["content"]]
    assert len(consents) == 1

    async with clean_db.acquire() as c:
        notified = await c.fetchval(
            "SELECT consent_notified_at FROM group_notes WHERE provider='zalo' AND chat_id='g-consent'")
    assert notified is not None


@pytest.mark.asyncio
async def test_second_boss_same_group_does_not_resend(clean_db):
    acc = await _bot_acc(clean_db)
    await _boss_with_link(clean_db, "c2a@x.test", "zalo", "U_BOSS", acc)
    bus = InMemoryEventBus()
    outbound = _CaptureOutbound()
    InboundIngest(clean_db, bus, outbound_service=outbound).register()

    await bus.publish("inbound.normalized", {"message": _msg(bot_account_id=acc)})
    await asyncio.sleep(0)
    assert len(outbound.sent) == 1

    # boss thứ hai (chung acc) track cùng nhóm SAU đó → group_notes row mới
    # nhưng nhóm đã được thông báo → không gửi lại
    await _boss_with_link(clean_db, "c2b@x.test", "zalo", "U_BOSS2", acc)
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m9", sender_provider_id="U_BOSS2")})
    await asyncio.sleep(0)
    consents = [s for s in outbound.sent if "Tin nhắn trong nhóm sẽ được ghi nhận" in s["content"]]
    assert len(consents) == 1


@pytest.mark.asyncio
async def test_web_provider_sends_no_consent(clean_db):
    acc = await _bot_acc(clean_db, provider="web")
    await _boss_with_link(clean_db, "c3@x.test", "web", "U_BOSS", acc)
    bus = InMemoryEventBus()
    outbound = _CaptureOutbound()
    InboundIngest(clean_db, bus, outbound_service=outbound).register()

    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider="web")})
    await asyncio.sleep(0)
    assert outbound.sent == []
