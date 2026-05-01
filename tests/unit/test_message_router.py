"""Tests for MessageRouter — tenant gate behavior + delegation."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.channels.base import IncomingMessage
from src.controllers.message_router import MessageRouter


def _incoming(sender_id: str = "uuid-sender", text: str = "hi") -> IncomingMessage:
    return IncomingMessage(
        channel="telegram",
        chat_id="uuid-chat",
        chat_type="dm",
        sender_id=sender_id,
        sender_name="Tester",
        text=text,
        attachments=[],
        is_mentioned=False,
        is_forwarded=False,
        reply_to_message_id=None,
        reply_to_sender_id=None,
        message_id="42",
        timestamp=0,
        group_name="",
        mentions=[],
        username_mentions=[],
        new_members=[],
        raw={},
    )


@pytest.mark.asyncio
async def test_tenant_active_passes_through_to_secretary():
    container = MagicMock()
    router = MessageRouter(container)
    msg = _incoming()

    with patch("src.controllers.message_router.db.get_boss",
               new_callable=AsyncMock,
               return_value={"chat_id": "uuid-sender", "status": "active"}), \
         patch("src.agent.secretary_agent.handle_message",
               new_callable=AsyncMock) as mock_handle:
        await router.handle(msg)

    mock_handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_tenant_suspended_drops_silently():
    container = MagicMock()
    router = MessageRouter(container)
    msg = _incoming()

    with patch("src.controllers.message_router.db.get_boss",
               new_callable=AsyncMock,
               return_value={"chat_id": "uuid-sender", "status": "suspended"}), \
         patch("src.agent.secretary_agent.handle_message",
               new_callable=AsyncMock) as mock_handle:
        await router.handle(msg)

    mock_handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_cancelled_drops_silently():
    container = MagicMock()
    router = MessageRouter(container)
    msg = _incoming()

    with patch("src.controllers.message_router.db.get_boss",
               new_callable=AsyncMock,
               return_value={"chat_id": "uuid-sender", "status": "cancelled"}), \
         patch("src.agent.secretary_agent.handle_message",
               new_callable=AsyncMock) as mock_handle:
        await router.handle(msg)

    mock_handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_sender_passes_through():
    """Non-boss senders (member DMs, unknown new users for onboarding) always
    reach the secretary loop; onboarding state machine handles them downstream."""
    container = MagicMock()
    router = MessageRouter(container)
    msg = _incoming()

    with patch("src.controllers.message_router.db.get_boss",
               new_callable=AsyncMock,
               return_value=None), \
         patch("src.agent.secretary_agent.handle_message",
               new_callable=AsyncMock) as mock_handle:
        await router.handle(msg)

    mock_handle.assert_awaited_once()
