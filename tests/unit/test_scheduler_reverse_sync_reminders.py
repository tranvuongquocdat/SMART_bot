"""Verify reverse-sync handles: time edits, manual adds, tombstone, reconcile push.

Tests call _reverse_sync_reminders_for_boss directly (skipping the every-5-min
gate inside _sync_lark_to_sqlite) so the notes block does not interfere."""
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.scheduler as scheduler

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BOSS = {
    "chat_id": "b1", "name": "Boss",
    "lark_base_token": "base", "lark_table_reminders": "rmd",
}


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas, lark_table_reminders,"
        " lark_table_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "base", "ppl", "tsk", "prj", "idea", "rmd", "notes"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def _passthrough(fn, **kw):
    return await fn()


async def test_reverse_sync_pulls_time_change(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(setup_db).set_lark_record_id(rid, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-1",
            "Nội dung": "x",
            "Thời gian nhắc": "2026-06-15 09:00",
            "Trạng thái": "pending",
            "SQLite ID": rid,
        }]),
    )
    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT remind_at FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    # Stored UTC for Asia/Ho_Chi_Minh 2026-06-15 09:00 = 2026-06-15 02:00 UTC
    assert row["remind_at"].startswith("2026-06-15 02:00")


async def test_reverse_sync_tombstones_vanished(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(setup_db).set_lark_record_id(rid, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT status FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "done"


async def test_reverse_sync_pulls_manual_add(setup_db, monkeypatch):
    sync_back_mock = AsyncMock(return_value="rec-99")
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-99",
            "Nội dung": "manually added",
            "Thời gian nhắc": "2026-07-01 14:30",
            "Trạng thái": "pending",
            "Người nhận": "",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", sync_back_mock)
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)

    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT id, content, remind_at, lark_record_id FROM reminders"
        " WHERE boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["content"] == "manually added"
    assert row["lark_record_id"] == "rec-99"
    sync_back_mock.assert_awaited()  # SQLite ID written back to Lark


async def test_reverse_sync_skips_unparseable_time(setup_db, monkeypatch, caplog):
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-bad",
            "Nội dung": "x",
            "Thời gian nhắc": "not a date",
            "Trạng thái": "pending",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", AsyncMock())
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)
    with caplog.at_level("WARNING"):
        await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute("SELECT COUNT(*) AS n FROM reminders") as cur:
        row = await cur.fetchone()
    assert row["n"] == 0  # parse failed → no row created


async def test_reverse_sync_reconciles_unsynced_db_row(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="needs sync",
        remind_at=datetime(2026, 5, 4, 10),
    )
    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    sync_mock = AsyncMock(return_value="rec-new")
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", sync_mock)
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)

    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT lark_record_id, status FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    # Tombstone must NOT have happened (lark_record_id was NULL before this pass).
    assert row["lark_record_id"] == "rec-new"
    assert row["status"] == "pending"
