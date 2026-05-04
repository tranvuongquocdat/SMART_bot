import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema
from src.repositories.note_repo import NoteRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield NoteRepo(conn)


async def test_upsert_returns_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    assert isinstance(rid, int) and rid > 0


async def test_upsert_returns_same_id_on_conflict(repo):
    a = await repo.upsert("b1", "personal", "x", "v1")
    b = await repo.upsert("b1", "personal", "x", "v2")
    assert a == b


async def test_set_lark_record_id_and_get_by_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    await repo.set_lark_record_id(rid, "rec-1")
    row = await repo.get_by_id(rid)
    assert row["lark_record_id"] == "rec-1"


async def test_find_by_lark_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    await repo.set_lark_record_id(rid, "rec-1")
    found = await repo.find_by_lark_id("b1", "rec-1")
    assert found["id"] == rid


async def test_list_unsynced(repo):
    a = await repo.upsert("b1", "personal", "x", "v")
    b = await repo.upsert("b1", "personal", "y", "v")
    await repo.set_lark_record_id(b, "rec-b")
    rows = await repo.list_unsynced("b1")
    assert [r["id"] for r in rows] == [a]


async def test_list_with_lark_id(repo):
    a = await repo.upsert("b1", "personal", "x", "v")
    b = await repo.upsert("b1", "personal", "y", "v")
    await repo.set_lark_record_id(a, "rec-a")
    await repo.set_lark_record_id(b, "rec-b")
    rows = await repo.list_with_lark_id("b1")
    assert sorted(r["lark_record_id"] for r in rows) == ["rec-a", "rec-b"]


async def test_delete_by_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "v")
    await repo.delete_by_id(rid)
    assert await repo.get_by_id(rid) is None
