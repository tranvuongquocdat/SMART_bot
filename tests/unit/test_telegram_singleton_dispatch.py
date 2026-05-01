"""Tests for `telegram_singleton._messenger_for` provider dispatch.

When the legacy `telegram.send/edit_message` shim is called for a chat
whose conversation provider is "zalo", it must route to the Zalo
messenger registered in `channels.registry` instead of Telegram.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.db  # noqa: F401
from src.channels import registry
from src.channels import telegram_singleton


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.clear()
    yield
    registry.clear()


async def test_messenger_for_routes_to_zalo_when_provider_matches():
    zalo_m = MagicMock()
    zalo_m.send_message = AsyncMock()
    registry.register("zalo", zalo_m)

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=("zalo", "EXT")):
        chosen = await telegram_singleton._messenger_for("INT-CHAT")

    assert chosen is zalo_m


async def test_messenger_for_falls_back_to_telegram_when_provider_telegram():
    telegram_m = MagicMock()
    fake_get_messenger = MagicMock(return_value=telegram_m)

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=("telegram", "12345")), \
         patch.object(telegram_singleton, "get_messenger", fake_get_messenger):
        chosen = await telegram_singleton._messenger_for("INT-CHAT")

    assert chosen is telegram_m


async def test_messenger_for_falls_back_when_conversation_unknown():
    telegram_m = MagicMock()
    fake_get_messenger = MagicMock(return_value=telegram_m)

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=None), \
         patch.object(telegram_singleton, "get_messenger", fake_get_messenger):
        chosen = await telegram_singleton._messenger_for("INT-CHAT")

    assert chosen is telegram_m


async def test_messenger_for_falls_back_when_provider_unregistered():
    """If conversation says 'zalo' but no zalo messenger is registered,
    we fall through to telegram (and the send will likely fail loudly)."""
    telegram_m = MagicMock()
    fake_get_messenger = MagicMock(return_value=telegram_m)

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=("zalo", "EXT")), \
         patch.object(telegram_singleton, "get_messenger", fake_get_messenger):
        chosen = await telegram_singleton._messenger_for("INT-CHAT")

    assert chosen is telegram_m


async def test_edit_message_falls_back_to_send_on_unsupported():
    """Zalo doesn't support edit; the legacy shim should degrade to send_message."""
    from src.channels.base import UnsupportedOperation, OutgoingMessage

    zalo_m = MagicMock()
    zalo_m.edit_message = AsyncMock(side_effect=UnsupportedOperation("zalo: edit_message"))
    zalo_m.send_message = AsyncMock(return_value=OutgoingMessage(message_id="X"))
    registry.register("zalo", zalo_m)

    with patch("src.db.lookup_external_for_conversation",
               new_callable=AsyncMock,
               return_value=("zalo", "EXT")):
        await telegram_singleton.edit_message("uuid-chat-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 1, "new")

    zalo_m.edit_message.assert_awaited_once()
    zalo_m.send_message.assert_awaited_once()
