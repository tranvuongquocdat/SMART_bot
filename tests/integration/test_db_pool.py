import pytest


@pytest.mark.asyncio
async def test_pool_query_one(db_pool):
    async with db_pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1")
    assert v == 1
