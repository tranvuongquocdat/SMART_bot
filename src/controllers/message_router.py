"""MessageRouter — single inbound boundary across all channels.

Inbound flow:
  External event
    → channel adapter (TelegramMessenger / future Zalo / webhook)
    → IncomingMessage (already carries internal UUIDs after Phase 2)
    → MessageRouter.handle(incoming)
       ├── tenant lifecycle gate (boss.status)
       └── delegate to secretary_agent (current LLM loop)

Phase 5b ships the boundary + the gate; the secretary loop body still lives
in `agent_pkg.secretary_agent.handle_message` and is called positionally.
Phase 6 will route per-channel capability checks here as well.
"""
from __future__ import annotations

import logging

from src import db
from src.channels.base import IncomingMessage
from src.container import AppContainer

logger = logging.getLogger("controllers.router")


class MessageRouter:
    def __init__(self, container: AppContainer) -> None:
        self._container = container

    async def handle(self, incoming: IncomingMessage) -> None:
        """Entry point for every inbound message from any channel."""
        from src.infrastructure.observability import request_context

        # Bind structured-logging context for the whole request — every log
        # record produced downstream gets boss_internal_id + internal_chat_id
        # + a fresh request_id automatically.
        with request_context(
            boss_internal_id=incoming.sender_id or None,
            internal_chat_id=incoming.chat_id,
        ):
            if await self._is_tenant_blocked(incoming):
                logger.info(
                    "[router] sender=%s suspended/cancelled — drop",
                    incoming.sender_id,
                )
                return

            # Phase 5b: delegate to the existing secretary loop body.
            # Phase 6 will route per-channel capability checks here too.
            from src.agent_pkg.secretary_agent import handle_message

            reply_to = None
            if incoming.reply_to_sender_id:
                reply_to = {
                    "id": incoming.reply_to_sender_id,
                    "name": "",
                    "username": "",
                }

            try:
                await handle_message(
                    incoming.text or "",
                    incoming.chat_id,
                    incoming.sender_id or None,
                    incoming.chat_type == "group",
                    incoming.is_mentioned,
                    incoming.group_name,
                    sender_name=incoming.sender_name,
                    mentions=incoming.mentions,
                    username_mentions=incoming.username_mentions,
                    reply_to=reply_to,
                    new_members=incoming.new_members,
                )
            except Exception:
                logger.exception("[router] handler raised for %s", incoming.chat_id)

    async def _is_tenant_blocked(self, incoming: IncomingMessage) -> bool:
        """Phase 3 schema added `bosses.status` (default 'active'). When the
        sender is a known boss with a non-active status, drop the message
        silently. Non-boss senders (members, unknown DMs) always pass — the
        downstream onboarding flow handles them."""
        sender_id = incoming.sender_id
        if not sender_id:
            return False
        boss = await db.get_boss(sender_id)
        if boss is None:
            return False
        status = (boss.get("status") or "active").lower()
        return status in {"suspended", "cancelled"}
