"""
Integration tests: scheduled review CRUD flow.
Tests create, list, update (toggle), delete — including owner isolation.
"""
import pytest
import aiosqlite

from src.db import (
    _init_schema,
    _migrate_schema,
    create_scheduled_review,
    list_scheduled_reviews,
    update_scheduled_review,
    delete_scheduled_review,
    get_all_enabled_reviews,
)


@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        await _migrate_schema(conn)
        yield conn


async def test_create_and_list_review(db):
    rid = await create_scheduled_review(db, "1001", "08:00", "morning_brief")
    assert rid is not None

    rows = await list_scheduled_reviews(db, "1001")
    assert len(rows) == 1
    assert rows[0]["cron_time"] == "08:00"
    assert rows[0]["content_type"] == "morning_brief"
    assert rows[0]["enabled"] == 1


async def test_custom_prompt_stored(db):
    await create_scheduled_review(
        db, "1001", "09:00", "custom", custom_prompt="List overdue tasks"
    )
    rows = await list_scheduled_reviews(db, "1001")
    assert rows[0]["custom_prompt"] == "List overdue tasks"


async def test_toggle_disable(db):
    rid = await create_scheduled_review(db, "1001", "17:00", "evening_summary")
    ok = await update_scheduled_review(db, rid, owner_id="1001", enabled=0)
    assert ok is True

    rows = await list_scheduled_reviews(db, "1001")
    assert rows[0]["enabled"] == 0


async def test_toggle_wrong_owner_returns_false(db):
    rid = await create_scheduled_review(db, "1001", "17:00", "evening_summary")
    ok = await update_scheduled_review(db, rid, owner_id="9999", enabled=0)
    assert ok is False

    # Original should still be enabled
    rows = await list_scheduled_reviews(db, "1001")
    assert rows[0]["enabled"] == 1


async def test_delete_review(db):
    rid = await create_scheduled_review(db, "1001", "10:00", "morning_brief")
    ok = await delete_scheduled_review(db, rid, owner_id="1001")
    assert ok is True

    rows = await list_scheduled_reviews(db, "1001")
    assert len(rows) == 0


async def test_delete_wrong_owner_returns_false(db):
    rid = await create_scheduled_review(db, "1001", "10:00", "morning_brief")
    ok = await delete_scheduled_review(db, rid, owner_id="9999")
    assert ok is False

    rows = await list_scheduled_reviews(db, "1001")
    assert len(rows) == 1


async def test_get_all_enabled_filters_disabled(db):
    rid1 = await create_scheduled_review(db, "1001", "08:00", "morning_brief")
    rid2 = await create_scheduled_review(db, "1001", "17:00", "evening_summary")
    await update_scheduled_review(db, rid2, owner_id="1001", enabled=0)

    enabled = await get_all_enabled_reviews(db)
    ids = [r["id"] for r in enabled]
    assert rid1 in ids
    assert rid2 not in ids


async def test_update_invalid_column_raises(db):
    rid = await create_scheduled_review(db, "1001", "08:00", "morning_brief")
    with pytest.raises(ValueError, match="Invalid column"):
        await update_scheduled_review(db, rid, owner_id="1001", malicious_col="DROP TABLE")


async def test_review_list_scoped_to_owner(db):
    await create_scheduled_review(db, "1001", "08:00", "morning_brief")
    await create_scheduled_review(db, "2002", "09:00", "morning_brief")

    rows1 = await list_scheduled_reviews(db, "1001")
    rows2 = await list_scheduled_reviews(db, "2002")
    assert len(rows1) == 1
    assert len(rows2) == 1
    assert rows1[0]["cron_time"] == "08:00"
    assert rows2[0]["cron_time"] == "09:00"
