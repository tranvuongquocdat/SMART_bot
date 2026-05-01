"""Verify Phase 3 forward-compat schema additions on a fresh DB and on a
post-Phase-2 DB (existing bosses row is upgraded, no data lost)."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path


def _columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        conn.close()
    return {r[1] for r in rows}


def _table_exists(db_path: Path, table: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    finally:
        conn.close()
    return row is not None


PHASE3_BOSS_COLUMNS = {
    "status", "plan", "expires_at",
    "llm_provider", "llm_model", "llm_api_key_encrypted",
    "embedding_provider", "embedding_model", "embedding_dim",
}


def test_fresh_install_has_phase3_columns(tmp_path):
    """A fresh DB built via _init_schema must have all Phase 3 boss columns + audit_log."""
    db_path = tmp_path / "fresh.db"

    async def _run():
        from src.db import get_db, close_db
        await close_db()  # reset stale singleton from prior tests
        await get_db(str(db_path))
        await close_db()

    asyncio.run(_run())

    cols = _columns(db_path, "bosses")
    missing = PHASE3_BOSS_COLUMNS - cols
    assert not missing, f"bosses missing columns: {missing}"
    assert _table_exists(db_path, "audit_log")


def test_existing_db_gets_columns_added(tmp_path):
    """Simulate a post-Phase-2 DB: bosses without Phase 3 columns. Run get_db
    and assert the additive migration ran without dropping data."""
    db_path = tmp_path / "post_phase2.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE bosses (
            chat_id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT DEFAULT '',
            lark_base_token TEXT, lark_table_people TEXT, lark_table_tasks TEXT,
            lark_table_projects TEXT, lark_table_ideas TEXT,
            lark_table_reminders TEXT DEFAULT '', lark_table_notes TEXT DEFAULT '',
            language TEXT DEFAULT 'en', email TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO bosses (chat_id, name) VALUES ('uuid-1', 'Boss A');
    """)
    conn.commit()
    conn.close()

    async def _run():
        from src.db import get_db, close_db
        await close_db()  # reset stale singleton from prior tests
        await get_db(str(db_path))
        await close_db()

    asyncio.run(_run())

    cols = _columns(db_path, "bosses")
    missing = PHASE3_BOSS_COLUMNS - cols
    assert not missing, f"bosses missing columns: {missing}"
    assert _table_exists(db_path, "audit_log")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT chat_id, name, status FROM bosses").fetchone()
        assert row == ("uuid-1", "Boss A", "active")
    finally:
        conn.close()
