"""End-to-end test for scripts.migrate_to_internal_id on a synthetic DB.

Builds a small SQLite DB matching the pre-phase-2 schema, runs the migration,
and asserts:
  - row counts preserved per table,
  - external_identity / conversation contain expected mappings,
  - business tables now hold internal_ids (UUIDs),
  - re-running the migration is a no-op.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "migrate_to_internal_id.py"


def _seed(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE bosses (
            chat_id INTEGER PRIMARY KEY, name TEXT NOT NULL, company TEXT DEFAULT '',
            lark_base_token TEXT, lark_table_people TEXT, lark_table_tasks TEXT,
            lark_table_projects TEXT, lark_table_ideas TEXT,
            lark_table_reminders TEXT DEFAULT '', lark_table_notes TEXT DEFAULT '',
            language TEXT DEFAULT 'en', email TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE memberships (
            chat_id TEXT NOT NULL, boss_chat_id TEXT NOT NULL, person_type TEXT NOT NULL,
            name TEXT, lark_record_id TEXT, status TEXT DEFAULT 'pending',
            request_info TEXT, requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP, language TEXT, active_workspace_id TEXT,
            PRIMARY KEY (chat_id, boss_chat_id)
        );
        CREATE TABLE group_map (
            group_chat_id INTEGER PRIMARY KEY, boss_chat_id INTEGER NOT NULL,
            group_name TEXT DEFAULT '', project_id TEXT DEFAULT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
            sender_id INTEGER, role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_messages_chat_created ON messages (chat_id, created_at);
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, boss_chat_id INTEGER NOT NULL,
            type TEXT NOT NULL, ref_id TEXT NOT NULL, content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (boss_chat_id, type, ref_id)
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, boss_chat_id INTEGER NOT NULL,
            target_chat_id INTEGER, target_name TEXT DEFAULT '', content TEXT NOT NULL,
            remind_at TIMESTAMP NOT NULL, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT, boss_chat_id INTEGER NOT NULL,
            source TEXT NOT NULL, prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_token_usage_boss_created ON token_usage (boss_chat_id, created_at);
        CREATE TABLE pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, boss_chat_id TEXT NOT NULL,
            requester_id TEXT NOT NULL, task_record_id TEXT NOT NULL,
            change_type TEXT DEFAULT 'update_task', payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        );
        CREATE TABLE task_notifications (
            task_record_id TEXT NOT NULL, boss_chat_id TEXT NOT NULL,
            assignee_chat_id TEXT, notified_assigned INTEGER DEFAULT 0,
            notified_24h INTEGER DEFAULT 0, notified_2h INTEGER DEFAULT 0,
            notified_overdue INTEGER DEFAULT 0, notified_overdue_at TIMESTAMP,
            PRIMARY KEY (task_record_id, boss_chat_id)
        );
        CREATE TABLE scheduled_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL,
            cron_time TEXT NOT NULL, content_type TEXT NOT NULL, custom_prompt TEXT,
            enabled INTEGER DEFAULT 1, timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, group_chat_id INTEGER DEFAULT NULL
        );
        CREATE TABLE outbound_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, boss_chat_id INTEGER NOT NULL,
            workspace_id TEXT, to_chat_id INTEGER NOT NULL, to_name TEXT,
            content TEXT NOT NULL, trigger_type TEXT DEFAULT 'manual',
            task_id TEXT, project TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_outbound_boss_to ON outbound_messages (boss_chat_id, to_chat_id, created_at DESC);
        CREATE TABLE onboarding_state (
            chat_id INTEGER PRIMARY KEY, state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sessions (
            user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
            expires_at TEXT NOT NULL, PRIMARY KEY (user_id, key)
        );
        CREATE TABLE seen_contacts (
            chat_id INTEGER PRIMARY KEY, display_name TEXT, username TEXT,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_chat INTEGER, seen_count INTEGER DEFAULT 1
        );
        CREATE INDEX idx_seen_contacts_name ON seen_contacts (display_name);
        CREATE INDEX idx_seen_contacts_username ON seen_contacts (username);
        CREATE TABLE people_map (
            chat_id INTEGER PRIMARY KEY, boss_chat_id INTEGER NOT NULL,
            type TEXT NOT NULL, name TEXT DEFAULT ''
        );
    """)
    # Seed data
    conn.executemany(
        "INSERT INTO bosses (chat_id, name) VALUES (?, ?)",
        [(100, "Boss A"), (200, "Boss B")],
    )
    conn.executemany(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) VALUES (?, ?, ?, ?, 'active')",
        [("100", "100", "boss", "Boss A"),
         ("200", "200", "boss", "Boss B"),
         ("300", "100", "member", "Alice"),
         ("400", "100", "partner", "Bob")],
    )
    conn.executemany(
        "INSERT INTO group_map (group_chat_id, boss_chat_id, group_name) VALUES (?, ?, ?)",
        [(-1001, 100, "Project G")],
    )
    conn.executemany(
        "INSERT INTO messages (chat_id, sender_id, role, content) VALUES (?, ?, ?, ?)",
        [(100, 100, "user", "hi"), (100, None, "assistant", "hello"),
         (-1001, 300, "user", "team msg")],
    )
    conn.execute(
        "INSERT INTO reminders (boss_chat_id, target_chat_id, content, remind_at) VALUES (?, ?, ?, '2026-12-31')",
        (100, 300, "ping Alice"),
    )
    conn.execute(
        "INSERT INTO outbound_messages (boss_chat_id, to_chat_id, to_name, content) VALUES (?, ?, ?, ?)",
        (100, 300, "Alice", "deadline reminder"),
    )
    conn.execute(
        "INSERT INTO seen_contacts (chat_id, display_name, last_seen_chat) VALUES (?, ?, ?)",
        (300, "Alice", -1001),
    )
    conn.execute(
        "INSERT INTO notes (boss_chat_id, type, ref_id, content) VALUES (?, 'personal', 'self', 'note A')",
        (100,),
    )
    conn.execute(
        "INSERT INTO token_usage (boss_chat_id, source, total_tokens) VALUES (?, 'agent', 100)",
        (100,),
    )
    conn.commit()
    conn.close()


def test_migration_end_to_end(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Migration committed." in result.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # external_identity has at least the 4 distinct persons (100, 200, 300, 400)
    persons = {r["external_id"] for r in conn.execute(
        "SELECT external_id FROM external_identity WHERE provider = 'telegram'"
    )}
    assert persons >= {"100", "200", "300", "400"}

    convos = {r["external_chat_id"] for r in conn.execute(
        "SELECT external_chat_id FROM conversation WHERE provider = 'telegram'"
    )}
    assert "-1001" in convos
    assert "100" in convos  # boss DM (from messages)

    # bosses now keyed by internal_id (TEXT, length 36 = UUID)
    rows = list(conn.execute("SELECT chat_id, name FROM bosses"))
    assert len(rows) == 2
    for r in rows:
        assert len(r["chat_id"]) == 36, "expected UUID"

    # memberships use internal ids
    for r in conn.execute("SELECT chat_id, boss_chat_id FROM memberships"):
        assert len(r["chat_id"]) == 36
        assert len(r["boss_chat_id"]) == 36

    # messages.chat_id resolves to a conversation row
    cur = conn.execute("""
        SELECT m.chat_id FROM messages m
        LEFT JOIN conversation c ON c.internal_chat_id = m.chat_id
        WHERE c.internal_chat_id IS NULL
    """)
    assert cur.fetchall() == [], "every messages.chat_id must resolve to a conversation"

    # reminders have UUIDs for boss + target
    for r in conn.execute("SELECT boss_chat_id, target_chat_id FROM reminders"):
        assert len(r["boss_chat_id"]) == 36
        assert len(r["target_chat_id"]) == 36

    # outbound_messages
    for r in conn.execute("SELECT boss_chat_id, to_chat_id FROM outbound_messages"):
        assert len(r["boss_chat_id"]) == 36
        assert len(r["to_chat_id"]) == 36

    # seen_contacts: chat_id is internal person id; last_seen_chat is internal conversation id
    for r in conn.execute("SELECT chat_id, last_seen_chat FROM seen_contacts"):
        assert len(r["chat_id"]) == 36
        if r["last_seen_chat"]:
            assert len(r["last_seen_chat"]) == 36

    # people_map dropped
    has_pm = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='people_map'"
    ).fetchone()
    assert has_pm is None

    # Row counts preserved for the seeded tables
    assert conn.execute("SELECT COUNT(*) FROM bosses").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM group_map").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM outbound_messages").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM seen_contacts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 1

    conn.close()

    # Idempotency: re-run is a no-op
    result2 = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        capture_output=True, text=True,
    )
    assert result2.returncode == 0
    assert "Already migrated" in result2.stdout
