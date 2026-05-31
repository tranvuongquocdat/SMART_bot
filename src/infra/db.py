import asyncpg

from src.config import settings


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        settings.POSTGRES_DSN,
        min_size=2,
        max_size=20,
        command_timeout=30,
    )
