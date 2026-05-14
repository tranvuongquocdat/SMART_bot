from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.scheduler as scheduler


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


BOSS = {"chat_id": "b1", "lark_base_token": "base", "lark_table_notes": "notes"}


async def test_notes_reverse_sync_pulls_lark_edit(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="old",
    )
    from src.repositories.note_repo import NoteRepo
    await NoteRepo(setup_db).set_lark_record_id(sqlite_id, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-1",
            "Loại": "personal", "Ref ID": "b1",
            "Nội dung": "edited via Lark UI",
            "SQLite ID": sqlite_id,
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", AsyncMock())

    await scheduler._reverse_sync_notes_for_boss(BOSS)

    async with setup_db.execute(
        "SELECT content FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row["content"] == "edited via Lark UI"


async def test_notes_reverse_sync_pulls_manual_add(setup_db, monkeypatch):
    sync_back = AsyncMock(return_value="rec-99")
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-99",
            "Loại": "project", "Ref ID": "P-1",
            "Nội dung": "manually added in lark",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", sync_back)
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)

    await scheduler._reverse_sync_notes_for_boss(BOSS)

    note = await db.get_note("b1", "project", "P-1")
    assert note is not None
    assert note["content"] == "manually added in lark"
    assert note["lark_record_id"] == "rec-99"


async def test_notes_reverse_sync_deletes_vanished(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="x",
    )
    from src.repositories.note_repo import NoteRepo
    await NoteRepo(setup_db).set_lark_record_id(sqlite_id, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", AsyncMock())

    await scheduler._reverse_sync_notes_for_boss(BOSS)

    async with setup_db.execute(
        "SELECT id FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row is None


async def test_notes_reverse_sync_reconciles_unsynced(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="needs sync",
    )
    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    sync_mock = AsyncMock(return_value="rec-new")
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", sync_mock)
    monkeypatch.setattr(scheduler.lark, "with_retry", _passthrough)

    await scheduler._reverse_sync_notes_for_boss(BOSS)

    async with setup_db.execute(
        "SELECT lark_record_id FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-new"
