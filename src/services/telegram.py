import asyncio
import logging

import httpx

logger = logging.getLogger("telegram")

_client: httpx.AsyncClient | None = None
_token: str = ""
_polling: bool = False

API = "https://api.telegram.org"


async def init_telegram(token: str):
    global _client, _token
    _token = token
    _client = httpx.AsyncClient(timeout=30.0)
    # Clear any existing webhook so polling works
    await _client.post(f"{API}/bot{_token}/deleteWebhook")


async def send(
    chat_id: int,
    text: str,
    parse_mode: str = "Markdown",
    save_history: bool = True,
) -> int | None:
    """Send message, return message_id. Falls back to plain text on Markdown parse errors.

    When save_history is True (default), persist the outbound text to the `messages`
    table as role='assistant' so it shows up in get_recent()-based context for
    future turns. Pass save_history=False for transient placeholders.
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    resp = await _client.post(f"{API}/bot{_token}/sendMessage", json=payload)
    data = resp.json()
    ok = data.get("ok")
    message_id = data["result"]["message_id"] if ok else None
    if not ok:
        desc = (data.get("description") or "").lower()
        if parse_mode and ("can't parse" in desc or "parse entities" in desc):
            logger.warning("sendMessage Markdown failed, retrying plain: %s", desc)
            payload["parse_mode"] = ""
            resp2 = await _client.post(f"{API}/bot{_token}/sendMessage", json=payload)
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
            from src import db  # local import to avoid import cycle at module load
            await db.save_message(chat_id, "assistant", text)
        except Exception:
            logger.warning("save_message after send failed", exc_info=True)

    return message_id


# Alias for compatibility
send_message = send


async def edit_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown"):
    """Edit existing message via editMessageText API. Falls back to plain text on Markdown parse errors."""
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    resp = await _client.post(f"{API}/bot{_token}/editMessageText", json=payload)
    data = resp.json()
    if data.get("ok"):
        return
    desc = (data.get("description") or "").lower()
    # Telegram Markdown parse errors → retry plain text so the message still delivers
    if parse_mode and ("can't parse" in desc or "parse entities" in desc):
        logger.warning("editMessageText Markdown failed, retrying plain: %s", desc)
        payload["parse_mode"] = ""
        resp2 = await _client.post(f"{API}/bot{_token}/editMessageText", json=payload)
        data2 = resp2.json()
        if data2.get("ok"):
            return
        logger.warning("editMessageText plain retry also failed: %s", data2)
    else:
        logger.warning("editMessageText failed: %s", data)


async def start_polling(on_message):
    """
    Long polling loop.

    on_message callback signature (backward-compatible qua kwargs):
        on_message(text, chat_id, sender_id, is_group, bot_mentioned, group_name,
                   *, sender_name="", mentions=None, username_mentions=None,
                   reply_to=None, new_members=None)

    New kwargs:
      sender_name: display name from message.from
      mentions: [{id, name, username}] từ entities type=text_mention
      username_mentions: [str] — @username text chưa resolve user_id
      reply_to: {id, name, username} or None
      new_members: [{id, name, username}] từ new_chat_members
    """
    global _polling
    _polling = True

    me_resp = await _client.get(f"{API}/bot{_token}/getMe")
    bot_username = me_resp.json().get("result", {}).get("username", "")
    logger.info("Polling started as @%s", bot_username)

    offset = 0

    while _polling:
        try:
            resp = await _client.get(
                f"{API}/bot{_token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35.0,
            )
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "")
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                from_user = message.get("from", {}) or {}
                sender_id = from_user.get("id")
                chat_type = chat.get("type", "")

                new_members_raw = message.get("new_chat_members", []) or []

                if not chat_id:
                    continue
                if not text and not new_members_raw:
                    continue

                is_group = chat_type in ("group", "supergroup")
                bot_mentioned = bool(bot_username) and f"@{bot_username}" in (text or "")
                group_name = chat.get("title", "") if is_group else ""

                # --- Harvest identity data from update ---
                sender_name = _full_name(from_user)

                mentions: list[dict] = []
                username_mentions: list[str] = []
                for ent in (message.get("entities") or []):
                    etype = ent.get("type")
                    if etype == "text_mention":
                        u = ent.get("user", {}) or {}
                        if u.get("id"):
                            mentions.append({
                                "id": u["id"],
                                "name": _full_name(u),
                                "username": u.get("username", ""),
                            })
                    elif etype == "mention":
                        off = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mention_text = (text or "")[off:off + length].lstrip("@")
                        if mention_text:
                            username_mentions.append(mention_text)

                reply_to = None
                rt = message.get("reply_to_message", {})
                if rt:
                    rt_from = rt.get("from", {}) or {}
                    if rt_from.get("id"):
                        reply_to = {
                            "id": rt_from["id"],
                            "name": _full_name(rt_from),
                            "username": rt_from.get("username", ""),
                        }

                new_members: list[dict] = []
                for m in new_members_raw:
                    if m.get("is_bot"):
                        continue
                    if m.get("id"):
                        new_members.append({
                            "id": m["id"],
                            "name": _full_name(m),
                            "username": m.get("username", ""),
                        })

                logger.info(
                    "[chat:%s type:%s sender:%s] Received: %s",
                    chat_id, chat_type, sender_id, (text or "")[:100],
                )
                asyncio.create_task(
                    on_message(
                        text or "", chat_id, sender_id, is_group, bot_mentioned, group_name,
                        sender_name=sender_name,
                        mentions=mentions,
                        username_mentions=username_mentions,
                        reply_to=reply_to,
                        new_members=new_members,
                    )
                )

        except httpx.ReadTimeout:
            continue
        except Exception:
            logger.exception("Polling error, retrying in 3s")
            await asyncio.sleep(3)


def _full_name(user: dict) -> str:
    """Join first_name + last_name, stripped."""
    return (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip()


async def get_chat_member(chat_id: int, user_id: int) -> dict:
    """Returns chat member info including status ('administrator', 'member', etc.)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/getChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    return r.json().get("result", {})


async def add_chat_member(chat_id: int, user_id: int) -> bool:
    """Add a user to the group. Requires bot to be admin. User must have started bot."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/addChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def set_chat_title(chat_id: int, title: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/setChatTitle",
            json={"chat_id": chat_id, "title": title},
            timeout=10,
        )
    return r.json().get("ok", False)


async def set_chat_description(chat_id: int, description: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/setChatDescription",
            json={"chat_id": chat_id, "description": description},
            timeout=10,
        )
    return r.json().get("ok", False)


async def pin_chat_message(chat_id: int, message_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/pinChatMessage",
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": False},
            timeout=10,
        )
    return r.json().get("ok", False)


async def unpin_all_chat_messages(chat_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/unpinAllChatMessages",
            json={"chat_id": chat_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def ban_chat_member(chat_id: int, user_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/banChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def unban_chat_member(chat_id: int, user_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/unbanChatMember",
            json={"chat_id": chat_id, "user_id": user_id, "only_if_banned": True},
            timeout=10,
        )
    return r.json().get("ok", False)


async def create_invite_link(chat_id: int, member_limit: int = 1, expire_hours: int = 24) -> str:
    """Create a single-use invite link. Returns the link string or empty string on failure."""
    import time
    expire_date = int(time.time()) + expire_hours * 3600
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/createChatInviteLink",
            json={"chat_id": chat_id, "member_limit": member_limit, "expire_date": expire_date},
            timeout=10,
        )
    result = r.json().get("result", {})
    return result.get("invite_link", "")


async def get_bot_id() -> int | None:
    """Returns the bot's own user_id."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API}/bot{_token}/getMe", timeout=10)
    return r.json().get("result", {}).get("id")


def stop_polling():
    global _polling
    _polling = False
    logger.info("Polling stopped")


async def close_telegram():
    stop_polling()
    if _client:
        await _client.aclose()


# --- Admin list cache (10 min TTL) ---
_admins_cache: dict[int, tuple[float, list[dict]]] = {}
_ADMIN_TTL = 600  # seconds


async def get_chat_administrators(chat_id: int) -> list[dict]:
    """
    Returns list of admin members: [{user_id, name, username, status}, ...].
    Cached per-chat for 10 minutes.
    Privacy note: bot không list được non-admin members (Telegram API limit).
    """
    import time as _time
    now = _time.time()
    cached = _admins_cache.get(chat_id)
    if cached and now - cached[0] < _ADMIN_TTL:
        return cached[1]

    resp = await _client.post(
        f"{API}/bot{_token}/getChatAdministrators",
        json={"chat_id": chat_id},
        timeout=10,
    )
    data = resp.json()
    if not data.get("ok"):
        logger.warning("getChatAdministrators failed for %s: %s", chat_id, data)
        return []

    result = []
    for m in data.get("result", []):
        user = m.get("user", {})
        if user.get("is_bot"):
            continue
        result.append({
            "user_id": user.get("id"),
            "name": (user.get("first_name", "") + " " + user.get("last_name", "")).strip(),
            "username": user.get("username", ""),
            "status": m.get("status", ""),
        })
    _admins_cache[chat_id] = (now, result)
    return result
