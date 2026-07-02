"""InboundIngest — wrapper định danh + lọc nhóm dùng chung cho MỌI kênh.

Mỗi adapter dịch wire-format -> InboundMessage rồi publish ``inbound.normalized``
({"message": InboundMessage}). Đây là subscriber DUY NHẤT cho topic đó. Không
kênh nào tự resolve boss hay tự publish ``message.captured``.

Luồng:
  - DM "/start <token>"  -> LinkingService.consume -> ack, KHÔNG persist.
  - DM thường            -> resolve boss qua account_links (scope theo assignment).
  - Group                -> boss-spoke: sếp nói -> ensure_tracked; chỉ capture nếu
                            nhóm đã track cho ít nhất một boss assign vào bot acc này.
  - Dedup + insert per-boss + publish ``message.captured`` (mỗi boss một event).
"""

from __future__ import annotations

import hashlib
import logging

from src.channels.base import InboundMessage
from src.channels.zalo.inbound_filter import should_drop_normalized
from src.domain.message import NewMessage
from src.events.bus import EventBus
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.messages import MessagesRepo

log = logging.getLogger(__name__)

# PDPL: thông báo ghi nhận khi bot bắt đầu capture một nhóm — gửi ĐÚNG 1 lần
# mỗi (provider, chat_id). Giọng thư ký, không icon, tiếng Việt mặc định.
CONSENT_NOTICE_VI = (
    "Xin chào cả nhóm. Em là thư ký ảo của {boss_name}, được thêm vào nhóm để "
    "ghi nhận và hỗ trợ công việc chung (việc được giao, deadline, nhắc lịch). "
    "Tin nhắn trong nhóm sẽ được ghi nhận cho mục đích này. Nếu nhóm không "
    "đồng ý, vui lòng mời em rời nhóm."
)


class InboundIngest:
    def __init__(self, pool, bus: EventBus, outbound_service=None):
        self.pool = pool
        self.bus = bus
        self.outbound_service = outbound_service

    def register(self) -> None:
        self.bus.subscribe("inbound.normalized", self._handle)

    async def _handle(self, payload: dict) -> None:
        msg: InboundMessage = payload["message"]
        if should_drop_normalized(msg):
            return
        if msg.chat_type == "dm":
            await self._handle_dm(msg)
        else:
            await self._handle_group(msg)

    # ---- candidates / identity helpers -----------------------------------

    async def _candidates(self, bot_account_id) -> list[int]:
        if bot_account_id is None:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT boss_id FROM bot_account_assignments "
                "WHERE bot_account_id=$1 AND status='active'",
                bot_account_id,
            )
        return [r["boss_id"] for r in rows]

    async def _sender_boss(self, provider, sender_uid, candidates) -> int | None:
        if not sender_uid or not candidates:
            return None
        async with self.pool.acquire() as c:
            return await c.fetchval(
                "SELECT boss_id FROM account_links "
                "WHERE provider=$1 AND provider_user_id=$2 AND boss_id = ANY($3::int[])",
                provider, sender_uid, candidates,
            )

    # ---- DM ---------------------------------------------------------------

    async def _handle_dm(self, msg: InboundMessage) -> None:
        text = msg.text or ""
        if text.startswith("/start "):
            await self._handshake(msg, text.split(" ", 1)[1].strip())
            return
        candidates = await self._candidates(msg.bot_account_id)
        boss_id = await self._sender_boss(msg.provider, msg.sender_provider_id, candidates)
        if boss_id is None:
            return
        await self._persist_and_publish(msg, boss_id, sender_is_boss=True)

    async def _handshake(self, msg: InboundMessage, token: str) -> None:
        from src.services.linking_service import LinkingService

        boss_id = await LinkingService(self.pool).consume(
            token=token,
            sender_provider_uid=msg.sender_provider_id,
            bot_account_id=msg.bot_account_id,
        )
        if boss_id is not None and self.outbound_service is not None:
            await self.outbound_service.send(
                boss_id=boss_id, provider=msg.provider, chat_id=msg.chat_id,
                content="Đã kết nối. Em là bot của anh ở đây.", trigger="system",
            )
        else:
            log.info("handshake rejected provider=%s bot_acc=%s sender=%s",
                     msg.provider, msg.bot_account_id, msg.sender_provider_id)

    # ---- Group ------------------------------------------------------------

    async def _handle_group(self, msg: InboundMessage) -> None:
        candidates = await self._candidates(msg.bot_account_id)
        if not candidates:
            return
        sender_boss = await self._sender_boss(
            msg.provider, msg.sender_provider_id, candidates)
        if sender_boss is not None:
            await GroupNotesRepo(
                self.pool, BossContext(boss_id=sender_boss, user_role="boss")
            ).ensure_tracked(msg.provider, msg.chat_id, group_name=None)

        tracked = await GroupNotesRepo(
            self.pool, BossContext(boss_id=0, user_role="superadmin")
        ).bosses_tracking(msg.provider, msg.chat_id)
        tracked = [b for b in tracked if b in candidates]
        if not tracked:
            return
        await self._maybe_send_consent(msg)
        for boss_id in tracked:
            await self._persist_and_publish(
                msg, boss_id, sender_is_boss=(boss_id == sender_boss))

    async def _maybe_send_consent(self, msg: InboundMessage) -> None:
        """Tin thông báo ghi nhận (PDPL) — 1 lần/nhóm, mọi boss chung acc.

        Kênh 'web' bỏ qua: đó là sandbox nội bộ của chính boss, không có bên
        thứ ba cần được thông báo. Claim bằng UPDATE có điều kiện để không gửi
        trùng khi nhiều tin về cùng lúc / boss thứ hai track sau."""
        if msg.provider == "web" or self.outbound_service is None:
            return
        async with self.pool.acquire() as c:
            claimed = await c.fetch(
                """
                UPDATE group_notes SET consent_notified_at = NOW()
                WHERE provider=$1 AND chat_id=$2 AND consent_notified_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM group_notes
                    WHERE provider=$1 AND chat_id=$2
                      AND consent_notified_at IS NOT NULL)
                RETURNING boss_id
                """,
                msg.provider, msg.chat_id,
            )
            if not claimed:
                return
            boss_name = await c.fetchval(
                "SELECT name FROM users WHERE id=$1", claimed[0]["boss_id"])
        try:
            await self.outbound_service.send(
                boss_id=claimed[0]["boss_id"], provider=msg.provider,
                chat_id=msg.chat_id,
                content=CONSENT_NOTICE_VI.format(boss_name=boss_name or "sếp"),
                trigger="system",
            )
        except Exception:
            log.exception("consent notice send failed chat=%s", msg.chat_id)

    # ---- persist ----------------------------------------------------------

    def _dedup_id(self, msg: InboundMessage) -> str:
        if msg.provider_msg_id:
            return msg.provider_msg_id
        ts = int(msg.ts.timestamp()) if msg.ts else 0
        h = hashlib.sha1((msg.text or "").encode()).hexdigest()[:10]
        return f"syn:{msg.sender_provider_id or ''}:{ts}:{h}"

    async def _persist_and_publish(self, msg, boss_id: int, sender_is_boss: bool) -> None:
        repo = MessagesRepo(self.pool, BossContext(boss_id=boss_id, user_role="boss"))
        msg_id = await repo.insert(NewMessage(
            provider=msg.provider, chat_id=msg.chat_id, chat_type=msg.chat_type,
            provider_msg_id=self._dedup_id(msg),
            sender_provider_id=msg.sender_provider_id or None,
            sender_name=msg.sender_name, text=msg.text or None,
            media_kind=msg.media_kind or "text", media_url=msg.media_url,
            media_text=None, ts=msg.ts,
        ))
        if msg_id is None:
            return  # dedup
        await self.bus.publish("message.captured", {
            "message_id": msg_id, "boss_id": boss_id, "provider": msg.provider,
            "chat_id": msg.chat_id, "chat_type": msg.chat_type,
            "mentions_bot": bool(msg.mentions_bot), "sender_is_boss": sender_is_boss,
            "text": msg.text, "bot_account_id": msg.bot_account_id,
        })
