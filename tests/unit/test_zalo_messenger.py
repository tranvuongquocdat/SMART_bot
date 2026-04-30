"""Tests for ZaloMessenger — _normalize and send_message dispatch.

Bridge is mocked via AsyncMock; db helpers are patched per-test so we don't
need a real SQLite. The protocol surface (channel name, capabilities,
Messenger Protocol satisfaction) is verified once.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.db  # noqa: F401  — register submodule for patch("src.db.*") resolution
from src.channels.base import IncomingMessage, Messenger, OutgoingMessage
from src.channels.zalo import ZaloMessenger


def _bridge_event(**overrides) -> dict:
    base = {
        "thread_id": "EXT-THREAD-1",
        "thread_type": "dm",
        "sender_uid": "EXT-USER-1",
        "sender_name": "Alice",
        "msg_id": "M-1",
        "ts_ms": 1_700_000_000_000,
        "text": "hello",
        "content_type": "text",
        "attachments": [],
        "mentions": [],
        "is_mentioned": False,
        "is_forwarded": False,
        "reply_to": None,
        "group_name": "",
    }
    base.update(overrides)
    return base


def test_zalo_messenger_satisfies_messenger_protocol():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    assert isinstance(m, Messenger)
    assert m.channel == "zalo"
    assert m.capabilities.supports_groups is True
    assert m.capabilities.supports_markdown is False


async def test_normalize_dm_text_message():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    ev = _bridge_event()

    with patch("src.db.resolve_or_create_conversation",
               new_callable=AsyncMock,
               return_value="INT-CHAT-UUID") as conv_mock, \
         patch("src.db.resolve_or_create_person",
               new_callable=AsyncMock,
               return_value="INT-USER-UUID") as person_mock:
        incoming = await m._normalize(ev)

    assert isinstance(incoming, IncomingMessage)
    assert incoming.channel == "zalo"
    assert incoming.chat_id == "INT-CHAT-UUID"
    assert incoming.chat_type == "dm"
    assert incoming.sender_id == "INT-USER-UUID"
    assert incoming.sender_name == "Alice"
    assert incoming.text == "hello"
    assert incoming.message_id == "M-1"
    assert incoming.timestamp == 1_700_000_000          # ms → s
    assert incoming.is_mentioned is False
    assert incoming.is_forwarded is False
    conv_mock.assert_awaited_once_with("zalo", "EXT-THREAD-1", "dm", "")
    person_mock.assert_awaited_once_with("zalo", "EXT-USER-1", "Alice", "")


async def test_normalize_group_with_mention_and_reply():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    ev = _bridge_event(
        thread_type="group",
        group_name="Team Chat",
        is_mentioned=True,
        mentions=[{"uid": "U2", "pos": 0, "len": 3}],
        reply_to={"msg_id": "PARENT", "sender_uid": "U3"},
    )

    with patch("src.db.resolve_or_create_conversation",
               new_callable=AsyncMock,
               return_value="INT-CHAT"), \
         patch("src.db.resolve_or_create_person",
               new_callable=AsyncMock,
               side_effect=lambda provider, ext, *a, **k: f"INT-{ext}"):
        incoming = await m._normalize(ev)

    assert incoming.chat_type == "group"
    assert incoming.group_name == "Team Chat"
    assert incoming.is_mentioned is True
    assert incoming.reply_to_message_id == "PARENT"
    assert incoming.reply_to_sender_id == "INT-U3"
    assert incoming.mentions == [{"id": "INT-U2", "name": "", "username": ""}]


async def test_normalize_photo_attachment():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    ev = _bridge_event(
        text="",
        content_type="image",
        attachments=[{"kind": "image", "href": "https://cdn.zalo/x.jpg"}],
    )

    with patch("src.db.resolve_or_create_conversation",
               new_callable=AsyncMock, return_value="C"), \
         patch("src.db.resolve_or_create_person",
               new_callable=AsyncMock, return_value="P"):
        incoming = await m._normalize(ev)

    assert len(incoming.attachments) == 1
    assert incoming.attachments[0].kind == "image"
    assert incoming.attachments[0].url == "https://cdn.zalo/x.jpg"


async def test_send_message_routes_dm_via_bridge():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    bridge = MagicMock()
    bridge.call = AsyncMock(return_value={"msg_id": "OUT-1"})
    m._bridge = bridge

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=("zalo", "EXT-THREAD-9")), \
         patch("src.db.get_conversation_kind",
               new_callable=AsyncMock, return_value="dm"), \
         patch("src.db.save_message", new_callable=AsyncMock) as save:
        out = await m.send_message("INT-CHAT", "hi there")

    assert isinstance(out, OutgoingMessage)
    assert out.message_id == "OUT-1"
    bridge.call.assert_awaited_once_with(
        "send",
        {"thread_id": "EXT-THREAD-9", "thread_type": "dm", "text": "hi there"},
    )
    save.assert_awaited_once_with("INT-CHAT", "assistant", "hi there")


async def test_send_message_uses_group_thread_type():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    bridge = MagicMock()
    bridge.call = AsyncMock(return_value={"msg_id": "G"})
    m._bridge = bridge

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock, return_value=("zalo", "G123")), \
         patch("src.db.get_conversation_kind",
               new_callable=AsyncMock, return_value="group"), \
         patch("src.db.save_message", new_callable=AsyncMock):
        await m.send_message("INT-CHAT", "team")

    assert bridge.call.await_args.args[1]["thread_type"] == "group"


async def test_send_message_skips_when_provider_not_zalo():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    bridge = MagicMock()
    bridge.call = AsyncMock()
    m._bridge = bridge

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock, return_value=("telegram", "12345")):
        out = await m.send_message("INT-CHAT", "x")

    assert out.message_id == ""
    bridge.call.assert_not_awaited()


async def test_send_message_no_bridge_returns_empty():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    out = await m.send_message("INT-CHAT", "x")
    assert out.message_id == ""


async def test_handle_event_dispatches_message_to_handler():
    m = ZaloMessenger("node", "/x/bridge.js", "/x/s.json")
    received: list = []

    async def handler(incoming):
        received.append(incoming)

    m._on_message = handler

    with patch("src.db.resolve_or_create_conversation",
               new_callable=AsyncMock, return_value="C"), \
         patch("src.db.resolve_or_create_person",
               new_callable=AsyncMock, return_value="P"):
        await m._handle_event("message", _bridge_event())
        # handler is scheduled via create_task — yield once.
        import asyncio
        await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].text == "hello"
