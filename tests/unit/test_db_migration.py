import pytest
import pytest_asyncio
import aiosqlite
import asyncio
from src.db import _init_schema, _migrate_schema

@pytest_asyncio.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        await _migrate_schema(conn)
        yield conn

@pytest.mark.asyncio
async def test_memberships_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memberships'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_memberships_composite_pk(db):
    await db.execute("INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) VALUES ('111', '222', 'member', 'Test', 'active')")
    await db.commit()
    with pytest.raises(Exception):
        await db.execute("INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) VALUES ('111', '222', 'partner', 'Test2', 'active')")
        await db.commit()

@pytest.mark.asyncio
async def test_pending_approvals_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_task_notifications_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_notifications'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_scheduled_reviews_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_reviews'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_bosses_has_lark_table_reminders(db):
    async with db.execute("PRAGMA table_info(bosses)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_table_reminders" in cols
    assert "lark_table_notes" in cols

@pytest.mark.asyncio
async def test_get_memberships_returns_active(db):
    from src.db import get_memberships, upsert_membership
    await upsert_membership(db, "111", "222", "member", "Test User", "active")
    await upsert_membership(db, "111", "333", "partner", "Test User", "pending")
    results = await get_memberships(db, "111")
    assert len(results) == 1
    assert results[0]["boss_chat_id"] == "222"

@pytest.mark.asyncio
async def test_upsert_membership_updates_on_conflict(db):
    from src.db import upsert_membership, get_membership
    await upsert_membership(db, "111", "222", "member", "Old Name", "active")
    await upsert_membership(db, "111", "222", "partner", "New Name", "active")
    m = await get_membership(db, "111", "222")
    assert m["person_type"] == "partner"
    assert m["name"] == "New Name"
