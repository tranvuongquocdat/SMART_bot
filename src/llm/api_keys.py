import json

from cryptography.fernet import Fernet

from src.config import settings

_fernet = Fernet(settings.FERNET_KEY.encode())


def make_api_key_provider(pool):
    async def provider(boss_id: int, provider_name: str) -> str:
        async with pool.acquire() as c:
            blob = await c.fetchval(
                "SELECT api_keys_enc FROM users WHERE id=$1", boss_id
            )
        if blob:
            try:
                keys = json.loads(_fernet.decrypt(bytes(blob)).decode())
                if provider_name in keys:
                    return keys[provider_name]
            except Exception:
                pass
        env_key = {
            "openai": settings.PLATFORM_OPENAI_API_KEY,
            "groq": settings.PLATFORM_GROQ_API_KEY,
        }.get(provider_name)
        if not env_key:
            raise LookupError(
                f"no api key for boss={boss_id} provider={provider_name}"
            )
        return env_key

    return provider
