"""SSEHub — in-memory pub-sub cho web channel.

Mỗi browser tab attach() → nhận `SSEClient` có `queue` asyncio. Route
``/test/stream`` consume queue → flush ra `text/event-stream`.
Adapter / fanout subscriber publish() vào để push event đến các tab.

Queue có maxsize=100 — overflow → drop event (tab chậm, không block sender).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

QUEUE_MAX = 100


@dataclass
class SSEClient:
    web_user_id: str
    queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_MAX)
    )


class SSEHub:
    def __init__(self) -> None:
        self._clients: dict[str, list[SSEClient]] = defaultdict(list)

    def attach(self, web_user_id: str) -> SSEClient:
        client = SSEClient(web_user_id=web_user_id)
        self._clients[web_user_id].append(client)
        return client

    def detach(self, client: SSEClient) -> None:
        bucket = self._clients.get(client.web_user_id, [])
        if client in bucket:
            bucket.remove(client)

    async def publish(self, web_user_id: str, event: dict) -> None:
        for client in list(self._clients.get(web_user_id, [])):
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning(
                    "SSE queue full for web_user_id=%s; dropping event",
                    web_user_id,
                )

    async def broadcast(self, web_user_ids: list[str], event: dict) -> None:
        for uid in web_user_ids:
            await self.publish(uid, event)
