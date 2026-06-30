import pytest

from src.domain.memory import MemoryScope
from src.repositories.base import BossContext
from src.repositories.memory_entries import MemoryEntriesRepo


@pytest.mark.asyncio
async def test_upsert_and_get(db_pool, boss_user):
    repo = MemoryEntriesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    mid = await repo.upsert(
        scope=MemoryScope.SEMANTIC,
        key="preferred_name",
        content="Đạt",
    )
    fetched = await repo.get(MemoryScope.SEMANTIC, "preferred_name")
    assert fetched is not None
    assert fetched.id == mid
    assert fetched.content == "Đạt"
    assert fetched.scope == MemoryScope.SEMANTIC


@pytest.mark.asyncio
async def test_upsert_updates_existing(db_pool, boss_user):
    repo = MemoryEntriesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    mid1 = await repo.upsert(
        scope=MemoryScope.SEMANTIC, key="preferred_name", content="Đạt"
    )
    mid2 = await repo.upsert(
        scope=MemoryScope.SEMANTIC, key="preferred_name", content="Đại"
    )
    assert mid1 == mid2  # same row, updated
    fetched = await repo.get(MemoryScope.SEMANTIC, "preferred_name")
    assert fetched.content == "Đại"


@pytest.mark.asyncio
async def test_insert_episodic_no_key(db_pool, boss_user):
    repo = MemoryEntriesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    mid_a = await repo.insert(
        scope=MemoryScope.EPISODIC, content="Hôm nay sếp họp lúc 9h"
    )
    mid_b = await repo.insert(
        scope=MemoryScope.EPISODIC, content="Sếp hủy meeting 10h"
    )
    assert mid_a != mid_b
    rows = await repo.list_all(MemoryScope.EPISODIC)
    assert len(rows) == 2
