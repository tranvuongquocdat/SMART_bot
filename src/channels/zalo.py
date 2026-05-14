"""ZaloMessenger — `Messenger` impl over the Node zca-js bridge.

Demo scope: one Zalo account, session.json on disk (path from Settings).
Multi-account, encryption, rate-limiting, circuit breaker, daily refresh —
deferred to Phase 6b proper.
"""
from __future__ import annotations

import asyncio
import logging

from src.channels.base import (
    Attachment,
    BaseMessenger,
    IncomingHandler,
    IncomingMessage,
    MessengerCapabilities,
    OutgoingMessage,
)
from src.channels.zalo_bridge.inbound_filter import ZaloInboundFilter
from src.channels.zalo_bridge.markdown_strip import markdown_to_plain
from src.channels.zalo_bridge.process import ZaloBridgeProcess
from src.channels.zalo_bridge.rate_limiter import ZaloRateLimiter

logger = logging.getLogger("channels.zalo")


class ZaloMessenger(BaseMessenger):
    channel = "zalo"
    capabilities = MessengerCapabilities(
        supports_groups=True,
        supports_group_admin=False,
        supports_invite_links=False,
        supports_edit=False,
        supports_delete=False,
        supports_typing=False,
        supports_photos=True,
        supports_files=True,
        supports_voice=True,
        supports_markdown=False,
    )

    def __init__(
        self,
        node_path: str,
        bridge_js_path: str,
        session_path: str,
        rate_limiter: ZaloRateLimiter | None = None,
        inbound_filter: ZaloInboundFilter | None = None,
    ) -> None:
        self._node_path = node_path
        self._bridge_js = bridge_js_path
        self._session = session_path
        self._bridge: ZaloBridgeProcess | None = None
        self._on_message: IncomingHandler | None = None
        self._own_id: str = ""
        self._rate_limiter = rate_limiter or ZaloRateLimiter()
        self._filter = inbound_filter

    # --- Lifecycle ---------------------------------------------------------

    async def start(self, on_message: IncomingHandler) -> None:
        self._on_message = on_message
        self._bridge = ZaloBridgeProcess(
            self._node_path, self._bridge_js, self._session,
            on_event=self._handle_event,
        )
        await self._bridge.start()
        self._own_id = self._bridge.own_id
        logger.info("Zalo online as uid=%s", self._own_id)

    async def stop(self) -> None:
        if self._bridge is not None:
            await self._bridge.close()
            self._bridge = None

    # --- Inbound -----------------------------------------------------------

    async def _handle_event(self, event: str, data: dict) -> None:
        if event == "message":
            if self._filter is not None:
                try:
                    if not await self._filter.should_forward(data):
                        logger.debug(
                            "zalo: dropped (filter) thread=%s sender=%s",
                            data.get("thread_id"), data.get("sender_uid"),
                        )
                        return
                except Exception:
                    logger.exception("zalo: filter raised; dropping to be safe")
                    return
            try:
                incoming = await self._normalize(data)
            except Exception:
                logger.exception("zalo: normalize failed: %s", data)
                return
            if self._on_message is None:
                return
            logger.info(
                "[chat:%s type:%s sender:%s] Received: %s",
                incoming.chat_id, incoming.chat_type, incoming.sender_id,
                (incoming.text or "")[:100],
            )
            asyncio.create_task(self._on_message(incoming))
        elif event == "disconnected":
            logger.warning("zalo bridge disconnected: %s", data)
        else:
            logger.debug("zalo bridge event=%s data=%s", event, data)

    async def _normalize(self, ev: dict) -> IncomingMessage:
        from src import db

        thread_type = "group" if ev.get("thread_type") == "group" else "dm"
        external_thread = str(ev.get("thread_id", ""))
        sender_uid = str(ev.get("sender_uid", ""))
        sender_name = ev.get("sender_name", "") or ""
        group_name = ev.get("group_name", "") or ""

        internal_chat_id = await db.resolve_or_create_conversation(
            "zalo", external_thread, thread_type, group_name,
        )
        internal_sender_id = ""
        if sender_uid:
            internal_sender_id = await db.resolve_or_create_person(
                "zalo", sender_uid, sender_name, "",
            )

        reply_to_message_id = None
        reply_to_sender_id = None
        rt = ev.get("reply_to") or None
        if rt:
            reply_to_message_id = str(rt.get("msg_id") or "") or None
            sup = str(rt.get("sender_uid") or "")
            if sup:
                reply_to_sender_id = await db.resolve_or_create_person(
                    "zalo", sup, "", "",
                )

        attachments: list[Attachment] = []
        for a in (ev.get("attachments") or []):
            kind = a.get("kind", "file")
            # Zalo "url card" / link preview is wrapped by the bridge as a
            # fake attachment with kind in {link, text} and filename = raw
            # message body. Drop it — the URL is already in ev["text"] and
            # the LLM will call fetch_url. Keeping it triggered the
            # `_looks_like_filename` heuristic and silently stashed the
            # message, so the bot never responded to YouTube/TikTok links.
            if kind in ("link", "text"):
                continue
            # Real file attachment but download failed (e.g. EACCES on the
            # inbound dir) — no usable file path, drop so the agent doesn't
            # mis-stash a textless message.
            if a.get("error"):
                continue
            attachments.append(Attachment(
                kind=kind,
                url=a.get("local_path", "") or "",
                mime_type=a.get("mime", ""),
                filename=a.get("filename", ""),
                size_bytes=int(a.get("size_bytes", 0) or 0),
            ))

        mentions: list[dict] = []
        for m in (ev.get("mentions") or []):
            uid = str(m.get("uid") or "")
            if not uid:
                continue
            internal = await db.resolve_or_create_person("zalo", uid, "", "")
            mentions.append({"id": internal, "name": "", "username": ""})

        return IncomingMessage(
            channel="zalo",
            chat_id=internal_chat_id,
            chat_type=thread_type,
            sender_id=internal_sender_id,
            sender_name=sender_name,
            text=ev.get("text", "") or "",
            attachments=attachments,
            is_mentioned=bool(ev.get("is_mentioned")),
            is_forwarded=bool(ev.get("is_forwarded")),
            reply_to_message_id=reply_to_message_id,
            reply_to_sender_id=reply_to_sender_id,
            message_id=str(ev.get("msg_id") or ""),
            timestamp=int((ev.get("ts_ms") or 0) // 1000),
            group_name=group_name,
            mentions=mentions,
            raw=ev,
        )

    # --- Outbound ----------------------------------------------------------

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        format: str = "markdown",
        save_history: bool = True,
        reply_to_message_id: str | None = None,
    ) -> OutgoingMessage:
        if self._bridge is None:
            logger.warning("zalo.send: bridge not running")
            return OutgoingMessage(message_id="", chat_id=chat_id)

        from src import db

        ext = await db.lookup_external_for_conversation(chat_id)
        if not ext:
            logger.warning("zalo.send: no conversation row for %s", chat_id)
            return OutgoingMessage(message_id="", chat_id=chat_id)
        provider, external_thread = ext
        if provider != "zalo":
            logger.warning(
                "zalo.send: chat %s belongs to provider=%s, not zalo",
                chat_id, provider,
            )
            return OutgoingMessage(message_id="", chat_id=chat_id)

        kind = await db.get_conversation_kind(chat_id)
        thread_type = "group" if kind == "group" else "dm"

        # Zalo doesn't render markdown — strip it so users don't see literal **, #, etc.
        plain = markdown_to_plain(text)

        await self._rate_limiter.acquire(external_thread)

        msg_id = ""
        try:
            res = await self._bridge.call("send", {
                "thread_id": external_thread,
                "thread_type": thread_type,
                "text": plain,
            })
            msg_id = str(res.get("msg_id") or "")
        except Exception:
            logger.exception("zalo.send failed for chat=%s", chat_id)

        if save_history and chat_id and plain:
            try:
                await db.save_message(chat_id, "assistant", plain)
            except Exception:
                logger.warning("zalo.send: save_message failed", exc_info=True)

        return OutgoingMessage(message_id=msg_id, chat_id=chat_id)

    # --- Identity ----------------------------------------------------------

    async def get_bot_id(self) -> str:
        return self._own_id
