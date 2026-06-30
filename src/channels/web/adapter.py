"""WebAdapter — implements ChannelAdapter cho channel web.

start_inbound / stop_inbound: no-op (web không có long-lived subprocess).
send_text: broadcast tới các SSE client của các thành viên chat đích.
list_members: query WebGroupsRepo cho group chat.
health_check: web bot account luôn alive khi app chạy.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo

log = logging.getLogger(__name__)


class WebAdapter:
    provider = "web"

    # Wired by channels.web.setup() after construction (HTTP routes reach these
    # via app.state); declared here so they're part of the adapter's typed surface.
    users_repo: WebUsersRepo
    outbound_service: Any
    pool: Any

    def __init__(
        self,
        bus: Any,
        sse_hub: SSEHub,
        groups_repo: WebGroupsRepo | None,
    ) -> None:
        self.bus = bus
        self.sse_hub = sse_hub
        self.groups_repo = groups_repo

    async def start_inbound(self, bot_acc) -> None:
        return  # web inbound đến qua HTTP, không cần long-lived process

    async def stop_inbound(self, bot_acc) -> None:
        return

    async def send_text(
        self, bot_acc, chat_id: str, text: str, thread_kind: str
    ) -> str:
        recipients = await self._recipients_of(chat_id)
        event = {
            "kind": "message",
            "chat_id": chat_id,
            "msg_id": f"o-{uuid.uuid4().hex[:8]}",
            "sender_kind": "bot",
            "sender_id": "web-bot-1",
            "sender_name": "Bot",
            "text": text,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        await self.sse_hub.broadcast(recipients, event)
        return event["msg_id"]

    async def list_members(self, bot_acc, group_id: str) -> list[str]:
        if self.groups_repo is None:
            return []
        return await self.groups_repo.list_members(group_id)

    def classify_thread_kind(self, chat_id: str) -> str:
        if chat_id.startswith("dm:"):
            return "user"
        return "group"

    def normalize_text(self, text: str) -> str:
        # Web UI renders markdown — không cần strip.
        return text

    async def health_check(self) -> dict[int, bool]:
        # Web không có subprocess — bot_account luôn "alive" while app up.
        return {}

    async def _recipients_of(self, chat_id: str) -> list[str]:
        if chat_id.startswith("dm:"):
            return [chat_id[3:]]
        if self.groups_repo is None:
            return []
        return await self.groups_repo.list_members(chat_id)
