"""Inbound fanout — khi user X gửi message trong group g-001, các tab
khác (user Y, Z) phải thấy realtime. Subscribe vào ``message.captured``
provider='web' và broadcast event "message" qua SSEHub tới các member.

Sender's own tab cũng nhận event (đơn giản hơn dedup); frontend hiển
thị uniform — không có "optimistic update" mismatch.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo
from src.events.bus import EventBus


def register(
    bus: EventBus, sse_hub: SSEHub, groups_repo: WebGroupsRepo, pool
) -> None:
    async def handle(payload: dict) -> None:
        if payload.get("provider") != "web":
            return
        chat_id = payload["chat_id"]
        if chat_id.startswith("dm:"):
            recipients = [chat_id[3:]]
        else:
            recipients = await groups_repo.list_members(chat_id)

        # Pull sender info từ DB (normalizer đã insert)
        async with pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT m.sender_provider_id, m.sender_name, m.text, m.ts
                FROM messages m WHERE m.id=$1
                """,
                payload["message_id"],
            )
        if row is None:
            return

        event = {
            "kind": "message",
            "chat_id": chat_id,
            "msg_id": str(payload["message_id"]),
            "sender_kind": "user",
            "sender_id": row["sender_provider_id"],
            "sender_name": row["sender_name"],
            "text": row["text"] or "",
            "ts": (row["ts"] or datetime.now(tz=timezone.utc)).isoformat(),
        }
        await sse_hub.broadcast(recipients, event)

    bus.subscribe("message.captured", handle)
