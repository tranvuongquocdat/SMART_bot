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


async def send(chat_id: int, text: str, parse_mode: str = "Markdown") -> int | None:
    """Send message, return message_id."""
    resp = await _client.post(
        f"{API}/bot{_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
    )
    data = resp.json()
    if data.get("ok"):
        return data["result"]["message_id"]
    logger.warning("sendMessage failed: %s", data)
    return None


# Alias for compatibility
send_message = send


async def edit_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown"):
    """Edit existing message via editMessageText API."""
    resp = await _client.post(
        f"{API}/bot{_token}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        },
    )
    data = resp.json()
    if not data.get("ok"):
        logger.warning("editMessageText failed: %s", data)


async def start_polling(on_message):
    """
    Long polling loop.

    on_message callback signature: (text, chat_id, sender_id, is_group, bot_mentioned, group_name)
    - text: message text
    - chat_id: conversation id (user or group)
    - sender_id: who sent (from.id)
    - is_group: True if chat.type is "group" or "supergroup"
    - bot_mentioned: True if @bot_username appears in text
    - group_name: group title (empty string for DMs)
    """
    global _polling
    _polling = True

    # Resolve bot username once for mention detection
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
                sender_id = message.get("from", {}).get("id")
                chat_type = chat.get("type", "")

                if not (text and chat_id):
                    continue

                is_group = chat_type in ("group", "supergroup")
                bot_mentioned = bool(bot_username) and f"@{bot_username}" in text
                group_name = chat.get("title", "") if is_group else ""

                logger.info(
                    "[chat:%s type:%s sender:%s] Received: %s",
                    chat_id, chat_type, sender_id, text[:100],
                )
                asyncio.create_task(
                    on_message(text, chat_id, sender_id, is_group, bot_mentioned, group_name)
                )

        except httpx.ReadTimeout:
            continue  # normal for long polling
        except Exception:
            logger.exception("Polling error, retrying in 3s")
            await asyncio.sleep(3)


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
