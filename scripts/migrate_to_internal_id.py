"""One-shot migration: external chat_ids → internal_id (UUID).

Idempotent. Safe to re-run — exits 0 if already migrated. Wraps everything
in a single transaction; rolls back on any error.

Usage:
    python scripts/migrate_to_internal_id.py [--db data/history.db]
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path

PROVIDER = "telegram"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return str(uuid.uuid4())


def exec_many(conn: sqlite3.Connection, sql: str) -> None:
    """Run multi-statement SQL via execute() so statements participate in
    our manual transaction. `executescript()` issues an implicit COMMIT,
    which would defeat rollback safety."""
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)


def already_migrated(conn: sqlite3.Connection) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='external_identity'"
    )
    if cur.fetchone() is None:
        return False
    cur = conn.execute(
        "SELECT 1 FROM external_identity WHERE provider = ? LIMIT 1", (PROVIDER,)
    )
    return cur.fetchone() is not None


def collect_person_external_ids(conn: sqlite3.Connection) -> set[str]:
    """Every external id that represents a person."""
    ids: set[str] = set()
    for sql in (
        "SELECT chat_id FROM bosses",
        "SELECT chat_id FROM memberships",
        "SELECT boss_chat_id FROM memberships",
        "SELECT boss_chat_id FROM group_map",
        "SELECT chat_id FROM seen_contacts",
        "SELECT DISTINCT sender_id FROM messages WHERE sender_id IS NOT NULL",
    ):
        for (val,) in conn.execute(sql):
            if val is not None and str(val) != "":
                ids.add(str(val))
    # owner_id of scheduled_reviews — also persons
    for (val,) in conn.execute("SELECT DISTINCT owner_id FROM scheduled_reviews"):
        if val is not None and str(val) != "":
            ids.add(str(val))
    # boss/requester in pending_approvals
    for sql in (
        "SELECT DISTINCT boss_chat_id FROM pending_approvals",
        "SELECT DISTINCT requester_id FROM pending_approvals",
    ):
        for (val,) in conn.execute(sql):
            if val is not None and str(val) != "":
                ids.add(str(val))
    # boss/assignee in task_notifications
    for sql in (
        "SELECT DISTINCT boss_chat_id FROM task_notifications",
        "SELECT DISTINCT assignee_chat_id FROM task_notifications WHERE assignee_chat_id IS NOT NULL",
    ):
        for (val,) in conn.execute(sql):
            if val is not None and str(val) != "":
                ids.add(str(val))
    # reminders
    for sql in (
        "SELECT DISTINCT boss_chat_id FROM reminders",
        "SELECT DISTINCT target_chat_id FROM reminders WHERE target_chat_id IS NOT NULL",
    ):
        for (val,) in conn.execute(sql):
            if val is not None and str(val) != "":
                ids.add(str(val))
    # outbound_messages
    for sql in (
        "SELECT DISTINCT boss_chat_id FROM outbound_messages",
        "SELECT DISTINCT to_chat_id FROM outbound_messages",
    ):
        for (val,) in conn.execute(sql):
            if val is not None and str(val) != "":
                ids.add(str(val))
    # notes
    for (val,) in conn.execute("SELECT DISTINCT boss_chat_id FROM notes"):
        if val is not None and str(val) != "":
            ids.add(str(val))
    # token_usage
    for (val,) in conn.execute("SELECT DISTINCT boss_chat_id FROM token_usage"):
        if val is not None and str(val) != "":
            ids.add(str(val))
    # onboarding_state
    for (val,) in conn.execute("SELECT DISTINCT chat_id FROM onboarding_state"):
        if val is not None and str(val) != "":
            ids.add(str(val))
    # sessions
    for (val,) in conn.execute("SELECT DISTINCT user_id FROM sessions"):
        if val is not None and str(val) != "":
            ids.add(str(val))
    return ids


def collect_conversation_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Returns list of (external_chat_id, chat_type, title)."""
    rows: dict[str, tuple[str, str]] = {}
    # Group conversations
    for cid, name in conn.execute("SELECT group_chat_id, group_name FROM group_map"):
        if cid is None:
            continue
        rows[str(cid)] = ("group", name or "")
    # Every distinct messages.chat_id — DM unless it appears in group_map (already added above)
    for (cid,) in conn.execute("SELECT DISTINCT chat_id FROM messages"):
        if cid is None:
            continue
        s = str(cid)
        rows.setdefault(s, ("dm", ""))
    # outbound_messages.to_chat_id — also DMs
    for (cid,) in conn.execute("SELECT DISTINCT to_chat_id FROM outbound_messages"):
        if cid is None:
            continue
        s = str(cid)
        rows.setdefault(s, ("dm", ""))
    # scheduled_reviews.group_chat_id — groups (when not null)
    for (cid,) in conn.execute(
        "SELECT DISTINCT group_chat_id FROM scheduled_reviews WHERE group_chat_id IS NOT NULL"
    ):
        s = str(cid)
        rows.setdefault(s, ("group", ""))
    # seen_contacts.last_seen_chat — classify by Telegram sign convention:
    # negative chat_id = (super)group, positive = DM. Only used as a fallback
    # when this id wasn't already classified via group_map / messages / etc.
    for (cid,) in conn.execute(
        "SELECT DISTINCT last_seen_chat FROM seen_contacts WHERE last_seen_chat IS NOT NULL"
    ):
        s = str(cid)
        if s in rows:
            continue
        try:
            chat_type = "group" if int(s) < 0 else "dm"
        except (TypeError, ValueError):
            chat_type = "dm"
        rows[s] = (chat_type, "")
    return [(eid, ct, title) for eid, (ct, title) in rows.items()]


def insert_mappings(conn: sqlite3.Connection) -> dict:
    """Build mapping rows for both tables. Returns counts."""
    person_ids = collect_person_external_ids(conn)
    convo_rows = collect_conversation_rows(conn)

    now = _now_ms()

    for ext in sorted(person_ids):
        conn.execute(
            """INSERT OR IGNORE INTO external_identity
               (internal_id, provider, external_id, name, username, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_new_id(), PROVIDER, ext, "", "", now),
        )

    for ext, ct, title in sorted(convo_rows):
        conn.execute(
            """INSERT OR IGNORE INTO conversation
               (internal_chat_id, provider, external_chat_id, chat_type, title, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_new_id(), PROVIDER, ext, ct, title, now),
        )

    # Backfill display names from existing tables (best-effort).
    for chat_id, name in conn.execute("SELECT chat_id, name FROM bosses"):
        conn.execute(
            "UPDATE external_identity SET name = ? WHERE provider = 'telegram' AND external_id = ? AND (name IS NULL OR name = '')",
            (name or "", str(chat_id)),
        )
    for chat_id, name in conn.execute("SELECT chat_id, name FROM memberships"):
        if name:
            conn.execute(
                "UPDATE external_identity SET name = ? WHERE provider = 'telegram' AND external_id = ? AND (name IS NULL OR name = '')",
                (name, str(chat_id)),
            )
    for chat_id, dn, un in conn.execute("SELECT chat_id, display_name, username FROM seen_contacts"):
        if dn:
            conn.execute(
                "UPDATE external_identity SET name = ? WHERE provider = 'telegram' AND external_id = ? AND (name IS NULL OR name = '')",
                (dn, str(chat_id)),
            )
        if un:
            conn.execute(
                "UPDATE external_identity SET username = ? WHERE provider = 'telegram' AND external_id = ? AND (username IS NULL OR username = '')",
                (un, str(chat_id)),
            )
    for cid, name in conn.execute("SELECT group_chat_id, group_name FROM group_map"):
        if name:
            conn.execute(
                "UPDATE conversation SET title = ? WHERE provider = 'telegram' AND external_chat_id = ? AND (title IS NULL OR title = '')",
                (name, str(cid)),
            )

    return {"persons": len(person_ids), "conversations": len(convo_rows)}


def rebuild_business_tables(conn: sqlite3.Connection) -> None:
    """Rebuild every business table using copy-pattern to swap external ids → internal ids."""

    # ----- bosses -----
    exec_many(conn, """
        CREATE TABLE bosses_new (
            chat_id              TEXT PRIMARY KEY,
            name                 TEXT NOT NULL,
            company              TEXT DEFAULT '',
            lark_base_token      TEXT,
            lark_table_people    TEXT,
            lark_table_tasks     TEXT,
            lark_table_projects  TEXT,
            lark_table_ideas     TEXT,
            lark_table_reminders TEXT DEFAULT '',
            lark_table_notes     TEXT DEFAULT '',
            language             TEXT DEFAULT 'en',
            email                TEXT DEFAULT '',
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO bosses_new
            (chat_id, name, company, lark_base_token, lark_table_people,
             lark_table_tasks, lark_table_projects, lark_table_ideas,
             lark_table_reminders, lark_table_notes, language, email, created_at)
        SELECT
            ei.internal_id,
            b.name, b.company, b.lark_base_token, b.lark_table_people,
            b.lark_table_tasks, b.lark_table_projects, b.lark_table_ideas,
            b.lark_table_reminders, b.lark_table_notes, b.language, b.email, b.created_at
        FROM bosses b
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(b.chat_id AS TEXT);
        DROP TABLE bosses;
        ALTER TABLE bosses_new RENAME TO bosses;
    """)

    # ----- memberships -----
    exec_many(conn, """
        CREATE TABLE memberships_new (
            chat_id             TEXT NOT NULL,
            boss_chat_id        TEXT NOT NULL,
            person_type         TEXT NOT NULL,
            name                TEXT,
            lark_record_id      TEXT,
            status              TEXT DEFAULT 'pending',
            request_info        TEXT,
            requested_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at         TIMESTAMP,
            language            TEXT DEFAULT NULL,
            active_workspace_id TEXT DEFAULT NULL,
            PRIMARY KEY (chat_id, boss_chat_id)
        );
        INSERT INTO memberships_new
            (chat_id, boss_chat_id, person_type, name, lark_record_id, status,
             request_info, requested_at, approved_at, language, active_workspace_id)
        SELECT
            ei_p.internal_id,
            ei_b.internal_id,
            m.person_type, m.name, m.lark_record_id, m.status,
            m.request_info, m.requested_at, m.approved_at, m.language, m.active_workspace_id
        FROM memberships m
        JOIN external_identity ei_p
          ON ei_p.provider = 'telegram' AND ei_p.external_id = m.chat_id
        JOIN external_identity ei_b
          ON ei_b.provider = 'telegram' AND ei_b.external_id = m.boss_chat_id;
        DROP TABLE memberships;
        ALTER TABLE memberships_new RENAME TO memberships;
    """)

    # ----- group_map -----
    exec_many(conn, """
        CREATE TABLE group_map_new (
            group_chat_id  TEXT PRIMARY KEY,
            boss_chat_id   TEXT NOT NULL,
            group_name     TEXT DEFAULT '',
            project_id     TEXT DEFAULT NULL
        );
        INSERT INTO group_map_new
            (group_chat_id, boss_chat_id, group_name, project_id)
        SELECT
            c.internal_chat_id,
            ei.internal_id,
            g.group_name, g.project_id
        FROM group_map g
        JOIN conversation c
          ON c.provider = 'telegram' AND c.external_chat_id = CAST(g.group_chat_id AS TEXT)
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(g.boss_chat_id AS TEXT);
        DROP TABLE group_map;
        ALTER TABLE group_map_new RENAME TO group_map;
    """)

    # ----- messages -----
    exec_many(conn, """
        CREATE TABLE messages_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    TEXT NOT NULL,
            sender_id  TEXT,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO messages_new (id, chat_id, sender_id, role, content, created_at)
        SELECT
            m.id,
            c.internal_chat_id,
            ei.internal_id,
            m.role, m.content, m.created_at
        FROM messages m
        JOIN conversation c
          ON c.provider = 'telegram' AND c.external_chat_id = CAST(m.chat_id AS TEXT)
        LEFT JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(m.sender_id AS TEXT);
        DROP INDEX IF EXISTS idx_messages_chat_created;
        DROP TABLE messages;
        ALTER TABLE messages_new RENAME TO messages;
        CREATE INDEX idx_messages_chat_created ON messages (chat_id, created_at);
    """)

    # ----- notes -----
    exec_many(conn, """
        CREATE TABLE notes_new (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id TEXT NOT NULL,
            type         TEXT NOT NULL CHECK (type IN ('personal', 'project', 'group')),
            ref_id       TEXT NOT NULL,
            content      TEXT NOT NULL,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (boss_chat_id, type, ref_id)
        );
        INSERT INTO notes_new (id, boss_chat_id, type, ref_id, content, updated_at)
        SELECT n.id, ei.internal_id, n.type, n.ref_id, n.content, n.updated_at
        FROM notes n
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(n.boss_chat_id AS TEXT);
        DROP TABLE notes;
        ALTER TABLE notes_new RENAME TO notes;
    """)

    # ----- reminders -----
    exec_many(conn, """
        CREATE TABLE reminders_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id    TEXT NOT NULL,
            target_chat_id  TEXT,
            target_name     TEXT DEFAULT '',
            content         TEXT NOT NULL,
            remind_at       TIMESTAMP NOT NULL,
            status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO reminders_new
            (id, boss_chat_id, target_chat_id, target_name, content, remind_at, status, created_at)
        SELECT
            r.id,
            ei_b.internal_id,
            ei_t.internal_id,
            r.target_name, r.content, r.remind_at, r.status, r.created_at
        FROM reminders r
        JOIN external_identity ei_b
          ON ei_b.provider = 'telegram' AND ei_b.external_id = CAST(r.boss_chat_id AS TEXT)
        LEFT JOIN external_identity ei_t
          ON ei_t.provider = 'telegram' AND ei_t.external_id = CAST(r.target_chat_id AS TEXT);
        DROP TABLE reminders;
        ALTER TABLE reminders_new RENAME TO reminders;
    """)

    # ----- token_usage -----
    exec_many(conn, """
        CREATE TABLE token_usage_new (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id      TEXT NOT NULL,
            source            TEXT NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO token_usage_new
            (id, boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens, created_at)
        SELECT t.id, ei.internal_id, t.source, t.prompt_tokens, t.completion_tokens, t.total_tokens, t.created_at
        FROM token_usage t
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(t.boss_chat_id AS TEXT);
        DROP INDEX IF EXISTS idx_token_usage_boss_created;
        DROP TABLE token_usage;
        ALTER TABLE token_usage_new RENAME TO token_usage;
        CREATE INDEX idx_token_usage_boss_created ON token_usage (boss_chat_id, created_at);
    """)

    # ----- pending_approvals -----
    exec_many(conn, """
        CREATE TABLE pending_approvals_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id    TEXT NOT NULL,
            requester_id    TEXT NOT NULL,
            task_record_id  TEXT NOT NULL,
            change_type     TEXT DEFAULT 'update_task',
            payload         TEXT NOT NULL,
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at      TIMESTAMP
        );
        INSERT INTO pending_approvals_new
            (id, boss_chat_id, requester_id, task_record_id, change_type, payload, status, created_at, expires_at)
        SELECT
            p.id,
            ei_b.internal_id,
            ei_r.internal_id,
            p.task_record_id, p.change_type, p.payload, p.status, p.created_at, p.expires_at
        FROM pending_approvals p
        JOIN external_identity ei_b
          ON ei_b.provider = 'telegram' AND ei_b.external_id = p.boss_chat_id
        JOIN external_identity ei_r
          ON ei_r.provider = 'telegram' AND ei_r.external_id = p.requester_id;
        DROP TABLE pending_approvals;
        ALTER TABLE pending_approvals_new RENAME TO pending_approvals;
    """)

    # ----- task_notifications -----
    exec_many(conn, """
        CREATE TABLE task_notifications_new (
            task_record_id      TEXT NOT NULL,
            boss_chat_id        TEXT NOT NULL,
            assignee_chat_id    TEXT,
            notified_assigned   INTEGER DEFAULT 0,
            notified_24h        INTEGER DEFAULT 0,
            notified_2h         INTEGER DEFAULT 0,
            notified_overdue    INTEGER DEFAULT 0,
            notified_overdue_at TIMESTAMP,
            PRIMARY KEY (task_record_id, boss_chat_id)
        );
        INSERT INTO task_notifications_new
            (task_record_id, boss_chat_id, assignee_chat_id,
             notified_assigned, notified_24h, notified_2h,
             notified_overdue, notified_overdue_at)
        SELECT
            t.task_record_id,
            ei_b.internal_id,
            ei_a.internal_id,
            t.notified_assigned, t.notified_24h, t.notified_2h,
            t.notified_overdue, t.notified_overdue_at
        FROM task_notifications t
        JOIN external_identity ei_b
          ON ei_b.provider = 'telegram' AND ei_b.external_id = t.boss_chat_id
        LEFT JOIN external_identity ei_a
          ON ei_a.provider = 'telegram' AND ei_a.external_id = t.assignee_chat_id;
        DROP TABLE task_notifications;
        ALTER TABLE task_notifications_new RENAME TO task_notifications;
    """)

    # ----- scheduled_reviews -----
    exec_many(conn, """
        CREATE TABLE scheduled_reviews_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id      TEXT NOT NULL,
            cron_time     TEXT NOT NULL,
            content_type  TEXT NOT NULL,
            custom_prompt TEXT,
            enabled       INTEGER DEFAULT 1,
            timezone      TEXT DEFAULT 'Asia/Ho_Chi_Minh',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            group_chat_id TEXT DEFAULT NULL
        );
        INSERT INTO scheduled_reviews_new
            (id, owner_id, cron_time, content_type, custom_prompt, enabled, timezone, created_at, group_chat_id)
        SELECT
            s.id,
            ei.internal_id,
            s.cron_time, s.content_type, s.custom_prompt, s.enabled, s.timezone, s.created_at,
            c.internal_chat_id
        FROM scheduled_reviews s
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = s.owner_id
        LEFT JOIN conversation c
          ON c.provider = 'telegram' AND c.external_chat_id = CAST(s.group_chat_id AS TEXT);
        DROP TABLE scheduled_reviews;
        ALTER TABLE scheduled_reviews_new RENAME TO scheduled_reviews;
    """)

    # ----- outbound_messages -----
    exec_many(conn, """
        CREATE TABLE outbound_messages_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id  TEXT NOT NULL,
            workspace_id  TEXT,
            to_chat_id    TEXT NOT NULL,
            to_name       TEXT,
            content       TEXT NOT NULL,
            trigger_type  TEXT DEFAULT 'manual',
            task_id       TEXT,
            project       TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO outbound_messages_new
            (id, boss_chat_id, workspace_id, to_chat_id, to_name, content,
             trigger_type, task_id, project, created_at)
        SELECT
            o.id,
            ei_b.internal_id,
            o.workspace_id,
            ei_t.internal_id,
            o.to_name, o.content, o.trigger_type, o.task_id, o.project, o.created_at
        FROM outbound_messages o
        JOIN external_identity ei_b
          ON ei_b.provider = 'telegram' AND ei_b.external_id = CAST(o.boss_chat_id AS TEXT)
        JOIN external_identity ei_t
          ON ei_t.provider = 'telegram' AND ei_t.external_id = CAST(o.to_chat_id AS TEXT);
        DROP INDEX IF EXISTS idx_outbound_boss_to;
        DROP TABLE outbound_messages;
        ALTER TABLE outbound_messages_new RENAME TO outbound_messages;
        CREATE INDEX idx_outbound_boss_to ON outbound_messages (boss_chat_id, to_chat_id, created_at DESC);
    """)

    # ----- onboarding_state -----
    exec_many(conn, """
        CREATE TABLE onboarding_state_new (
            chat_id    TEXT PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO onboarding_state_new (chat_id, state_json, updated_at)
        SELECT ei.internal_id, o.state_json, o.updated_at
        FROM onboarding_state o
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(o.chat_id AS TEXT);
        DROP TABLE onboarding_state;
        ALTER TABLE onboarding_state_new RENAME TO onboarding_state;
    """)

    # ----- sessions -----
    exec_many(conn, """
        CREATE TABLE sessions_new (
            user_id     TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        INSERT INTO sessions_new (user_id, key, value, expires_at)
        SELECT ei.internal_id, s.key, s.value, s.expires_at
        FROM sessions s
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(s.user_id AS TEXT);
        DROP TABLE sessions;
        ALTER TABLE sessions_new RENAME TO sessions;
    """)

    # ----- seen_contacts -----
    exec_many(conn, """
        CREATE TABLE seen_contacts_new (
            chat_id          TEXT PRIMARY KEY,
            display_name     TEXT,
            username         TEXT,
            first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_chat   TEXT,
            seen_count       INTEGER DEFAULT 1
        );
        INSERT INTO seen_contacts_new
            (chat_id, display_name, username, first_seen_at, last_seen_at, last_seen_chat, seen_count)
        SELECT
            ei.internal_id, s.display_name, s.username, s.first_seen_at, s.last_seen_at,
            c.internal_chat_id, s.seen_count
        FROM seen_contacts s
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(s.chat_id AS TEXT)
        LEFT JOIN conversation c
          ON c.provider = 'telegram' AND c.external_chat_id = CAST(s.last_seen_chat AS TEXT);
        DROP INDEX IF EXISTS idx_seen_contacts_name;
        DROP INDEX IF EXISTS idx_seen_contacts_username;
        DROP TABLE seen_contacts;
        ALTER TABLE seen_contacts_new RENAME TO seen_contacts;
        CREATE INDEX idx_seen_contacts_name ON seen_contacts (display_name);
        CREATE INDEX idx_seen_contacts_username ON seen_contacts (username);
    """)

    # ----- people_map: drop legacy -----
    conn.execute("DROP TABLE IF EXISTS people_map")


# Tables that must preserve row count across migration. Maps logical name to
# (pre-count-snapshot SQL, post-count SQL). Snapshots are taken before rebuild.
_COUNT_TABLES = (
    "bosses", "memberships", "group_map", "messages", "notes",
    "reminders", "token_usage", "pending_approvals", "task_notifications",
    "scheduled_reviews", "outbound_messages", "onboarding_state",
    "sessions", "seen_contacts",
)


def snapshot_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in _COUNT_TABLES
    }


def assert_counts_unchanged(conn: sqlite3.Connection, before: dict[str, int]) -> None:
    """Raise if any rebuilt table dropped or gained rows. Detects silent FK-resolve failures."""
    after = snapshot_counts(conn)
    diffs = {t: (before[t], after[t]) for t in _COUNT_TABLES if before[t] != after[t]}
    if diffs:
        details = ", ".join(f"{t}: {b}->{a}" for t, (b, a) in diffs.items())
        raise RuntimeError(f"Row counts changed during rebuild: {details}")


def assert_fk_resolves(conn: sqlite3.Connection) -> None:
    """Verify every FK column in rebuilt tables resolves to a mapping row.
    Catches silent NULL-via-LEFT-JOIN bugs and CAST mismatches."""
    checks = (
        ("bosses.chat_id",
         "SELECT COUNT(*) FROM bosses b LEFT JOIN external_identity ei ON ei.internal_id = b.chat_id WHERE ei.internal_id IS NULL"),
        ("memberships.chat_id",
         "SELECT COUNT(*) FROM memberships m LEFT JOIN external_identity ei ON ei.internal_id = m.chat_id WHERE ei.internal_id IS NULL"),
        ("memberships.boss_chat_id",
         "SELECT COUNT(*) FROM memberships m LEFT JOIN external_identity ei ON ei.internal_id = m.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("group_map.group_chat_id",
         "SELECT COUNT(*) FROM group_map g LEFT JOIN conversation c ON c.internal_chat_id = g.group_chat_id WHERE c.internal_chat_id IS NULL"),
        ("group_map.boss_chat_id",
         "SELECT COUNT(*) FROM group_map g LEFT JOIN external_identity ei ON ei.internal_id = g.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("messages.chat_id",
         "SELECT COUNT(*) FROM messages m LEFT JOIN conversation c ON c.internal_chat_id = m.chat_id WHERE c.internal_chat_id IS NULL"),
        ("messages.sender_id (non-null)",
         "SELECT COUNT(*) FROM messages m LEFT JOIN external_identity ei ON ei.internal_id = m.sender_id WHERE m.sender_id IS NOT NULL AND ei.internal_id IS NULL"),
        ("notes.boss_chat_id",
         "SELECT COUNT(*) FROM notes n LEFT JOIN external_identity ei ON ei.internal_id = n.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("reminders.boss_chat_id",
         "SELECT COUNT(*) FROM reminders r LEFT JOIN external_identity ei ON ei.internal_id = r.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("reminders.target_chat_id (non-null)",
         "SELECT COUNT(*) FROM reminders r LEFT JOIN external_identity ei ON ei.internal_id = r.target_chat_id WHERE r.target_chat_id IS NOT NULL AND ei.internal_id IS NULL"),
        ("token_usage.boss_chat_id",
         "SELECT COUNT(*) FROM token_usage t LEFT JOIN external_identity ei ON ei.internal_id = t.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("pending_approvals.boss_chat_id",
         "SELECT COUNT(*) FROM pending_approvals p LEFT JOIN external_identity ei ON ei.internal_id = p.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("pending_approvals.requester_id",
         "SELECT COUNT(*) FROM pending_approvals p LEFT JOIN external_identity ei ON ei.internal_id = p.requester_id WHERE ei.internal_id IS NULL"),
        ("task_notifications.boss_chat_id",
         "SELECT COUNT(*) FROM task_notifications tn LEFT JOIN external_identity ei ON ei.internal_id = tn.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("task_notifications.assignee_chat_id (non-null)",
         "SELECT COUNT(*) FROM task_notifications tn LEFT JOIN external_identity ei ON ei.internal_id = tn.assignee_chat_id WHERE tn.assignee_chat_id IS NOT NULL AND ei.internal_id IS NULL"),
        ("scheduled_reviews.owner_id",
         "SELECT COUNT(*) FROM scheduled_reviews s LEFT JOIN external_identity ei ON ei.internal_id = s.owner_id WHERE ei.internal_id IS NULL"),
        ("scheduled_reviews.group_chat_id (non-null)",
         "SELECT COUNT(*) FROM scheduled_reviews s LEFT JOIN conversation c ON c.internal_chat_id = s.group_chat_id WHERE s.group_chat_id IS NOT NULL AND c.internal_chat_id IS NULL"),
        ("outbound_messages.boss_chat_id",
         "SELECT COUNT(*) FROM outbound_messages o LEFT JOIN external_identity ei ON ei.internal_id = o.boss_chat_id WHERE ei.internal_id IS NULL"),
        ("outbound_messages.to_chat_id",
         "SELECT COUNT(*) FROM outbound_messages o LEFT JOIN external_identity ei ON ei.internal_id = o.to_chat_id WHERE ei.internal_id IS NULL"),
        ("onboarding_state.chat_id",
         "SELECT COUNT(*) FROM onboarding_state o LEFT JOIN external_identity ei ON ei.internal_id = o.chat_id WHERE ei.internal_id IS NULL"),
        ("sessions.user_id",
         "SELECT COUNT(*) FROM sessions s LEFT JOIN external_identity ei ON ei.internal_id = s.user_id WHERE ei.internal_id IS NULL"),
        ("seen_contacts.chat_id",
         "SELECT COUNT(*) FROM seen_contacts sc LEFT JOIN external_identity ei ON ei.internal_id = sc.chat_id WHERE ei.internal_id IS NULL"),
        ("seen_contacts.last_seen_chat (non-null)",
         "SELECT COUNT(*) FROM seen_contacts sc LEFT JOIN conversation c ON c.internal_chat_id = sc.last_seen_chat WHERE sc.last_seen_chat IS NOT NULL AND c.internal_chat_id IS NULL"),
    )
    failures: list[str] = []
    for label, sql in checks:
        n = conn.execute(sql).fetchone()[0]
        if n:
            failures.append(f"{label}: {n} unresolved row(s)")
    if failures:
        raise RuntimeError("FK resolution failed: " + "; ".join(failures))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/history.db")
    args = p.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    backup_path = db_path.with_suffix(db_path.suffix + ".pre-phase2.bak")
    if not backup_path.exists():
        shutil.copy2(db_path, backup_path)
        print(f"Backup written: {backup_path}")
    else:
        print(f"Backup already exists, skipping: {backup_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # autocommit off, manual transaction control. Default LEGACY_TRANSACTION_CONTROL
    # would auto-commit on DDL, defeating rollback. isolation_level = None gives
    # us "no implicit BEGIN" so we drive the transaction explicitly.
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")
    # PRAGMA must run outside the transaction; subsequent BEGIN starts the txn.

    if already_migrated(conn):
        print("Already migrated — exiting 0.")
        conn.close()
        return 0

    try:
        conn.execute("BEGIN")
        # Tables external_identity / conversation must already exist (added by db._init_schema).
        # If running migration on a fresh DB from sqlite3 directly (no app boot), create now.
        exec_many(conn, """
            CREATE TABLE IF NOT EXISTS external_identity (
                internal_id   TEXT PRIMARY KEY,
                provider      TEXT NOT NULL,
                external_id   TEXT NOT NULL,
                name          TEXT DEFAULT '',
                username      TEXT DEFAULT '',
                created_at    INTEGER NOT NULL,
                UNIQUE(provider, external_id)
            );
            CREATE TABLE IF NOT EXISTS conversation (
                internal_chat_id  TEXT PRIMARY KEY,
                provider          TEXT NOT NULL,
                external_chat_id  TEXT NOT NULL,
                chat_type         TEXT NOT NULL,
                title             TEXT DEFAULT '',
                created_at        INTEGER NOT NULL,
                UNIQUE(provider, external_chat_id)
            );
        """)

        counts = insert_mappings(conn)
        print(f"Mapped {counts['persons']} persons and {counts['conversations']} conversations.")

        # Snapshot row counts before destructive rebuild so we can detect
        # silent FK-resolve failures (LEFT JOIN dropping rows on CAST mismatch).
        pre_counts = snapshot_counts(conn)

        rebuild_business_tables(conn)

        assert_counts_unchanged(conn, pre_counts)
        assert_fk_resolves(conn)

        conn.execute("COMMIT")
        print("Migration committed.")
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        print(f"Migration failed, rolled back: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
