"""
TelegramMessenger — concrete `Messenger` for Telegram Bot API.

Wraps the previous `src.services.telegram` module into a class that satisfies
the channel Protocol. Group-admin ops remain as methods because Telegram
supports them natively.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time as _time
import unicodedata
from pathlib import Path

import httpx

from src.channels.base import (
    Attachment,
    BaseMessenger,
    IncomingHandler,
    IncomingMessage,
    MessengerCapabilities,
    OutgoingMessage,
)
from src.utils.text import full_name

logger = logging.getLogger("channels.telegram")

API = "https://api.telegram.org"

_INBOUND_ROOT = Path("data/inbound")


def _safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name or "file")
    name = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", name)
    if "." in name:
        base, ext = name.rsplit(".", 1)
        return f"{base[:80]}.{ext[:20]}"
    return name[:80]


async def _download_to_disk(
    http_client, bot_token: str, file_id: str,
    chat_id: str, msg_id: str, filename: str,
) -> str:
    """Telegram getFile + GET file. Returns local path or '' on failure."""
    try:
        r = await http_client.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
        )
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            return ""
        file_path = body["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        r2 = await http_client.get(url)
        r2.raise_for_status()
        d = _INBOUND_ROOT / chat_id
        d.mkdir(parents=True, exist_ok=True)
        local = d / f"{msg_id}_{_safe_filename(filename)}"
        local.write_bytes(r2.content)
        return str(local)
    except Exception:
        logger.warning(
            "telegram download failed for file_id=%s", file_id, exc_info=True,
        )
        return ""

_ADMIN_TTL = 600  # seconds


class TelegramMessenger(BaseMessenger):
    channel = "telegram"
    capabilities = MessengerCapabilities(
        supports_groups=True,
        supports_group_admin=True,
        supports_invite_links=True,
        supports_edit=True,
        supports_delete=True,
        supports_typing=True,
        supports_photos=True,
        supports_files=True,
        supports_voice=True,
        supports_markdown=True,
    )

    def __init__(self, token: str):
        self._token = token
        self._client: httpx.AsyncClient | None = None
        self._polling: bool = False
        self._bot_username: str = ""
        self._bot_id: str = ""
        self._admins_cache: dict[str, tuple[float, list[dict]]] = {}

    # --- Lifecycle ---------------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def init(self) -> None:
        """Create HTTP client + clear any existing webhook so polling works."""
        client = await self._ensure_client()
        await client.post(f"{API}/bot{self._token}/deleteWebhook")

    async def start(self, on_message: IncomingHandler) -> None:
        """Long-polling loop → IncomingMessage → on_message."""
        client = await self._ensure_client()
        self._polling = True

        me_resp = await client.get(f"{API}/bot{self._token}/getMe")
        me = me_resp.json().get("result", {})
        self._bot_username = me.get("username", "")
        self._bot_id = str(me.get("id", ""))
        logger.info("Polling started as @%s", self._bot_username)

        offset = 0
        while self._polling:
            try:
                resp = await client.get(
                    f"{API}/bot{self._token}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=35.0,
                )
                updates = resp.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    incoming = await self._parse_update(update)
                    if incoming is None:
                        continue
                    logger.info(
                        "[chat:%s type:%s sender:%s] Received: %s",
                        incoming.chat_id, incoming.chat_type, incoming.sender_id,
                        (incoming.text or "")[:100],
                    )
                    asyncio.create_task(on_message(incoming))
            except httpx.ReadTimeout:
                continue
            except Exception:
                logger.exception("Polling error, retrying in 3s")
                await asyncio.sleep(3)

    async def stop(self) -> None:
        self._polling = False
        logger.info("Polling stopped")
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _resolve_external_chat(self, internal_id: str) -> str | None:
        """internal_chat_id → external Telegram chat id (string of int).
        Returns None if not found."""
        from src import db
        ext = await db.lookup_external_for_conversation(internal_id)
        if not ext:
            logger.warning("no conversation row for internal_id=%s", internal_id)
            return None
        return ext[1]

    async def _resolve_external_user(self, internal_id: str) -> str | None:
        """internal person_id → external Telegram user id (string of int).
        Returns None if not found."""
        from src import db
        ext = await db.lookup_external_for_person(internal_id)
        if not ext:
            logger.warning("no external_identity for internal_id=%s", internal_id)
            return None
        return ext[1]

    async def _parse_update(self, update: dict) -> IncomingMessage | None:
        message = update.get("message", {})
        text = message.get("text", "")
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        from_user = message.get("from", {}) or {}
        sender_id = from_user.get("id")
        chat_type_raw = chat.get("type", "")
        new_members_raw = message.get("new_chat_members", []) or []

        if not chat_id:
            return None
        if not text and not new_members_raw:
            return None

        is_group = chat_type_raw in ("group", "supergroup")
        chat_type = "group" if is_group else "dm"
        bot_mentioned = bool(self._bot_username) and f"@{self._bot_username}" in (text or "")
        group_name = chat.get("title", "") if is_group else ""

        # --- Mentions harvest ---
        mentions: list[dict] = []
        username_mentions: list[str] = []
        for ent in (message.get("entities") or []):
            etype = ent.get("type")
            if etype == "text_mention":
                u = ent.get("user", {}) or {}
                if u.get("id"):
                    mentions.append({
                        "id": u["id"],
                        "name": full_name(u),
                        "username": u.get("username", ""),
                    })
            elif etype == "mention":
                off = ent.get("offset", 0)
                length = ent.get("length", 0)
                mention_text = (text or "")[off:off + length].lstrip("@")
                if mention_text:
                    username_mentions.append(mention_text)

        # --- Reply-to ---
        reply_to_message_id = None
        reply_to_sender_id = None
        rt = message.get("reply_to_message", {})
        if rt:
            reply_to_message_id = str(rt.get("message_id", "")) or None
            rt_from = rt.get("from", {}) or {}
            if rt_from.get("id"):
                reply_to_sender_id = str(rt_from["id"])

        # --- New members ---
        new_members: list[dict] = []
        for m in new_members_raw:
            if m.get("is_bot"):
                continue
            if m.get("id"):
                new_members.append({
                    "id": m["id"],
                    "name": full_name(m),
                    "username": m.get("username", ""),
                })

        # --- Attachments ---
        attachments: list[Attachment] = []
        msg_id_str = str(message.get("message_id", ""))
        chat_id_str = str(chat_id)
        if message.get("photo"):
            photos = message["photo"]
            largest = photos[-1]
            unique = largest.get("file_unique_id", largest.get("file_id", "p"))
            name = f"{unique}.jpg"
            local = await _download_to_disk(
                self._client, self._token, largest["file_id"],
                chat_id_str, msg_id_str, name,
            )
            attachments.append(Attachment(
                kind="photo",
                url=local,
                mime_type="image/jpeg",
                filename=name,
                size_bytes=int(largest.get("file_size", 0)),
            ))
        if message.get("voice"):
            attachments.append(Attachment(kind="voice"))  # voice out of scope
        if message.get("document"):
            doc = message["document"]
            name = doc.get("file_name") or f"doc_{doc.get('file_unique_id', '')}"
            local = await _download_to_disk(
                self._client, self._token, doc["file_id"],
                chat_id_str, msg_id_str, name,
            )
            attachments.append(Attachment(
                kind="file",
                url=local,
                filename=name,
                mime_type=doc.get("mime_type", ""),
                size_bytes=int(doc.get("file_size", 0)),
            ))

        # Resolve external chat_id / sender_id → internal ids (UUID).
        # In Phase 5 this moves to MessageRouter; for now we do it inline so
        # downstream code (agent, tools, db) sees only internal ids. The
        # original payload stays on `raw` for the harvester.
        from src import db
        internal_chat_id = await db.resolve_or_create_conversation(
            "telegram", str(chat_id), chat_type, group_name,
        )
        internal_sender_id = ""
        if sender_id:
            internal_sender_id = await db.resolve_or_create_person(
                "telegram", str(sender_id),
                full_name(from_user), from_user.get("username", "") or "",
            )

        if reply_to_sender_id:
            reply_to_sender_id = await db.resolve_or_create_person(
                "telegram", reply_to_sender_id, "", "",
            )

        for m in mentions:
            m["id"] = await db.resolve_or_create_person(
                "telegram", str(m["id"]),
                m.get("name", ""), m.get("username", ""),
            )
        for m in new_members:
            m["id"] = await db.resolve_or_create_person(
                "telegram", str(m["id"]),
                m.get("name", ""), m.get("username", ""),
            )

        return IncomingMessage(
            channel="telegram",
            chat_id=internal_chat_id,
            chat_type=chat_type,
            sender_id=internal_sender_id,
            sender_name=full_name(from_user),
            text=text or "",
            attachments=attachments,
            is_mentioned=bot_mentioned,
            is_forwarded=bool(message.get("forward_date")),
            reply_to_message_id=reply_to_message_id,
            reply_to_sender_id=reply_to_sender_id,
            message_id=str(message.get("message_id", "")),
            timestamp=int(message.get("date", 0)),
            group_name=group_name,
            mentions=mentions,
            username_mentions=username_mentions,
            new_members=new_members,
            raw=update,
        )

    # --- Send --------------------------------------------------------------

    @staticmethod
    def _map_format(fmt: str) -> str:
        """Map channel-agnostic FormatHint → Telegram parse_mode."""
        f = (fmt or "").lower()
        if f in ("markdown", "md"):
            return "Markdown"
        if f == "html":
            return "HTML"
        return ""  # plain

    async def send_message(
        self,
        chat_id: str,                  # internal_chat_id (UUID)
        text: str,
        *,
        format: str = "markdown",
        save_history: bool = True,
        reply_to_message_id: str | None = None,
    ) -> OutgoingMessage:
        external_chat_id = await self._resolve_external_chat(chat_id)
        if not external_chat_id:
            return OutgoingMessage(message_id="", chat_id=chat_id)

        client = await self._ensure_client()
        parse_mode = self._map_format(format)
        payload: dict = {"chat_id": int(external_chat_id), "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = int(reply_to_message_id)

        resp = await client.post(f"{API}/bot{self._token}/sendMessage", json=payload)
        data = resp.json()
        ok = data.get("ok")
        message_id = data["result"]["message_id"] if ok else None

        # Fallback: parse-mode errors → retry as plain
        if not ok:
            desc = (data.get("description") or "").lower()
            if parse_mode and ("can't parse" in desc or "parse entities" in desc):
                logger.warning("sendMessage Markdown failed, retrying plain: %s", desc)
                payload.pop("parse_mode", None)
                resp2 = await client.post(f"{API}/bot{self._token}/sendMessage", json=payload)
                data2 = resp2.json()
                if data2.get("ok"):
                    message_id = data2["result"]["message_id"]
                    ok = True
                else:
                    logger.warning("sendMessage plain retry also failed: %s", data2)
            else:
                logger.warning("sendMessage failed: %s", data)

        if ok and save_history and chat_id and text:
            try:
                from src import db
                await db.save_message(chat_id, "assistant", text)
            except Exception:
                logger.warning("save_message after send failed", exc_info=True)

        return OutgoingMessage(
            message_id=str(message_id) if message_id else "",
            chat_id=str(chat_id),
        )

    async def edit_message(
        self,
        chat_id: str,                  # internal_chat_id (UUID)
        message_id: str,
        text: str,
        *,
        format: str = "markdown",
    ) -> None:
        external_chat_id = await self._resolve_external_chat(chat_id)
        if not external_chat_id:
            return

        client = await self._ensure_client()
        parse_mode = self._map_format(format)
        payload: dict = {
            "chat_id": int(external_chat_id),
            "message_id": int(message_id),
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        resp = await client.post(f"{API}/bot{self._token}/editMessageText", json=payload)
        data = resp.json()
        if data.get("ok"):
            return
        desc = (data.get("description") or "").lower()
        if parse_mode and ("can't parse" in desc or "parse entities" in desc):
            logger.warning("editMessageText Markdown failed, retrying plain: %s", desc)
            payload.pop("parse_mode", None)
            resp2 = await client.post(f"{API}/bot{self._token}/editMessageText", json=payload)
            data2 = resp2.json()
            if data2.get("ok"):
                return
            logger.warning("editMessageText plain retry also failed: %s", data2)
        else:
            logger.warning("editMessageText failed: %s", data)

    # --- Identity ----------------------------------------------------------

    async def get_bot_id(self) -> str:
        if self._bot_id:
            return self._bot_id
        client = await self._ensure_client()
        r = await client.get(f"{API}/bot{self._token}/getMe", timeout=10)
        self._bot_id = str(r.json().get("result", {}).get("id", ""))
        return self._bot_id

    # --- Group admin -------------------------------------------------------

    async def get_chat_member(self, chat_id: str, user_id: str) -> dict:
        ext_chat = await self._resolve_external_chat(chat_id)
        ext_user = await self._resolve_external_user(user_id)
        if not ext_chat or not ext_user:
            return {}
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/getChatMember",
                json={"chat_id": int(ext_chat), "user_id": int(ext_user)},
                timeout=10,
            )
        return r.json().get("result", {})

    async def add_chat_member(self, chat_id: str, user_id: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        ext_user = await self._resolve_external_user(user_id)
        if not ext_chat or not ext_user:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/addChatMember",
                json={"chat_id": int(ext_chat), "user_id": int(ext_user)},
                timeout=10,
            )
        return r.json().get("ok", False)

    async def set_chat_title(self, chat_id: str, title: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/setChatTitle",
                json={"chat_id": int(ext_chat), "title": title},
                timeout=10,
            )
        return r.json().get("ok", False)

    async def set_chat_description(self, chat_id: str, description: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/setChatDescription",
                json={"chat_id": int(ext_chat), "description": description},
                timeout=10,
            )
        return r.json().get("ok", False)

    async def pin_chat_message(self, chat_id: str, message_id: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/pinChatMessage",
                json={
                    "chat_id": int(ext_chat),
                    "message_id": int(message_id),
                    "disable_notification": False,
                },
                timeout=10,
            )
        return r.json().get("ok", False)

    async def unpin_all_chat_messages(self, chat_id: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/unpinAllChatMessages",
                json={"chat_id": int(ext_chat)},
                timeout=10,
            )
        return r.json().get("ok", False)

    async def ban_chat_member(self, chat_id: str, user_id: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        ext_user = await self._resolve_external_user(user_id)
        if not ext_chat or not ext_user:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/banChatMember",
                json={"chat_id": int(ext_chat), "user_id": int(ext_user)},
                timeout=10,
            )
        return r.json().get("ok", False)

    async def unban_chat_member(self, chat_id: str, user_id: str) -> bool:
        ext_chat = await self._resolve_external_chat(chat_id)
        ext_user = await self._resolve_external_user(user_id)
        if not ext_chat or not ext_user:
            return False
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/unbanChatMember",
                json={
                    "chat_id": int(ext_chat),
                    "user_id": int(ext_user),
                    "only_if_banned": True,
                },
                timeout=10,
            )
        return r.json().get("ok", False)

    async def create_invite_link(
        self, chat_id: str, *, member_limit: int = 1, expire_hours: int = 24
    ) -> str:
        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return ""
        expire_date = int(_time.time()) + expire_hours * 3600
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{API}/bot{self._token}/createChatInviteLink",
                json={
                    "chat_id": int(ext_chat),
                    "member_limit": member_limit,
                    "expire_date": expire_date,
                },
                timeout=10,
            )
        return r.json().get("result", {}).get("invite_link", "")

    async def get_chat_administrators(self, chat_id: str) -> list[dict]:
        """Returns admin list. `user_id` in each entry is **internal** (resolved
        by Telegram payload through resolve_or_create_person), so callers can
        compare against ChatContext.boss_chat_id directly.
        """
        now = _time.time()
        cached = self._admins_cache.get(chat_id)
        if cached and now - cached[0] < _ADMIN_TTL:
            return cached[1]

        ext_chat = await self._resolve_external_chat(chat_id)
        if not ext_chat:
            return []

        client = await self._ensure_client()
        resp = await client.post(
            f"{API}/bot{self._token}/getChatAdministrators",
            json={"chat_id": int(ext_chat)},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("getChatAdministrators failed for %s: %s", chat_id, data)
            return []

        from src import db
        result = []
        for m in data.get("result", []):
            user = m.get("user", {})
            if user.get("is_bot"):
                continue
            ext_user_id = user.get("id")
            internal_user_id = await db.resolve_or_create_person(
                "telegram", str(ext_user_id),
                full_name(user), user.get("username", "") or "",
            )
            result.append({
                "user_id": internal_user_id,
                "name": full_name(user),
                "username": user.get("username", ""),
                "status": m.get("status", ""),
            })
        self._admins_cache[chat_id] = (now, result)
        return result
