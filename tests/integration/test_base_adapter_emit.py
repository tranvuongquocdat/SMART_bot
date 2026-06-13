import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import BaseChannelAdapter, InboundMessage
from src.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_emit_inbound_publishes_normalized():
    bus = InMemoryEventBus()

    class A(BaseChannelAdapter):
        provider = "zalo"

    a = A(bus)
    seen: list[dict] = []
    bus.subscribe("inbound.normalized", lambda p: seen.append(p) or asyncio.sleep(0))

    msg = InboundMessage(
        bot_account_id=1, provider="zalo", chat_id="g", chat_type="group",
        provider_msg_id="m", sender_provider_id="u", sender_name="x", text="hi",
        mentions_bot=False, reply_to_provider_msg_id=None, media_kind="text",
        media_url=None, ts=datetime.now(tz=timezone.utc))
    await a._emit_inbound(msg)
    await asyncio.sleep(0)
    assert seen and seen[0]["message"] is msg
