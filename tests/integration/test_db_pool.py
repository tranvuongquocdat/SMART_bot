import pytest

from src.infra.db import create_pool


@pytest.mark.asyncio
async def test_pool_query_one():
    pool = await create_pool()
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1")
    await pool.close()
    assert v == 1
