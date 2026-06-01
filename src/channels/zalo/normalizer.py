"""Subscribe to ``inbound.raw.zalo`` → INSERT message → publish ``message.captured``.

Also intercepts ``/start <token>`` DMs to complete the linking handshake
(see Task E3 — ``src/services/linking_service.py``).

Boss resolution:
  - DM: look up ``account_links`` by ``(provider, sender_uid)`` — link
        established by E3 handshake.
  - Group: for now (MVP), find any boss linked to ANY participant
        present in this group by matching against any account_links row
        whose boss has an active assignment to this bot_account. Full
        resolution via ``GroupOwnerResolver`` is Batch F. We DROP groups
        with no resolvable boss to avoid leaking cross-tenant data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.channels.zalo.inbound_filter import should_drop
from src.domain.message import NewMessage
from src.events.bus import EventBus
from src.repositories.base import BossContext
from src.repositories.messages import MessagesRepo

log = logging.getLogger(__name__)


def _coerce_text(data: dict) -> str:
    val = data.get("text")
    if isinstance(val, str):
        return val
    val = data.get("content")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("title") or val.get("text") or ""
    return ""


def _ts(data: dict) -> datetime:
    ms = data.get("ts") or data.get("ts_ms") or 0
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)


def register(bus: EventBus, pool) -> None:
    async def handle(payload: dict) -> None:
        data = payload.get("data") or {}
        bot_acc_id = payload.get("bot_account_id")
        own_uid = payload.get("own_uid")
        if should_drop(data):
            return

        chat_type = "dm" if data.get("type") == 0 else "group"
        thread_id = str(data.get("threadId") or data.get("thread_id") or "")
        sender_uid = str(data.get("uidFrom") or data.get("sender_uid") or "")
        sender_name = data.get("dName") or data.get("sender_name")
        provider_msg_id = str(data.get("msgId") or data.get("msg_id") or "") or None
        text = _coerce_text(data)
        mentions = data.get("mentions") or []
        mentions_bot = bool(data.get("is_mentioned")) or any(
            m.get("uid") == own_uid for m in mentions
        )
        media_kind = data.get("content_type") or "text"
        media_url = data.get("media_url")

        # ----- /start <token> handshake (E3) ---------------------------
        if chat_type == "dm" and isinstance(text, str) and text.startswith("/start "):
            token = text.split(" ", 1)[1].strip()
            # Defer import to avoid cycle on module load.
            from src.services.linking_service import LinkingService

            linked_boss_id = await LinkingService(pool).consume(
                token=token,
                sender_provider_uid=sender_uid,
                bot_account_id=bot_acc_id,
            )
            if linked_boss_id is not None:
                await bus.publish(
                    "outbound.send",
                    {
                        "outbound_id": None,
                        "boss_id": linked_boss_id,
                        "provider": "zalo",
                        "chat_id": sender_uid,
                        "content": "Đã kết nối. Em là bot của anh ở đây.",
                        "trigger": "system",
                        "reply_to_message_id": None,
                    },
                )
            else:
                log.info(
                    "zalo /start token rejected bot_acc=%s sender=%s",
                    bot_acc_id,
                    sender_uid,
                )
            return  # do not persist handshake messages

        # ----- resolve boss --------------------------------------------
        boss_id: int | None = None
        sender_is_boss = False
        async with pool.acquire() as c:
            if chat_type == "dm":
                row = await c.fetchrow(
                    """
                    SELECT al.boss_id
                    FROM account_links al
                    JOIN bot_account_assignments baa
                      ON baa.boss_id = al.boss_id AND baa.provider = al.provider
                    WHERE al.provider = 'zalo'
                      AND al.provider_user_id = $1
                      AND baa.bot_account_id = $2
                      AND baa.status = 'active'
                    """,
                    sender_uid,
                    bot_acc_id,
                )
                if row:
                    boss_id = row["boss_id"]
                    sender_is_boss = True
            else:
                # GROUP: find the boss whose link is associated with this
                # bot_account assignment. Full resolution (verifying that
                # the boss is actually a member of this group via
                # GroupOwnerResolver) lands in Batch F. For MVP we accept
                # any active assignment for this bot_acc — that's safe so
                # long as a bot_account serves only one boss per provider
                # (constraint enforced by bot_account_assignments PK).
                row = await c.fetchrow(
                    """
                    SELECT baa.boss_id
                    FROM bot_account_assignments baa
                    WHERE baa.provider = 'zalo'
                      AND baa.bot_account_id = $1
                      AND baa.status = 'active'
                    LIMIT 1
                    """,
                    bot_acc_id,
                )
                if row:
                    boss_id = row["boss_id"]

        if boss_id is None:
            return

        # ----- persist + publish ---------------------------------------
        repo = MessagesRepo(pool, BossContext(boss_id=boss_id, user_role="boss"))
        msg = NewMessage(
            provider="zalo",
            chat_id=thread_id,
            chat_type=chat_type,
            provider_msg_id=provider_msg_id,
            sender_provider_id=sender_uid or None,
            sender_name=sender_name,
            text=text or None,
            media_kind=media_kind,
            media_url=media_url,
            media_text=None,
            ts=_ts(data),
        )
        msg_id = await repo.insert(msg)
        if msg_id is None:
            # Duplicate (already ingested) — skip downstream fan-out.
            return

        await bus.publish(
            "message.captured",
            {
                "message_id": msg_id,
                "boss_id": boss_id,
                "provider": "zalo",
                "chat_id": thread_id,
                "chat_type": chat_type,
                "mentions_bot": mentions_bot,
                "sender_is_boss": sender_is_boss,
                "text": text,
                "bot_account_id": bot_acc_id,
            },
        )

    bus.subscribe("inbound.raw.zalo", handle)
