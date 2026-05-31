import asyncpg
from fastapi import Request


async def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool
