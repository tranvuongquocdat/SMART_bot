from datetime import datetime, timezone

import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield ReminderRepo(conn)


async def _make(repo, boss="b1", content="x"):
    return await repo.create(
        boss, content,
        datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
    )


async def test_set_and_get_lark_record_id(repo):
    rid = await _make(repo)
    await repo.set_lark_record_id(rid, "rec-abc")
    row = await repo.get_by_id(rid)
    assert row["lark_record_id"] == "rec-abc"


async def test_find_by_lark_id(repo):
    rid = await _make(repo)
    await repo.set_lark_record_id(rid, "rec-xyz")
    found = await repo.find_by_lark_id("b1", "rec-xyz")
    assert found is not None
    assert found["id"] == rid


async def test_find_by_lark_id_other_boss_returns_none(repo):
    rid = await _make(repo, boss="b1")
    await repo.set_lark_record_id(rid, "rec-1")
    assert await repo.find_by_lark_id("b2", "rec-1") is None


async def test_list_unsynced_pending(repo):
    r1 = await _make(repo, content="unsynced")
    r2 = await _make(repo, content="synced")
    await repo.set_lark_record_id(r2, "rec-2")
    rows = await repo.list_unsynced_pending("b1")
    ids = [r["id"] for r in rows]
    assert ids == [r1]


async def test_list_unsynced_pending_skips_done(repo):
    r1 = await _make(repo, content="will be done")
    await repo.mark_done(r1)
    rows = await repo.list_unsynced_pending("b1")
    assert rows == []


async def test_list_with_lark_id(repo):
    r1 = await _make(repo)
    r2 = await _make(repo)
    await repo.set_lark_record_id(r1, "rec-1")
    await repo.set_lark_record_id(r2, "rec-2")
    rows = await repo.list_with_lark_id("b1")
    pairs = sorted((r["id"], r["lark_record_id"]) for r in rows)
    assert pairs == [(r1, "rec-1"), (r2, "rec-2")]


async def test_tombstone(repo):
    rid = await _make(repo)
    await repo.tombstone(rid)
    row = await repo.get_by_id(rid)
    assert row["status"] == "done"


async def test_update_remind_at_and_content(repo):
    rid = await _make(repo)
    new_dt = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    await repo.update_remind_at_and_content(rid, content="updated", remind_at=new_dt)
    row = await repo.get_by_id(rid)
    assert row["content"] == "updated"
    assert row["remind_at"].startswith("2026-06-01 09:00")
