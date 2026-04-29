# Phase 2 — Schema Migration to Internal ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce synthetic `internal_id` (UUID) for persons and conversations. Add `external_identity` and `conversation` mapping tables. Rebuild every business table so primary/foreign keys are TEXT internal ids. Update `db.py` functions and the Telegram channel adapter to operate on internal ids. Existing function-style API in `db.py` is preserved (Phase 3 splits into repos).

**Architecture:** Two new mapping tables hold the (provider, external_id) → internal_id mapping. The Telegram channel adapter is the single point that converts external → internal on inbound; everything downstream (agent, tools, db) sees only internal ids. A one-shot migration script (`scripts/migrate_to_internal_id.py`) generates UUIDs for existing rows and rebuilds every business table via SQLite copy-pattern. After Phase 2 the bot still works end-to-end on Telegram with the new schema.

**Tech Stack:** Python 3.11+, aiosqlite, sqlite3, uuid (stdlib), pytest.

**Spec reference:** [docs/superpowers/specs/2026-04-28-platform-channel-and-layered-architecture-design.md](../specs/2026-04-28-platform-channel-and-layered-architecture-design.md), Phase 2.

---

## Scope Notes

**In scope:**

- Add `external_identity` and `conversation` tables (idempotent `CREATE IF NOT EXISTS`).
- Backfill mapping rows for every existing person (boss, member, partner, harvested seen_contact) and every existing conversation (DM + group).
- Rebuild **every** business table so any column that today holds an external `chat_id` (whether `INTEGER` or stringified `TEXT`) becomes a `TEXT internal_id` referencing the new mapping tables.
- Update `db.py` schema definition + every function signature: `chat_id: int` → `chat_id: str` (now interpreted as internal_id). Variable name **stays** `chat_id` — semantic rename to `internal_id` happens in Phase 3 when we split into repos.
- Update `src/channels/telegram.py` to call `_resolve_internal_chat_id` + `_resolve_internal_sender_id` before constructing the `IncomingMessage` dispatched downstream. The provider-native external ids stay on `IncomingMessage.raw` for the harvester.
- Strip every `int(chat_id)` cast in non-channel code (channel still casts when calling Telegram API because Telegram requires int).
- Drop the legacy `people_map` table (already migrated to `memberships` by an earlier additive migration; keeping it dual-write is the only thing forcing a non-text schema).

**Out of scope (deferred to later phases):**

- Splitting `db.py` into per-aggregate repositories — Phase 3.
- Service layer / handler classes / tool dispatcher — Phase 4.
- `MessageRouter` / `AppContainer` — Phase 5. Phase 2 lookup logic is **temporarily** inside `channels/telegram.py`; Phase 5 moves it to `MessageRouter` and reverts the channel to be platform-only.
- Multiple providers — Phase 6. Mapping rows in this phase carry `provider='telegram'` for every backfilled record.

**Why no automated tests for repo/migration logic:** existing `tests/` will not survive the refactor (per spec). New tests against repos arrive in Phase 3, against services in Phase 4. Phase 2 verification is the smoke checklist + a focused unit test for the **migration script** itself (replayed on a synthetic SQLite fixture).

---

## File Structure After This Phase

```
src/
├── db.py                        # MODIFIED — schema + functions take internal_id (TEXT)
├── channels/
│   └── telegram.py              # MODIFIED — looks up internal ids on inbound
└── identity.py                  # MODIFIED — chat_id passed in + persisted as TEXT internal_id

scripts/
└── migrate_to_internal_id.py    # NEW — one-shot, idempotent migration

tests/
└── unit/
    └── test_migrate_to_internal_id.py   # NEW — runs migration on synthetic db
```

---

## Migration Strategy (Read Before Coding)

Each existing **external person** (boss, every distinct member chat_id, every harvested seen_contact) gets one fresh UUID. Each existing **external conversation** (every distinct chat_id seen in messages, every group_map row, every DM) gets one fresh UUID. The mapping tables are populated atomically; then every business table is rebuilt by `INSERT INTO new SELECT … JOIN external_identity / conversation` so foreign keys point at the new internal ids.

Tables to rebuild (column → translation):

| Table | Column(s) carrying external id | Becomes |
|---|---|---|
| `bosses` | `chat_id INTEGER PK` | `chat_id TEXT PK` (internal_id of the boss person) |
| `group_map` | `group_chat_id INTEGER PK`, `boss_chat_id INTEGER FK` | both `TEXT` (internal ids) |
| `messages` | `chat_id INTEGER`, `sender_id INTEGER` | both `TEXT` (internal_chat_id, internal sender id) |
| `notes` | `boss_chat_id INTEGER FK` | `TEXT` (internal id) |
| `reminders` | `boss_chat_id INTEGER`, `target_chat_id INTEGER` | both `TEXT` |
| `token_usage` | `boss_chat_id INTEGER` | `TEXT` |
| `memberships` | `chat_id TEXT` (currently external), `boss_chat_id TEXT` (currently external) | both reinterpreted as internal ids; **values rewritten** by the migration |
| `pending_approvals` | `boss_chat_id TEXT`, `requester_id TEXT` | both reinterpreted as internal ids; values rewritten |
| `task_notifications` | `boss_chat_id TEXT`, `assignee_chat_id TEXT` | both reinterpreted; values rewritten |
| `scheduled_reviews` | `owner_id TEXT`, `group_chat_id INTEGER` | both reinterpreted as internal ids; values rewritten |
| `outbound_messages` | `boss_chat_id INTEGER`, `to_chat_id INTEGER` | both `TEXT` |
| `onboarding_state` | `chat_id INTEGER PK` | `TEXT` |
| `sessions` | `user_id INTEGER` | `TEXT` |
| `seen_contacts` | `chat_id INTEGER PK`, `last_seen_chat INTEGER` | `chat_id TEXT` (internal id of the harvested person), `last_seen_chat TEXT` (internal id of the conversation it was seen in) |
| `people_map` | (legacy) | **DROPPED** — superseded by `memberships` since the previous additive migration |

Idempotency: the migration script first checks whether `external_identity` exists **and** has at least one row whose `provider='telegram'`. If so, it logs "already migrated" and exits 0. The migration runs inside a single transaction (`BEGIN; … COMMIT;`); if any statement fails, the DB is rolled back and the original tables remain untouched.

**Backup before running:** the script copies `data/history.db` → `data/history.db.pre-phase2.bak` as its first step. Restore by `cp` if anything goes wrong.

---

## Task 1 — Backup and inspect the live database

**Files:** None. Pure inspection.

- [ ] **Step 1: Take a manual backup of the production DB**

```bash
cp data/history.db data/history.db.manual-backup-$(date +%Y%m%d-%H%M%S)
ls -lh data/*.db*
```

Expected: a `.manual-backup-YYYYMMDD-HHMMSS` file appears next to `history.db`.

- [ ] **Step 2: Inspect current row counts**

```bash
sqlite3 data/history.db <<'SQL'
.headers on
.mode column
SELECT 'bosses' AS table_name, COUNT(*) AS rows FROM bosses
UNION ALL SELECT 'memberships', COUNT(*) FROM memberships
UNION ALL SELECT 'group_map', COUNT(*) FROM group_map
UNION ALL SELECT 'messages', COUNT(*) FROM messages
UNION ALL SELECT 'reminders', COUNT(*) FROM reminders
UNION ALL SELECT 'notes', COUNT(*) FROM notes
UNION ALL SELECT 'seen_contacts', COUNT(*) FROM seen_contacts
UNION ALL SELECT 'outbound_messages', COUNT(*) FROM outbound_messages
UNION ALL SELECT 'onboarding_state', COUNT(*) FROM onboarding_state;
SQL
```

Record the output in your notes. After migration these counts must be **identical** in the rebuilt tables.

- [ ] **Step 3: List distinct external chat_ids that will be mapped**

```bash
sqlite3 data/history.db <<'SQL'
SELECT 'bosses' AS src, chat_id FROM bosses
UNION SELECT 'memberships', chat_id FROM memberships
UNION SELECT 'group_map', group_chat_id FROM group_map
UNION SELECT 'group_map_boss', boss_chat_id FROM group_map
UNION SELECT 'seen_contacts', chat_id FROM seen_contacts
UNION SELECT 'messages_chat', DISTINCT chat_id FROM messages
UNION SELECT 'messages_sender', DISTINCT sender_id FROM messages WHERE sender_id IS NOT NULL;
SQL
```

You should see every external id that will need a mapping. No commit.

---

## Task 2 — Add `external_identity` and `conversation` tables to schema

**Files:**
- Modify: `src/db.py` — add table definitions inside `_init_schema` (so fresh installs get them) and inside `_migrate_schema` (so existing DBs get them via additive migration).

- [ ] **Step 1: Add the table DDL inside `_init_schema`**

Open `src/db.py`. Inside `_init_schema`, **after** the existing `CREATE TABLE IF NOT EXISTS scheduled_reviews` block but **before** the call to `_migrate_schema`, insert:

```python
    await db.execute("""
        CREATE TABLE IF NOT EXISTS external_identity (
            internal_id   TEXT PRIMARY KEY,
            provider      TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            name          TEXT DEFAULT '',
            username      TEXT DEFAULT '',
            created_at    INTEGER NOT NULL,
            UNIQUE(provider, external_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS conversation (
            internal_chat_id  TEXT PRIMARY KEY,
            provider          TEXT NOT NULL,
            external_chat_id  TEXT NOT NULL,
            chat_type         TEXT NOT NULL,
            title             TEXT DEFAULT '',
            created_at        INTEGER NOT NULL,
            UNIQUE(provider, external_chat_id)
        )
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_external_identity_provider_external
            ON external_identity (provider, external_id)
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_provider_external
            ON conversation (provider, external_chat_id)
    """)
```

- [ ] **Step 2: Boot the bot once so the new tables are created**

```bash
python -c "import asyncio; from src.db import get_db; asyncio.run(get_db('data/history.db'))"
```

Expected: no error. Verify:

```bash
sqlite3 data/history.db ".schema external_identity"
sqlite3 data/history.db ".schema conversation"
```

Expected: both schemas print exactly as defined above.

- [ ] **Step 3: Commit**

```bash
git add src/db.py
git commit -m "feat(db): add external_identity and conversation mapping tables"
```

---

## Task 3 — Add `db.py` functions to resolve and create internal ids

**Files:**
- Modify: `src/db.py` — add a new section near the top (after `_migrate_schema`, before the `bosses` section).

These functions are used by the Telegram channel adapter (Task 9) and by the migration script (Task 4).

- [ ] **Step 1: Add identity-resolution functions to `db.py`**

After the closing of `_migrate_schema` and before the `# bosses` section comment, append:

```python
# ---------------------------------------------------------------------------
# external_identity / conversation — resolve external (provider, id) → internal_id
# ---------------------------------------------------------------------------

import uuid as _uuid
import time as _time


async def resolve_or_create_person(
    provider: str,
    external_id: str,
    name: str = "",
    username: str = "",
    db_path: str = "data/history.db",
) -> str:
    """Return internal_id (UUID) for (provider, external_id). Inserts if missing."""
    db = await get_db(db_path)
    async with db.execute(
        "SELECT internal_id FROM external_identity WHERE provider = ? AND external_id = ?",
        (provider, str(external_id)),
    ) as cur:
        row = await cur.fetchone()
    if row:
        if name or username:
            await db.execute(
                """UPDATE external_identity
                   SET name = COALESCE(NULLIF(?, ''), name),
                       username = COALESCE(NULLIF(?, ''), username)
                   WHERE internal_id = ?""",
                (name, username, row["internal_id"]),
            )
            await db.commit()
        return row["internal_id"]
    internal_id = str(_uuid.uuid4())
    await db.execute(
        """INSERT INTO external_identity
           (internal_id, provider, external_id, name, username, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (internal_id, provider, str(external_id), name or "", username or "", int(_time.time() * 1000)),
    )
    await db.commit()
    return internal_id


async def lookup_external_for_person(
    internal_id: str,
    db_path: str = "data/history.db",
) -> tuple[str, str] | None:
    """Return (provider, external_id) for an internal_id. None if not found."""
    db = await get_db(db_path)
    async with db.execute(
        "SELECT provider, external_id FROM external_identity WHERE internal_id = ?",
        (str(internal_id),),
    ) as cur:
        row = await cur.fetchone()
    return (row["provider"], row["external_id"]) if row else None


async def resolve_or_create_conversation(
    provider: str,
    external_chat_id: str,
    chat_type: str,
    title: str = "",
    db_path: str = "data/history.db",
) -> str:
    """Return internal_chat_id (UUID) for (provider, external_chat_id). Inserts if missing."""
    db = await get_db(db_path)
    async with db.execute(
        "SELECT internal_chat_id FROM conversation WHERE provider = ? AND external_chat_id = ?",
        (provider, str(external_chat_id)),
    ) as cur:
        row = await cur.fetchone()
    if row:
        if title:
            await db.execute(
                """UPDATE conversation
                   SET title = COALESCE(NULLIF(?, ''), title)
                   WHERE internal_chat_id = ?""",
                (title, row["internal_chat_id"]),
            )
            await db.commit()
        return row["internal_chat_id"]
    internal_chat_id = str(_uuid.uuid4())
    await db.execute(
        """INSERT INTO conversation
           (internal_chat_id, provider, external_chat_id, chat_type, title, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (internal_chat_id, provider, str(external_chat_id), chat_type, title or "", int(_time.time() * 1000)),
    )
    await db.commit()
    return internal_chat_id


async def lookup_external_for_conversation(
    internal_chat_id: str,
    db_path: str = "data/history.db",
) -> tuple[str, str] | None:
    """Return (provider, external_chat_id) for an internal_chat_id. None if not found."""
    db = await get_db(db_path)
    async with db.execute(
        "SELECT provider, external_chat_id FROM conversation WHERE internal_chat_id = ?",
        (str(internal_chat_id),),
    ) as cur:
        row = await cur.fetchone()
    return (row["provider"], row["external_chat_id"]) if row else None
```

- [ ] **Step 2: Boot-check**

```bash
python -c "from src import db; print(db.resolve_or_create_person)"
```

Expected: `<function resolve_or_create_person at 0x...>` printed.

- [ ] **Step 3: Smoke-test the round-trip in an ad-hoc script**

```bash
python <<'PY'
import asyncio
from src import db

async def main():
    iid = await db.resolve_or_create_person("telegram", "12345", "Test User", "testuser")
    print("internal_id:", iid)
    again = await db.resolve_or_create_person("telegram", "12345", "", "")
    assert iid == again, "must return same id on second call"
    ext = await db.lookup_external_for_person(iid)
    print("external:", ext)
    assert ext == ("telegram", "12345")
    cid = await db.resolve_or_create_conversation("telegram", "67890", "dm", "")
    print("internal_chat_id:", cid)

asyncio.run(main())
PY
```

Expected: prints two UUIDs and `external: ('telegram', '12345')`. No assertion errors.

- [ ] **Step 4: Clean up the test rows**

```bash
sqlite3 data/history.db <<'SQL'
DELETE FROM external_identity WHERE external_id = '12345';
DELETE FROM conversation WHERE external_chat_id = '67890';
SQL
```

- [ ] **Step 5: Commit**

```bash
git add src/db.py
git commit -m "feat(db): add resolve_or_create / lookup_external for persons and conversations"
```

---

## Task 4 — Write the migration script

**Files:**
- Create: `scripts/migrate_to_internal_id.py`

The script does everything in **one** sqlite3 connection inside one transaction:

1. Idempotency check — if `external_identity` already has any `provider='telegram'` row, exit 0.
2. Generate UUID for every distinct external person id observed in (`bosses.chat_id`, `memberships.chat_id`, `memberships.boss_chat_id`, `group_map.boss_chat_id`, `seen_contacts.chat_id`, `messages.sender_id`, every distinct DM `messages.chat_id` (one where `chat_type='dm'`)). Insert into `external_identity`.
3. Generate UUID for every distinct external conversation id observed in (`group_map.group_chat_id` (chat_type='group'), every distinct DM `messages.chat_id` matching a row in `bosses` (chat_type='dm'), `outbound_messages.to_chat_id`, `scheduled_reviews.group_chat_id`). Insert into `conversation`.
4. Rebuild every business table in dependency order using copy-pattern (`CREATE new`, `INSERT … SELECT JOIN`, `DROP old`, `ALTER RENAME`).
5. Drop `people_map`.
6. Commit.

- [ ] **Step 1: Create the script skeleton**

Create `scripts/migrate_to_internal_id.py`:

```python
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
    return ids


def collect_conversation_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Returns list of (external_chat_id, chat_type, title)."""
    rows: dict[str, tuple[str, str]] = {}
    # Group conversations
    for cid, name in conn.execute("SELECT group_chat_id, group_name FROM group_map"):
        if cid is None:
            continue
        rows[str(cid)] = ("group", name or "")
    # DM conversations — every distinct messages.chat_id that is a boss chat_id
    boss_ids = {str(c) for (c,) in conn.execute("SELECT chat_id FROM bosses")}
    for (cid,) in conn.execute("SELECT DISTINCT chat_id FROM messages"):
        if cid is None:
            continue
        s = str(cid)
        if s in rows:
            continue
        chat_type = "dm" if s in boss_ids else "dm"  # default to dm; member/partner DMs are still dm
        rows.setdefault(s, (chat_type, ""))
    # outbound_messages.to_chat_id — also DMs
    for (cid,) in conn.execute("SELECT DISTINCT to_chat_id FROM outbound_messages"):
        if cid is None:
            continue
        s = str(cid)
        rows.setdefault(s, ("dm", ""))
    # scheduled_reviews.group_chat_id — already groups
    for (cid,) in conn.execute(
        "SELECT DISTINCT group_chat_id FROM scheduled_reviews WHERE group_chat_id IS NOT NULL"
    ):
        s = str(cid)
        rows.setdefault(s, ("group", ""))
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

    return {"persons": len(person_ids), "conversations": len(convo_rows)}


def rebuild_business_tables(conn: sqlite3.Connection) -> None:
    """Rebuild every business table using copy-pattern to swap external ids → internal ids."""
    # Helper: SQL that maps an external person id (TEXT or INTEGER, cast to TEXT) → internal_id.
    # We embed it inline in JOINs.

    # ----- bosses -----
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
        CREATE TABLE messages_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    TEXT NOT NULL,
            sender_id  TEXT,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_messages_new_chat_created
            ON messages_new (chat_id, created_at);
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
        ALTER INDEX idx_messages_new_chat_created RENAME TO idx_messages_chat_created;
    """)

    # ----- notes -----
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
        CREATE TABLE token_usage_new (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id      TEXT NOT NULL,
            source            TEXT NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_token_usage_new_boss_created
            ON token_usage_new (boss_chat_id, created_at);
        INSERT INTO token_usage_new
            (id, boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens, created_at)
        SELECT t.id, ei.internal_id, t.source, t.prompt_tokens, t.completion_tokens, t.total_tokens, t.created_at
        FROM token_usage t
        JOIN external_identity ei
          ON ei.provider = 'telegram' AND ei.external_id = CAST(t.boss_chat_id AS TEXT);
        DROP INDEX IF EXISTS idx_token_usage_boss_created;
        DROP TABLE token_usage;
        ALTER TABLE token_usage_new RENAME TO token_usage;
        ALTER INDEX idx_token_usage_new_boss_created RENAME TO idx_token_usage_boss_created;
    """)

    # ----- pending_approvals -----
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
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
        CREATE INDEX idx_outbound_new_boss_to
            ON outbound_messages_new (boss_chat_id, to_chat_id, created_at DESC);
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
        ALTER INDEX idx_outbound_new_boss_to RENAME TO idx_outbound_boss_to;
    """)

    # ----- onboarding_state -----
    conn.executescript("""
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
    conn.executescript("""
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
    conn.executescript("""
        CREATE TABLE seen_contacts_new (
            chat_id          TEXT PRIMARY KEY,
            display_name     TEXT,
            username         TEXT,
            first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_chat   TEXT,
            seen_count       INTEGER DEFAULT 1
        );
        CREATE INDEX idx_seen_contacts_new_name ON seen_contacts_new (display_name);
        CREATE INDEX idx_seen_contacts_new_username ON seen_contacts_new (username);
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
        ALTER INDEX idx_seen_contacts_new_name RENAME TO idx_seen_contacts_name;
        ALTER INDEX idx_seen_contacts_new_username RENAME TO idx_seen_contacts_username;
    """)

    # ----- people_map: drop legacy -----
    conn.execute("DROP TABLE IF EXISTS people_map")


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
    conn.execute("PRAGMA foreign_keys = OFF")

    if already_migrated(conn):
        print("Already migrated — exiting 0.")
        conn.close()
        return 0

    try:
        conn.execute("BEGIN")
        # Tables external_identity / conversation must already exist (Task 2 added them).
        # If not present (someone is migrating without first running app boot), create now.
        conn.executescript("""
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

        rebuild_business_tables(conn)
        conn.commit()
        print("Migration committed.")
    except Exception as exc:
        conn.rollback()
        print(f"Migration failed, rolled back: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Boot-check the script syntactically**

```bash
python -m py_compile scripts/migrate_to_internal_id.py && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_to_internal_id.py
git commit -m "feat(scripts): add migrate_to_internal_id.py one-shot migration"
```

---

## Task 5 — Unit-test the migration on a synthetic DB

**Files:**
- Create: `tests/unit/test_migrate_to_internal_id.py`

- [ ] **Step 1: Write the test**

Create `tests/unit/test_migrate_to_internal_id.py`:

```python
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

import pytest

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
    conn.commit()
    conn.close()


def test_migration_end_to_end(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)

    # Run migration (subprocess so we exercise the actual CLI entry point)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Migration committed." in result.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    # external_identity has 4 distinct persons (100, 200, 300, 400)
    persons = {r["external_id"] for r in conn.execute(
        "SELECT external_id FROM external_identity WHERE provider = 'telegram'"
    )}
    assert persons >= {"100", "200", "300", "400"}

    # conversation has at least the group + DMs we touched
    convos = {r["external_chat_id"] for r in conn.execute(
        "SELECT external_chat_id FROM conversation WHERE provider = 'telegram'"
    )}
    assert "-1001" in convos
    assert "100" in convos  # boss DM

    # bosses now keyed by internal_id (TEXT, length 36)
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

    # people_map dropped
    has_pm = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='people_map'"
    ).fetchone()
    assert has_pm is None

    conn.close()

    # Idempotency: re-run is a no-op
    result2 = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db)],
        capture_output=True, text=True,
    )
    assert result2.returncode == 0
    assert "Already migrated" in result2.stdout
```

- [ ] **Step 2: Run the test**

```bash
pytest tests/unit/test_migrate_to_internal_id.py -v
```

Expected: PASS. If it fails, fix the migration script (Task 4) — do not modify the test to pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_migrate_to_internal_id.py
git commit -m "test(migration): end-to-end test for migrate_to_internal_id on synthetic db"
```

---

## Task 6 — Run the migration against the production DB

**Files:** None.

- [ ] **Step 1: Confirm we have a fresh backup**

```bash
ls -lh data/history.db.manual-backup-* data/history.db.pre-phase2.bak 2>/dev/null
```

If `pre-phase2.bak` is missing, the script will create it on first run. Otherwise OK.

- [ ] **Step 2: Run the migration**

```bash
python scripts/migrate_to_internal_id.py --db data/history.db
```

Expected output:

```
Backup written: data/history.db.pre-phase2.bak     (only if first run)
Mapped N persons and M conversations.
Migration committed.
```

If you see `Migration failed, rolled back: …`, the DB is untouched. Inspect the error, fix the script, and rerun.

- [ ] **Step 3: Verify row counts match Task 1 step 2**

```bash
sqlite3 data/history.db <<'SQL'
SELECT 'bosses' AS table_name, COUNT(*) FROM bosses
UNION ALL SELECT 'memberships', COUNT(*) FROM memberships
UNION ALL SELECT 'group_map', COUNT(*) FROM group_map
UNION ALL SELECT 'messages', COUNT(*) FROM messages
UNION ALL SELECT 'reminders', COUNT(*) FROM reminders
UNION ALL SELECT 'notes', COUNT(*) FROM notes
UNION ALL SELECT 'seen_contacts', COUNT(*) FROM seen_contacts
UNION ALL SELECT 'outbound_messages', COUNT(*) FROM outbound_messages
UNION ALL SELECT 'onboarding_state', COUNT(*) FROM onboarding_state
UNION ALL SELECT 'external_identity', COUNT(*) FROM external_identity
UNION ALL SELECT 'conversation', COUNT(*) FROM conversation;
SQL
```

Expected: every business table count is **exactly equal** to Task 1 step 2. New mapping tables have ≥ 1 row each.

- [ ] **Step 4: Spot-check a row**

```bash
sqlite3 data/history.db <<'SQL'
.headers on
.mode column
SELECT b.chat_id AS internal_id, b.name, ei.external_id
FROM bosses b
JOIN external_identity ei ON ei.internal_id = b.chat_id
LIMIT 5;
SQL
```

Expected: each row shows a UUID `internal_id`, the boss name, and the original Telegram external chat id.

- [ ] **Step 5: Re-run idempotency check**

```bash
python scripts/migrate_to_internal_id.py --db data/history.db
```

Expected: `Already migrated — exiting 0.`

- [ ] **Step 6: No commit** (the migration only changes `data/`, which is gitignored)

`git status` should be clean.

---

## Task 7 — Update `_init_schema` in `db.py` to reflect the post-migration schema

**Files:**
- Modify: `src/db.py` — replace the `_init_schema` body so fresh installs build the new schema directly. Drop legacy migrations that are now subsumed.

> **Why this matters:** the migration script handled the **existing** DB. But on a *fresh install* (e.g., a contributor cloning the repo, or `data/` deleted), `get_db()` runs `_init_schema` against an empty DB. That code path must also produce the new schema.

- [ ] **Step 1: Replace `_init_schema`**

In `src/db.py`, replace the entire `async def _init_schema(...)` body (currently lines 36-166) with:

```python
async def _init_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS external_identity (
            internal_id   TEXT PRIMARY KEY,
            provider      TEXT NOT NULL,
            external_id   TEXT NOT NULL,
            name          TEXT DEFAULT '',
            username      TEXT DEFAULT '',
            created_at    INTEGER NOT NULL,
            UNIQUE(provider, external_id)
        );

        CREATE INDEX IF NOT EXISTS idx_external_identity_provider_external
            ON external_identity (provider, external_id);

        CREATE TABLE IF NOT EXISTS conversation (
            internal_chat_id  TEXT PRIMARY KEY,
            provider          TEXT NOT NULL,
            external_chat_id  TEXT NOT NULL,
            chat_type         TEXT NOT NULL,
            title             TEXT DEFAULT '',
            created_at        INTEGER NOT NULL,
            UNIQUE(provider, external_chat_id)
        );

        CREATE INDEX IF NOT EXISTS idx_conversation_provider_external
            ON conversation (provider, external_chat_id);

        CREATE TABLE IF NOT EXISTS bosses (
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

        CREATE TABLE IF NOT EXISTS memberships (
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

        CREATE TABLE IF NOT EXISTS group_map (
            group_chat_id TEXT PRIMARY KEY,
            boss_chat_id  TEXT NOT NULL,
            group_name    TEXT DEFAULT '',
            project_id    TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    TEXT NOT NULL,
            sender_id  TEXT,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_chat_created
            ON messages (chat_id, created_at);

        CREATE TABLE IF NOT EXISTS notes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id TEXT NOT NULL,
            type         TEXT NOT NULL CHECK (type IN ('personal', 'project', 'group')),
            ref_id       TEXT NOT NULL,
            content      TEXT NOT NULL,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (boss_chat_id, type, ref_id)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id    TEXT NOT NULL,
            target_chat_id  TEXT,
            target_name     TEXT DEFAULT '',
            content         TEXT NOT NULL,
            remind_at       TIMESTAMP NOT NULL,
            status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id      TEXT NOT NULL,
            source            TEXT NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_token_usage_boss_created
            ON token_usage (boss_chat_id, created_at);

        CREATE TABLE IF NOT EXISTS pending_approvals (
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

        CREATE TABLE IF NOT EXISTS task_notifications (
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

        CREATE TABLE IF NOT EXISTS scheduled_reviews (
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

        CREATE TABLE IF NOT EXISTS outbound_messages (
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

        CREATE INDEX IF NOT EXISTS idx_outbound_boss_to
            ON outbound_messages (boss_chat_id, to_chat_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS onboarding_state (
            chat_id    TEXT PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            user_id     TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );

        CREATE TABLE IF NOT EXISTS seen_contacts (
            chat_id          TEXT PRIMARY KEY,
            display_name     TEXT,
            username         TEXT,
            first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_chat   TEXT,
            seen_count       INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_seen_contacts_name
            ON seen_contacts (display_name);
        CREATE INDEX IF NOT EXISTS idx_seen_contacts_username
            ON seen_contacts (username);
    """)

    await db.commit()
```

Delete the entire `_migrate_schema` function — every additive migration is now subsumed by the canonical CREATE statements above. Also delete the `await _migrate_schema(db)` call at the bottom of `_init_schema`.

- [ ] **Step 2: Boot-check**

```bash
python -c "import asyncio; from src.db import get_db; asyncio.run(get_db('data/history.db'))"
```

Expected: no error. (Existing tables match `CREATE IF NOT EXISTS` so this is a no-op against the migrated DB.)

- [ ] **Step 3: Boot-check fresh install**

```bash
rm -f /tmp/fresh.db
python -c "import asyncio; from src.db import get_db; asyncio.run(get_db('/tmp/fresh.db'))"
sqlite3 /tmp/fresh.db ".schema bosses"
```

Expected: `bosses` schema shows `chat_id TEXT PRIMARY KEY` (not INTEGER).

- [ ] **Step 4: Commit**

```bash
git add src/db.py
git commit -m "refactor(db): rewrite _init_schema for internal_id world; remove _migrate_schema"
```

---

## Task 8 — Update `db.py` function signatures: `int` → `str`

**Files:**
- Modify: `src/db.py` — update every function that accepts a chat-id-shaped parameter so its declared type is `str` (and remove `int(...)` casts inside SQL bindings — bindings will receive UUID strings now). Function names are preserved per the spec; semantic rename to `internal_id` happens in Phase 3.

> **Important nuance:** Most functions already pass parameters straight through to SQL (no casts). Bodies barely change — type hints + docstrings + a few stray `str(...)` casts that no longer help — but the **signature change** signals to callers that these are internal ids now.

- [ ] **Step 1: Bulk-update signatures**

Walk through each function in `src/db.py` and apply the following changes. Quick way: open the file, jump to each function, change types in-place. Reference table:

| Function | Old signature parameter(s) | New |
|---|---|---|
| `get_boss(db_or_chat_id, chat_id_or_path)` | `chat_id` is `int` | `str` (treat `db_or_chat_id` as `str` when not a connection) |
| `create_boss(...)` | `chat_id: int` | `chat_id: str` |
| `get_person(chat_id: int, ...)` | int | str — also delete this function entirely (people_map dropped); its only callers are dead code (verify with `grep "get_person\|add_person\|delete_person" src/`); remove all three (`get_person`, `add_person`, `delete_person`) and any callers |
| `get_group(...)` | `group_chat_id: int` | `group_chat_id: str` |
| `add_group(group_chat_id: int, boss_chat_id: int, ...)` | both int | both str |
| `save_message(chat_id: int, role, content, sender_id: Optional[int] = None, ...)` | int / Optional[int] | `chat_id: str`, `sender_id: Optional[str] = None` |
| `get_recent(chat_id: int, ...)` | int | str |
| `get_note(boss_chat_id: int, ...)` | int | str |
| `update_note(boss_chat_id: int, ...)` | int | str |
| `create_reminder(boss_chat_id: int, content, remind_at, target_chat_id: Optional[int] = None, ...)` | int | both str |
| `get_due_reminders(...)` | unchanged |
| `mark_reminder_done(reminder_id: int, ...)` | unchanged (reminder_id is autoincrement int) |
| `list_reminders(boss_chat_id: int, ...)` | int | str |
| `update_reminder(... target_chat_id: Optional[int] = None ...)` | int | str |
| `delete_reminder(... boss_chat_id: int ...)` | int | str |
| `log_token_usage(boss_chat_id: int, ...)` | int | str |
| `set_session(user_id: int, ...)` | int | str |
| `get_session(user_id: int, ...)` | int | str |
| `delete_session(user_id: int, ...)` | int | str |
| `log_outbound_dm(boss_chat_id: int, to_chat_id: int, ...)` | int | both str |
| `get_outbound_log(boss_chat_id: int, to_chat_id: int | None = None, ...)` | int | str |
| `get_onboarding_state(chat_id: int)` | int | str |
| `save_onboarding_state(chat_id: int, state)` | int | str |
| `clear_onboarding_state(chat_id: int)` | int | str |
| `upsert_seen_contact(chat_id: int, ..., last_seen_chat: int | None = None)` | int | both str |
| `get_seen_contact(chat_id: int)` | int | str |
| `list_unlinked_seen_contacts(lark_people_chat_ids: set[int], ...)` | `set[int]` | `set[str]` |

For the signature update, also remove any `int(...)` casts inside the function body that no longer make sense:

- In `_init_schema`: already done in Task 7.
- In `save_message`: no casts.
- Anywhere a function does `(int_id, ...)` in SQL bindings, leave alone — sqlite3 accepts str natively for TEXT columns.

- [ ] **Step 2: Delete the legacy `people_map` functions**

Find:

```python
async def get_person(...): ...
async def add_person(...): ...
async def delete_person(...): ...
```

Delete all three. They referenced the now-dropped `people_map` table.

Verify no remaining caller:

```bash
grep -rn "db.get_person\|db.add_person\|db.delete_person\|from src.db import get_person\|from src.db import add_person\|from src.db import delete_person" src/ tests/
```

Expected: no matches. If any callers remain, they're dead code — the prior `memberships` migration (in `_migrate_schema`) already populated `memberships` from `people_map`, and live code uses memberships everywhere. Remove the dead callers in the same commit.

- [ ] **Step 3: Boot-check the module**

```bash
python -c "from src import db; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/db.py
git commit -m "refactor(db): functions take internal_id (TEXT); drop legacy people_map helpers"
```

---

## Task 9 — Update `channels/telegram.py` to resolve internal ids inline

**Files:**
- Modify: `src/channels/telegram.py` — `_parse_update` builds `IncomingMessage` carrying **internal** chat_id and sender_id; the original external ids stay on `IncomingMessage.raw` for the harvester. `send_message` calls `db.save_message` with internal chat_id.

> **Why inline:** spec defers the proper boundary to `MessageRouter` (Phase 5). For Phase 2 we put the `resolve_or_create_*` calls directly in `_parse_update` and `send_message` so all downstream code is internal-id-clean before we even build services.

- [ ] **Step 1: Make `_parse_update` async**

Currently `_parse_update(self, update: dict) -> IncomingMessage | None`. Change to:

```python
async def _parse_update(self, update: dict) -> IncomingMessage | None:
```

Inside `_parse_update`, **after** computing `chat_id`, `sender_id`, `chat_type`, `group_name`, but **before** the `return IncomingMessage(...)` block, insert:

```python
        # Resolve external chat_id / sender_id → internal ids.
        # In Phase 5 this moves to MessageRouter; for now we do it inline so
        # downstream code (agent, tools, db) sees only internal ids.
        from src import db

        internal_chat_id = await db.resolve_or_create_conversation(
            "telegram",
            str(chat_id),
            chat_type,
            group_name,
        )
        internal_sender_id = ""
        if sender_id:
            internal_sender_id = await db.resolve_or_create_person(
                "telegram",
                str(sender_id),
                full_name(from_user),
                from_user.get("username", "") or "",
            )

        # reply_to_sender_id: also resolve if present.
        if reply_to_sender_id:
            reply_to_sender_id = await db.resolve_or_create_person(
                "telegram",
                reply_to_sender_id,
                "",
                "",
            )

        # mentions[*].id and new_members[*].id: resolve to internal ids too.
        for m in mentions:
            m["id"] = await db.resolve_or_create_person(
                "telegram", str(m["id"]), m.get("name", ""), m.get("username", ""),
            )
        for m in new_members:
            m["id"] = await db.resolve_or_create_person(
                "telegram", str(m["id"]), m.get("name", ""), m.get("username", ""),
            )
```

Then change the `return IncomingMessage(...)` to use the internal ids:

```python
        return IncomingMessage(
            channel="telegram",
            chat_id=internal_chat_id,
            chat_type=chat_type,
            sender_id=internal_sender_id,
            sender_name=full_name(from_user),
            text=text or "",
            attachments=attachments,
            is_mentioned=bot_mentioned,
            is_forwarded=bool(message.get("forward_date")),
            reply_to_message_id=reply_to_message_id,
            reply_to_sender_id=reply_to_sender_id,
            message_id=str(message.get("message_id", "")),
            timestamp=int(message.get("date", 0)),
            group_name=group_name,
            mentions=mentions,
            username_mentions=username_mentions,
            new_members=new_members,
            raw=update,         # raw still has external ids for harvester
        )
```

- [ ] **Step 2: Update the polling loop to await `_parse_update`**

In `start()` find:

```python
                for update in updates:
                    offset = update["update_id"] + 1
                    incoming = self._parse_update(update)
                    if incoming is None:
                        continue
```

Change `self._parse_update(update)` to `await self._parse_update(update)`:

```python
                for update in updates:
                    offset = update["update_id"] + 1
                    incoming = await self._parse_update(update)
                    if incoming is None:
                        continue
```

- [ ] **Step 3: Fix `send_message` and `edit_message` to handle internal chat_id**

`send_message` and `edit_message` are currently called with `chat_id: str` that callers will now pass as **internal** chat_id. We must:

1. Look up `(provider, external_id)` from `internal_chat_id`.
2. Use the external id for the actual Telegram API call.
3. Save history with the **internal** chat_id (so `messages.chat_id` is internal).

Modify `send_message` (around line 222):

```python
    async def send_message(
        self,
        chat_id: str,                 # internal_chat_id
        text: str,
        *,
        format: str = "markdown",
        save_history: bool = True,
        reply_to_message_id: str | None = None,
    ) -> OutgoingMessage:
        from src import db

        # Translate internal_chat_id → external Telegram chat id.
        ext = await db.lookup_external_for_conversation(chat_id)
        if not ext:
            logger.warning("send_message: no conversation row for internal_id=%s", chat_id)
            return OutgoingMessage(message_id="", chat_id=chat_id)
        _, external_chat_id = ext

        client = await self._ensure_client()
        parse_mode = self._map_format(format)
        payload: dict = {"chat_id": int(external_chat_id), "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = int(reply_to_message_id)

        resp = await client.post(f"{API}/bot{self._token}/sendMessage", json=payload)
        data = resp.json()
        ok = data.get("ok")
        message_id = data["result"]["message_id"] if ok else None

        if not ok:
            desc = (data.get("description") or "").lower()
            if parse_mode and ("can't parse" in desc or "parse entities" in desc):
                logger.warning("sendMessage Markdown failed, retrying plain: %s", desc)
                payload.pop("parse_mode", None)
                resp2 = await client.post(f"{API}/bot{self._token}/sendMessage", json=payload)
                data2 = resp2.json()
                if data2.get("ok"):
                    message_id = data2["result"]["message_id"]
                    ok = True
                else:
                    logger.warning("sendMessage plain retry also failed: %s", data2)
            else:
                logger.warning("sendMessage failed: %s", data)

        if ok and save_history and chat_id and text:
            try:
                from src import db as _db
                await _db.save_message(chat_id, "assistant", text)   # internal id
            except Exception:
                logger.warning("save_message after send failed", exc_info=True)

        return OutgoingMessage(
            message_id=str(message_id) if message_id else "",
            chat_id=chat_id,
        )
```

(The key change: `chat_id` parameter is internal; the actual Telegram API call uses `external_chat_id` from the lookup; `save_message` gets the internal id.)

Modify `edit_message` similarly:

```python
    async def edit_message(
        self,
        chat_id: str,                # internal_chat_id
        message_id: str,
        text: str,
        *,
        format: str = "markdown",
    ) -> None:
        from src import db
        ext = await db.lookup_external_for_conversation(chat_id)
        if not ext:
            logger.warning("edit_message: no conversation row for internal_id=%s", chat_id)
            return
        _, external_chat_id = ext

        client = await self._ensure_client()
        parse_mode = self._map_format(format)
        payload: dict = {
            "chat_id": int(external_chat_id),
            "message_id": int(message_id),
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        # ... rest unchanged ...
```

- [ ] **Step 4: Audit other Telegram methods that take chat_id**

Search:

```bash
grep -n "chat_id" src/channels/telegram.py
```

Walk every callsite. For methods like `get_chat_administrators`, `kick_chat_member`, `delete_message`, `restrict_chat_member`, etc.: each accepts `chat_id: str` as a parameter. If those parameters arrive from agent/tool code, they'll now be **internal** ids → must be translated to external before the API call.

For each such method, add at the top:

```python
        from src import db
        ext = await db.lookup_external_for_conversation(chat_id)
        if not ext:
            return False  # or whatever the existing failure return is
        _, external_chat_id = ext
        # ... use int(external_chat_id) where the original used int(chat_id) ...
```

This applies to **every** method in `TelegramMessenger` that touches Telegram with a chat_id.

- [ ] **Step 5: Boot-check**

```bash
python -c "import src.main; print('OK')"
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add src/channels/telegram.py
git commit -m "refactor(channels/telegram): resolve internal ids inline; emit IncomingMessage with internal ids"
```

---

## Task 10 — Strip lingering `int(chat_id)` casts in agent / onboarding / scheduler / tools

**Files:** various — mechanical sweep.

UUIDs are not parseable as int. Any `int(chat_id)` that runs on an internal id will crash. Cast removal is the change.

- [ ] **Step 1: Inventory the casts**

```bash
grep -rn "int(chat_id\|int(boss_chat_id\|int(target_chat_id\|int(group_chat_id\|int(sender_id\|int(uid)\|int(user_id" src/ | grep -v "src/channels/telegram.py" | grep -v "src/services/telegram.py"
```

Record the list of files and line numbers. The exclude on `channels/telegram.py` is because that file legitimately calls `int(external_chat_id)` for the Telegram API. The exclude on `services/telegram.py` is because that legacy shim is deleted in Phase 5.

- [ ] **Step 2: Remove each cast**

For each line listed in Step 1, open the file and convert `int(<id>)` to just `<id>`. The variable is already a string; SQLite binds it fine to TEXT columns.

Common patterns:

```python
# OLD
await db.save_message(int(chat_id), "user", text)
# NEW
await db.save_message(chat_id, "user", text)

# OLD
await db.create_reminder(int(boss_chat_id), ..., target_chat_id=int(target_id))
# NEW
await db.create_reminder(boss_chat_id, ..., target_chat_id=target_id)
```

- [ ] **Step 3: Verify no cast remains**

```bash
grep -rn "int(chat_id\|int(boss_chat_id\|int(target_chat_id\|int(group_chat_id\|int(sender_id\|int(uid)\|int(user_id" src/ | grep -v "src/channels/telegram.py" | grep -v "src/services/telegram.py"
```

Expected: no matches.

- [ ] **Step 4: Inventory `chat_id: int` type hints elsewhere**

```bash
grep -rn "chat_id: int\|sender_id: int\|boss_chat_id: int\|target_chat_id: int\|group_chat_id: int" src/ | grep -v "src/services/telegram.py" | grep -v "src/channels/telegram.py"
```

Each of these is a type hint that lies after Phase 2. For each, change `int` to `str`. If the parameter has `Optional[int]` change to `Optional[str]`. If a function uses defaults like `target_chat_id: int | None = None`, change to `target_chat_id: str | None = None`.

- [ ] **Step 5: Boot-check**

```bash
python -c "import src.main; print('OK')"
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: strip int(chat_id) casts and update type hints to str (internal_id)"
```

---

## Task 11 — Update `agent.handle_message` entry-point signature

**Files:**
- Modify: `src/agent.py` — function signature uses `str` for chat_id and sender_id (the channel adapter now emits internal ids).

- [ ] **Step 1: Find the entry point**

```bash
grep -n "async def handle_message" src/agent.py
```

Open at that line. Current signature looks like:

```python
async def handle_message(
    text: str,
    chat_id: int,
    sender_id: int,
    *,
    is_group: bool = False,
    bot_mentioned: bool = False,
    ...
):
```

- [ ] **Step 2: Change types to str**

```python
async def handle_message(
    text: str,
    chat_id: str,
    sender_id: str,
    *,
    is_group: bool = False,
    bot_mentioned: bool = False,
    ...
):
```

Walk the body: any `int(chat_id)` cast disappears (covered by Task 10).

- [ ] **Step 3: Update the bridge in `src/services/telegram.py`**

This file is the legacy polling-bridge (slated for deletion in Phase 5). Look at how it calls `agent.handle_message` and confirm the call passes `incoming.chat_id` and `incoming.sender_id` straight through (they are already strings since Phase 1). If any `int()` cast wraps them, remove it.

```bash
grep -n "agent.handle_message\|handle_message(" src/services/telegram.py
```

Edit each call to drop int casts.

- [ ] **Step 4: Boot-check**

```bash
python -c "import src.agent; print('OK')"
python -c "import src.main; print('OK')"
```

Both expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/agent.py src/services/telegram.py
git commit -m "refactor(agent): handle_message takes string internal_id / sender_id"
```

---

## Task 12 — Update `identity.py` and harvester to write internal ids to `seen_contacts`

**Files:**
- Modify: `src/identity.py` — every place that writes to `seen_contacts` (via `db.upsert_seen_contact`) must first resolve the external chat_id to internal_id and pass that to db.

- [ ] **Step 1: Inventory `upsert_seen_contact` callers**

```bash
grep -rn "upsert_seen_contact\|seen_contacts" src/
```

Record the files / lines.

- [ ] **Step 2: For each caller, resolve before writing**

Open each call site. Replace:

```python
await db.upsert_seen_contact(external_chat_id, name, username, last_seen_chat=group_chat_id)
```

with:

```python
internal_id = await db.resolve_or_create_person("telegram", str(external_chat_id), name, username)
internal_chat = None
if group_chat_id:
    internal_chat = await db.resolve_or_create_conversation("telegram", str(group_chat_id), "group", "")
await db.upsert_seen_contact(internal_id, name, username, last_seen_chat=internal_chat)
```

**However:** if the harvester is being called from `channels/telegram.py._parse_update` (which already resolved everything), the values inside `mentions[*]["id"]` and `new_members[*]["id"]` are **already internal ids** (from Task 9 step 1). In that case, the harvester just passes them through and the `resolve_or_create_*` call is unnecessary.

Audit case-by-case. Rule: **the boundary that turns external → internal is `_parse_update`**. Anything reading from `IncomingMessage` already has internal ids. Only places that read raw Telegram payloads (`incoming.raw`) need to resolve.

- [ ] **Step 3: Boot-check**

```bash
python -c "import src.identity; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/identity.py
git commit -m "refactor(identity): write internal ids to seen_contacts; harvest via internal id"
```

---

## Task 13 — Update `scheduler.py` and reminder dispatch

**Files:**
- Modify: `src/scheduler.py` — when firing a reminder, the recipient chat_id read from `reminders.target_chat_id` is now an internal id. The scheduler calls some Telegram method to send. With Task 9 in place, sending uses internal id throughout — but verify.

- [ ] **Step 1: Audit scheduler send paths**

```bash
grep -n "send_message\|target_chat_id\|chat_id" src/scheduler.py
```

For each `await telegram.send_message(...)` (or via `messenger.send_message`) call, confirm the `chat_id` argument is the internal id from `reminders.target_chat_id`. No translation needed at this layer — the channel does it.

- [ ] **Step 2: Remove any remaining `int(...)` casts**

Already covered in Task 10, but double-check.

- [ ] **Step 3: Boot-check**

```bash
python -c "import src.scheduler; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit (only if changes made; otherwise skip)**

```bash
git add src/scheduler.py
git commit -m "refactor(scheduler): use internal chat_id throughout reminder dispatch"
```

---

## Task 14 — Manual smoke test

**Files:** None.

This is the safety net for Phase 2. Run through every flow on the **migrated** production DB.

- [ ] **Step 1: Start the bot**

```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Expected: Uvicorn starts; "Polling started as @<bot>" in the log; no traceback.

- [ ] **Step 2: DM "hello"**

In Telegram, DM the bot: `hello`.

Expected: Normal secretary reply. Watch the server log:
- `[chat:<UUID> type:dm sender:<UUID>] Received: hello` — chat_id and sender_id are now UUIDs in the log.
- No `ImportError`, no `ValueError: invalid literal for int()`, no `OperationalError: no such column`.

- [ ] **Step 3: Send a tool-using message**

DM: `tạo task test phase 2 cho [thành viên trong workspace] deadline 2026-12-31`.

Expected: bot creates a task in Lark and replies. Verify the task appears in your Lark Base.

- [ ] **Step 4: Reminder flow**

DM: `nhắc tôi 1 phút nữa: smoke test phase 2`.

Wait one minute. Expected: bot DMs the reminder content.

- [ ] **Step 5: Group flow**

In a registered group, mention the bot: `@<bot> tóm tắt giúp`.

Expected: bot replies with the relevant summary. Group flow paths exercise `group_map`, which has been rebuilt.

- [ ] **Step 6: Reset workspace (sanity, optional)**

If you have a test boss account, run `/reset` to confirm reset still works against the new schema. Skip on your real account.

- [ ] **Step 7: Stop the bot, check logs**

```bash
# Ctrl-C the uvicorn process
```

Scan the log for any traceback. If any flow produced an error you didn't notice in real time, file a fix and re-run that step.

- [ ] **Step 8: Final state check**

```bash
git log --oneline | head -15
git status
```

Expected: ~10–13 commits from this phase; clean working tree.

---

## Done Criteria

- [ ] `data/history.db.pre-phase2.bak` exists.
- [ ] `external_identity` and `conversation` tables populated; row counts match the count of distinct external persons / conversations from Task 1.
- [ ] Every business table’s id columns are `TEXT` and contain UUIDs.
- [ ] `people_map` table no longer exists.
- [ ] `pytest tests/unit/test_migrate_to_internal_id.py -v` is green.
- [ ] `python -c "import src.main"` succeeds.
- [ ] `grep -rn "int(chat_id\|int(boss_chat_id\|int(target_chat_id\|int(sender_id\|int(group_chat_id\|int(user_id" src/ | grep -v telegram.py` returns nothing.
- [ ] `grep -rn "chat_id: int\|sender_id: int\|boss_chat_id: int\|target_chat_id: int\|group_chat_id: int" src/ | grep -v telegram.py` returns nothing.
- [ ] Manual smoke test (Task 14) all six flows pass.

When all checked, Phase 2 is done. Next: come back to writing-plans skill to draft Phase 3 (split `db.py` into per-aggregate repositories).
