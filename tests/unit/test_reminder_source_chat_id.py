"""reminders.source_chat_id column + repo support."""
from datetime import datetime, timezone

import aiosqlite
import pytest
import pytest_asyncio

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield ReminderRepo(conn)


async def test_reminders_has_source_chat_id(repo):
    async with repo._db.execute("PRAGMA table_info(reminders)") as cur:
        cols = [row[1] async for row in cur]
    assert "source_chat_id" in cols


async def test_create_persists_source_chat_id(repo):
    rid = await repo.create(
        boss_chat_id="b1",
        content="x",
        remind_at=datetime(2026, 5, 11, 10, tzinfo=timezone.utc),
        source_chat_id="group-abc",
    )
    row = await repo.get_by_id(rid)
    assert row["source_chat_id"] == "group-abc"


async def test_create_source_chat_id_optional(repo):
    rid = await repo.create(
        boss_chat_id="b1",
        content="x",
        remind_at=datetime(2026, 5, 11, 10, tzinfo=timezone.utc),
    )
    row = await repo.get_by_id(rid)
    assert row["source_chat_id"] is None
