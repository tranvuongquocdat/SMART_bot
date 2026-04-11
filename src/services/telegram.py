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


async def send(chat_id: int, text: str):
    await _client.post(
        f"{API}/bot{_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
    )


async def start_polling(on_message):
    """Long polling loop. on_message(text, chat_id) is called for each message."""
    global _polling
    _polling = True
    offset = 0
    logger.info("Polling started")

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
                chat_id = message.get("chat", {}).get("id")

                if text and chat_id:
                    logger.info(f"[chat:{chat_id}] Received: {text[:100]}")
                    asyncio.create_task(on_message(text, chat_id))

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
