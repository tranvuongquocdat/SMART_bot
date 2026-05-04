"""reminders.lark_record_id and notes.lark_record_id must be present after migration."""
import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema


@pytest_asyncio.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield conn


async def test_reminders_has_lark_record_id(db):
    async with db.execute("PRAGMA table_info(reminders)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_record_id" in cols


async def test_notes_has_lark_record_id(db):
    async with db.execute("PRAGMA table_info(notes)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_record_id" in cols


async def test_lark_record_id_nullable_default(db):
    """Existing rows should default to NULL, allowing migration of legacy data."""
    await db.execute(
        "INSERT INTO reminders (boss_chat_id, content, remind_at) VALUES (?, ?, ?)",
        ("boss-1", "demo", "2026-05-04 10:00:00"),
    )
    await db.commit()
    async with db.execute("SELECT lark_record_id FROM reminders") as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] is None
