"""inbound.raw.web → MessagesRepo.insert → publish message.captured.

Schema payload (do routes.py publish):
  {
    web_user_id: str,        # sender
    chat_id: str,            # "dm:<uid>" or "<group_id>"
    chat_type: 'dm'|'group',
    text: str,
    mention_bot: bool,
    provider_msg_id: str,
    sender_name: str,
  }

Boss resolution:
  - DM: account_links lookup theo provider='web', provider_user_id=sender
  - Group: any boss đang là member của group (via web_users.is_boss=true
    JOIN web_group_members). MVP: lấy boss đầu tiên gặp.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.domain.message import NewMessage
from src.events.bus import EventBus
from src.repositories.base import BossContext
from src.repositories.messages import MessagesRepo

log = logging.getLogger(__name__)


def register(bus: EventBus, pool) -> None:
    async def handle(payload: dict) -> None:
        sender_uid = payload["web_user_id"]
        chat_id = payload["chat_id"]
        chat_type = payload["chat_type"]
        text = payload.get("text") or ""
        provider_msg_id = payload.get("provider_msg_id")
        sender_name = payload.get("sender_name")
        mention_bot = bool(payload.get("mention_bot"))

        boss_id: int | None = None
        sender_is_boss = False
        async with pool.acquire() as c:
            if chat_type == "dm":
                row = await c.fetchrow(
                    """
                    SELECT boss_id FROM account_links
                    WHERE provider='web' AND provider_user_id=$1
                    """,
                    sender_uid,
                )
                if row:
                    boss_id = row["boss_id"]
                    sender_is_boss = True
            else:
                row = await c.fetchrow(
                    """
                    SELECT wu.boss_user_id
                    FROM web_group_members m
                    JOIN web_users wu ON wu.id = m.web_user_id
                    WHERE m.group_id=$1
                      AND wu.is_boss=TRUE
                      AND wu.boss_user_id IS NOT NULL
                    LIMIT 1
                    """,
                    chat_id,
                )
                if row:
                    boss_id = row["boss_user_id"]
                # Check if sender themselves is the resolved boss
                if boss_id is not None:
                    own = await c.fetchrow(
                        """
                        SELECT boss_user_id FROM web_users
                        WHERE id=$1 AND is_boss=TRUE
                        """,
                        sender_uid,
                    )
                    if own and own["boss_user_id"] == boss_id:
                        sender_is_boss = True

        if boss_id is None:
            log.info(
                "web inbound dropped — no boss resolved (chat_id=%s sender=%s)",
                chat_id, sender_uid,
            )
            return

        repo = MessagesRepo(pool, BossContext(boss_id=boss_id, user_role="boss"))
        msg = NewMessage(
            provider="web",
            chat_id=chat_id,
            chat_type=chat_type,
            provider_msg_id=provider_msg_id,
            sender_provider_id=sender_uid,
            sender_name=sender_name,
            text=text or None,
            media_kind=payload.get("media_kind") or "text",
            media_url=payload.get("media_url"),
            media_text=None,
            ts=datetime.now(tz=timezone.utc),
        )
        msg_id = await repo.insert(msg)
        if msg_id is None:
            return  # dedup

        await bus.publish(
            "message.captured",
            {
                "message_id": msg_id,
                "boss_id": boss_id,
                "provider": "web",
                "chat_id": chat_id,
                "chat_type": chat_type,
                "mentions_bot": mention_bot,
                "sender_is_boss": sender_is_boss,
                "text": text,
                "bot_account_id": None,
            },
        )

    bus.subscribe("inbound.raw.web", handle)
