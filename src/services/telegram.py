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

    on_message callback signature: (text, chat_id, sender_id, is_group, bot_mentioned)
    - text: message text
    - chat_id: conversation id (user or group)
    - sender_id: who sent (from.id)
    - is_group: True if chat.type is "group" or "supergroup"
    - bot_mentioned: True if @bot_username appears in text
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

                logger.info(
                    "[chat:%s type:%s sender:%s] Received: %s",
                    chat_id, chat_type, sender_id, text[:100],
                )
                asyncio.create_task(
                    on_message(text, chat_id, sender_id, is_group, bot_mentioned)
                )

        except httpx.ReadTimeout:
            continue  # normal for long polling
        except Exception:
            logger.exception("Polling error, retrying in 3s")
            await asyncio.sleep(3)


def stop_polling():
    global _polling
    _polling = False
    logger.info("Polling stopped")


async def close_telegram():
    stop_polling()
    if _client:
        await _client.aclose()
