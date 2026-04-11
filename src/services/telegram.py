import httpx

_client: httpx.AsyncClient | None = None
_token: str = ""

API = "https://api.telegram.org"


async def init_telegram(token: str):
    global _client, _token
    _token = token
    _client = httpx.AsyncClient(timeout=15.0)


async def send(chat_id: int, text: str):
    await _client.post(
        f"{API}/bot{_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
    )


async def set_webhook(url: str):
    await _client.post(
        f"{API}/bot{_token}/setWebhook",
        json={"url": f"{url}/webhook/telegram"},
    )


async def close_telegram():
    if _client:
        await _client.aclose()
