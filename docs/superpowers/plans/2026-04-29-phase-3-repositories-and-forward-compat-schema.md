# Phase 3 — Repositories + Forward-Compat Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `src/db.py` into per-aggregate repository classes under `src/repositories/`, while `db.py` becomes a thin facade preserving the existing function-style API. Add forward-compat schema (tenant lifecycle, per-boss LLM config, audit log, encryption helper) so future multi-tenant features land without another data migration.

**Architecture:** Each repo is a class taking `aiosqlite.Connection` in `__init__`. `db.py` keeps its module-level functions but delegates to lazily-built singleton repo instances. Caller files (~28 of them) do not change in this phase — Phase 5 replaces the lazy-singleton pattern with `AppContainer` constructor injection. New schema columns are default-NULL or default-`'active'` so behaviour is unchanged until a future caller reads them.

**Tech Stack:** Python 3.11+, aiosqlite, sqlite3, cryptography (Fernet), pytest with `asyncio_mode = auto`.

**Spec reference:** [docs/superpowers/specs/2026-04-28-platform-channel-and-layered-architecture-design.md](../specs/2026-04-28-platform-channel-and-layered-architecture-design.md), Phase 3 + the "Forward-Compatibility for Scale" section.

---

## Scope Notes

**In scope:**

- Add columns to `bosses`: `status`, `plan`, `expires_at`, `llm_provider`, `llm_model`, `llm_api_key_encrypted`, `embedding_provider`, `embedding_model`, `embedding_dim`. All default-safe.
- Add new table `audit_log`.
- Add `Settings.boss_credential_encryption_key` (env var, optional). Add `infrastructure/crypto.py` Fernet helpers.
- Create 12 repository modules under `src/repositories/`. Each is a class with constructor-injected `aiosqlite.Connection`.
- `src/db.py` body shrinks: keeps `get_db()` / `close_db()` / `_init_schema` / `_notification_col`, replaces every other function with a one-line wrapper that calls into the corresponding repo singleton.
- Two unit tests: schema migration applied to a synthetic DB; one repo round-trip (boss).

**Out of scope (Phase 5+):**

- Update caller files (`agent.py`, `tools/*.py`, `onboarding.py`, …) to call repos directly. The facade keeps the old API working; Phase 5 will replace the facade with `AppContainer` injection.
- Wire `AuditService.log()` calls. Schema + repo are ready; no caller invokes them this phase.
- Read or enforce `boss.status` / `plan`. Schema is ready; gate ships in Phase 5.
- Read or use `boss.llm_*` / `boss.embedding_*` columns. Schema is ready; LLM provider abstraction ships in Phase 4.
- Rewrite Qdrant collection naming. Phase 4 work (depends on the LLM provider / embedding-dim split).
- Encryption key rotation tooling.

---

## File Structure After This Phase

```
src/
├── db.py                              # MODIFIED — thin facade
├── infrastructure/
│   └── crypto.py                      # NEW — Fernet encrypt/decrypt
├── repositories/                      # NEW package
│   ├── __init__.py
│   ├── _base.py                       # shared row-to-dict helpers if any
│   ├── boss_repo.py                   # bosses
│   ├── identity_repo.py               # external_identity, seen_contacts
│   ├── conversation_repo.py           # conversation, group_map
│   ├── membership_repo.py             # memberships (+ legacy people_map wrappers)
│   ├── message_repo.py                # messages, outbound_messages
│   ├── note_repo.py                   # notes
│   ├── reminder_repo.py               # reminders
│   ├── token_usage_repo.py            # token_usage
│   ├── session_repo.py                # sessions, onboarding_state
│   ├── approval_repo.py               # pending_approvals, task_notifications
│   ├── review_repo.py                 # scheduled_reviews
│   └── audit_repo.py                  # NEW table audit_log

tests/unit/
├── test_phase3_schema.py              # NEW
└── test_boss_repo.py                  # NEW

src/config.py                          # MODIFIED — add boss_credential_encryption_key
```

**Repo grouping rationale.** Spec lists 9 repos; we land 12 because `seen_contacts` (identity) / `outbound_messages` (message log) / `onboarding_state` (session-shaped) / `task_notifications` (paired with approvals) / `audit_log` (new) all need a home, and bunching unrelated tables under "misc" is worse than one extra file. Aggregates that share lifecycle (`sessions` + `onboarding_state`, `pending_approvals` + `task_notifications`) are intentionally co-located.

---

## Task 1 — Add forward-compat schema (columns + audit_log)

**Files:**
- Modify: `src/db.py:39-228` (`_init_schema`)
- Create: `tests/unit/test_phase3_schema.py`

> Schema is additive. Existing rows get `status='active'`, NULLs for the rest. No ALTER on prod DB needed — `_init_schema` is run on every boot via `get_db()`, but its CREATE TABLE statements use `IF NOT EXISTS` and don't add new columns to existing tables. So we *must* either (a) add ALTER TABLE statements inside `_init_schema` that swallow "duplicate column" errors, or (b) write a one-shot script. We pick (a) because it's idempotent on every boot and matches the prior `_migrate_schema` style — except this time it's a thin migration block focused on Phase 3 additions only.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_phase3_schema.py`:

```python
"""Verify Phase 3 forward-compat schema additions on a fresh DB and on a
post-Phase-2 DB (existing bosses row is upgraded, no data lost)."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from src.db import get_db, close_db


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


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    """db.py keeps a module-level _db singleton; reset between tests."""
    yield
    asyncio.get_event_loop().run_until_complete(close_db())


def test_fresh_install_has_phase3_columns(tmp_path):
    db_path = tmp_path / "fresh.db"

    async def _run():
        await get_db(str(db_path))

    asyncio.run(_run())

    cols = _columns(db_path, "bosses")
    expected = {
        "status", "plan", "expires_at",
        "llm_provider", "llm_model", "llm_api_key_encrypted",
        "embedding_provider", "embedding_model", "embedding_dim",
    }
    missing = expected - cols
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
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
            sender_id TEXT, role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO bosses (chat_id, name) VALUES ('uuid-1', 'Boss A');
    """)
    conn.commit()
    conn.close()

    async def _run():
        await get_db(str(db_path))

    asyncio.run(_run())

    cols = _columns(db_path, "bosses")
    assert "status" in cols
    assert "llm_api_key_encrypted" in cols
    assert _table_exists(db_path, "audit_log")

    # Existing row still exists, with default status='active'
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT chat_id, name, status FROM bosses").fetchone()
        assert row == ("uuid-1", "Boss A", "active")
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_phase3_schema.py -v
```

Expected: FAIL — `bosses missing columns: {...}` and `audit_log` does not exist.

- [ ] **Step 3: Add forward-compat block to `_init_schema`**

Open `src/db.py`. At the end of `_init_schema` (after the existing `executescript` and before `await db.commit()`), add a Phase 3 migration block:

```python
    # ---- Phase 3 forward-compat additions (additive, default-safe) ----
    for col, definition in [
        ("status",                "TEXT DEFAULT 'active'"),
        ("plan",                  "TEXT DEFAULT NULL"),
        ("expires_at",            "TIMESTAMP DEFAULT NULL"),
        ("llm_provider",          "TEXT DEFAULT NULL"),
        ("llm_model",             "TEXT DEFAULT NULL"),
        ("llm_api_key_encrypted", "TEXT DEFAULT NULL"),
        ("embedding_provider",    "TEXT DEFAULT NULL"),
        ("embedding_model",       "TEXT DEFAULT NULL"),
        ("embedding_dim",         "INTEGER DEFAULT NULL"),
    ]:
        try:
            await db.execute(f"ALTER TABLE bosses ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    await db.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_internal_id  TEXT,
            action             TEXT NOT NULL,
            target_table       TEXT,
            target_id          TEXT,
            payload_json       TEXT,
            ts                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_actor_ts
            ON audit_log (actor_internal_id, ts DESC)
    """)
```

Also add `status TEXT DEFAULT 'active'` and the other 8 new columns to the canonical `CREATE TABLE IF NOT EXISTS bosses` block in the same `executescript`, so a fresh install gets them directly. Replace the existing `bosses` CREATE block:

```sql
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
    status               TEXT DEFAULT 'active',
    plan                 TEXT DEFAULT NULL,
    expires_at           TIMESTAMP DEFAULT NULL,
    llm_provider         TEXT DEFAULT NULL,
    llm_model            TEXT DEFAULT NULL,
    llm_api_key_encrypted TEXT DEFAULT NULL,
    embedding_provider   TEXT DEFAULT NULL,
    embedding_model      TEXT DEFAULT NULL,
    embedding_dim        INTEGER DEFAULT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

The `audit_log` CREATE inside `executescript` for fresh installs (added next to the other `CREATE TABLE IF NOT EXISTS` lines):

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_internal_id  TEXT,
    action             TEXT NOT NULL,
    target_table       TEXT,
    target_id          TEXT,
    payload_json       TEXT,
    ts                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_actor_ts
    ON audit_log (actor_internal_id, ts DESC);
```

The duplicate (canonical CREATE + ALTER block) is intentional: fresh installs use the canonical CREATE; post-Phase-2 DBs hit the ALTER block which swallows the "duplicate column" error.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_phase3_schema.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run on production DB and verify**

```bash
uv run python -c "import asyncio; from src.db import get_db; asyncio.run(get_db('data/history.db'))"
sqlite3 data/history.db "PRAGMA table_info(bosses)" | grep -E "status|plan|llm_|embedding_|expires_at"
sqlite3 data/history.db ".schema audit_log"
sqlite3 data/history.db "SELECT chat_id, name, status FROM bosses"
```

Expected:
- 9 new column names print
- `audit_log` schema prints
- Existing boss row shows `status='active'`

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/unit/test_phase3_schema.py
git commit -m "feat(db): phase 3 forward-compat schema (tenant lifecycle, llm config, audit_log)"
```

---

## Task 2 — Add `Settings.boss_credential_encryption_key` + `infrastructure/crypto.py`

**Files:**
- Modify: `src/config.py`
- Create: `src/infrastructure/crypto.py`
- Create: `tests/unit/test_crypto.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_crypto.py`:

```python
"""Tests for src.infrastructure.crypto — Fernet round-trip + missing-key handling."""
import pytest

from src.infrastructure import crypto


def test_round_trip_with_key():
    key = crypto.generate_key()
    cipher = crypto.encrypt("sk-test-1234567890", key=key)
    assert cipher != "sk-test-1234567890"
    plain = crypto.decrypt(cipher, key=key)
    assert plain == "sk-test-1234567890"


def test_decrypt_with_wrong_key_raises():
    cipher = crypto.encrypt("hello", key=crypto.generate_key())
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(cipher, key=crypto.generate_key())


def test_encrypt_without_key_raises():
    with pytest.raises(crypto.CryptoError, match="encryption key not configured"):
        crypto.encrypt("hello", key=None)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_crypto.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.infrastructure.crypto'`.

- [ ] **Step 3: Add the env var to `Settings`**

Open `src/config.py`. Find the `Settings(BaseSettings)` class and add (alphabetically with other optional fields):

```python
    boss_credential_encryption_key: str = ""    # Fernet key (44-char base64); empty = encryption disabled
```

- [ ] **Step 4: Implement `src/infrastructure/crypto.py`**

```python
"""Fernet symmetric encryption for boss-supplied credentials.

The encryption key is read from `Settings.boss_credential_encryption_key`
(env var). If unset, encryption / decryption raise `CryptoError` rather than
silently degrading to plaintext.

Key generation (one-off, save the output to env):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(Exception):
    """Raised when encryption / decryption fails or key is missing."""


def generate_key() -> str:
    """Return a fresh Fernet key as a 44-char base64 string."""
    return Fernet.generate_key().decode()


def _fernet(key: str | None) -> Fernet:
    if not key:
        raise CryptoError("encryption key not configured")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CryptoError(f"invalid encryption key: {exc}") from exc


def encrypt(plain: str, *, key: str | None) -> str:
    """Encrypt `plain` with `key` (Fernet, base64). Returns ASCII ciphertext."""
    return _fernet(key).encrypt(plain.encode()).decode()


def decrypt(cipher: str, *, key: str | None) -> str:
    """Decrypt `cipher` produced by `encrypt`. Raises CryptoError on bad token."""
    try:
        return _fernet(key).decrypt(cipher.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("decryption failed (wrong key or tampered ciphertext)") from exc
```

- [ ] **Step 5: Confirm `cryptography` is in the dep set**

```bash
uv run python -c "import cryptography; print(cryptography.__version__)"
```

Expected: a version string. If `ModuleNotFoundError`, run `uv add cryptography` and re-run.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_crypto.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/infrastructure/crypto.py tests/unit/test_crypto.py
# stage pyproject.toml + uv.lock if uv add was needed:
git add pyproject.toml uv.lock
git commit -m "feat(infrastructure/crypto): Fernet helpers + boss_credential_encryption_key setting"
```

---

## Task 3 — Create `src/repositories/` package + `_base.py`

**Files:**
- Create: `src/repositories/__init__.py`
- Create: `src/repositories/_base.py`

- [ ] **Step 1: Create the empty package init**

Create `src/repositories/__init__.py` (empty):

```python
```

- [ ] **Step 2: Create `_base.py`**

Create `src/repositories/_base.py`:

```python
"""Shared helpers for repository implementations.

Every repo class follows the same shape:

    class FooRepo:
        def __init__(self, db: aiosqlite.Connection) -> None:
            self._db = db

        async def some_method(self, ...) -> ...:
            async with self._db.execute(...) as cur:
                row = await cur.fetchone()
            return dict(row) if row else None

Repos do NOT call `db.commit()` for read methods. Write methods call commit
inline (matches the existing function-style behaviour in `src/db.py`).
"""
from __future__ import annotations

from typing import Optional

import aiosqlite


def row_to_dict(row: Optional[aiosqlite.Row]) -> Optional[dict]:
    return dict(row) if row else None
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.repositories._base import row_to_dict; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/repositories/__init__.py src/repositories/_base.py
git commit -m "feat(repositories): create package skeleton + _base.row_to_dict"
```

---

## Task 4 — `boss_repo.py`

**Files:**
- Create: `src/repositories/boss_repo.py`
- Create: `tests/unit/test_boss_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_boss_repo.py`:

```python
"""Tests for src.repositories.boss_repo — round-trip via the canonical schema."""
from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from src.db import _init_schema
from src.repositories.boss_repo import BossRepo


@pytest.mark.asyncio
async def test_create_get_list_round_trip(tmp_path):
    path = tmp_path / "t.db"
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await _init_schema(conn)

    repo = BossRepo(conn)
    await repo.create(
        chat_id="uuid-boss-1",
        name="Boss A",
        company="ACME",
        lark_base_token="bt",
        lark_table_people="tp",
        lark_table_tasks="tt",
        lark_table_projects="tpr",
        lark_table_ideas="ti",
        lark_table_reminders="tr",
        lark_table_notes="tn",
        email="a@x.com",
    )

    one = await repo.get("uuid-boss-1")
    assert one is not None
    assert one["chat_id"] == "uuid-boss-1"
    assert one["name"] == "Boss A"
    assert one["status"] == "active"          # default from Phase 3 schema
    assert one["llm_api_key_encrypted"] is None

    assert await repo.get("nope") is None

    everyone = await repo.list_all()
    assert len(everyone) == 1
    assert everyone[0]["chat_id"] == "uuid-boss-1"

    await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_boss_repo.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.repositories.boss_repo'`.

- [ ] **Step 3: Implement `boss_repo.py`**

Create `src/repositories/boss_repo.py`:

```python
"""bosses table — workspace owner + Lark workspace pointers + per-boss config."""
from __future__ import annotations

from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class BossRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM bosses WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def list_all(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM bosses ORDER BY created_at"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def create(
        self,
        chat_id: str,
        name: str,
        company: str = "",
        lark_base_token: Optional[str] = None,
        lark_table_people: Optional[str] = None,
        lark_table_tasks: Optional[str] = None,
        lark_table_projects: Optional[str] = None,
        lark_table_ideas: Optional[str] = None,
        lark_table_reminders: Optional[str] = None,
        lark_table_notes: Optional[str] = None,
        email: str = "",
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO bosses
                (chat_id, name, company, lark_base_token, lark_table_people,
                 lark_table_tasks, lark_table_projects, lark_table_ideas,
                 lark_table_reminders, lark_table_notes, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                name                 = excluded.name,
                company              = excluded.company,
                lark_base_token      = excluded.lark_base_token,
                lark_table_people    = excluded.lark_table_people,
                lark_table_tasks     = excluded.lark_table_tasks,
                lark_table_projects  = excluded.lark_table_projects,
                lark_table_ideas     = excluded.lark_table_ideas,
                lark_table_reminders = excluded.lark_table_reminders,
                lark_table_notes     = excluded.lark_table_notes,
                email                = excluded.email
            """,
            (chat_id, name, company, lark_base_token, lark_table_people,
             lark_table_tasks, lark_table_projects, lark_table_ideas,
             lark_table_reminders, lark_table_notes, email),
        )
        await self._db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_boss_repo.py -v
```

Expected: PASS — 1 test.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/boss_repo.py tests/unit/test_boss_repo.py
git commit -m "feat(repositories/boss): add BossRepo with create/get/list_all"
```

---

## Task 5 — `identity_repo.py` + `conversation_repo.py`

**Files:**
- Create: `src/repositories/identity_repo.py`
- Create: `src/repositories/conversation_repo.py`

> No new tests this task — round-trip is already exercised by Phase 2's existing migration test through the same SQL. Tests come back with the facade verification in Task 11.

- [ ] **Step 1: Implement `identity_repo.py`**

Create `src/repositories/identity_repo.py`. The class merges three concerns: external_identity (provider mapping for persons), and seen_contacts (passive harvest index). They share the "this is a person id" semantics.

```python
"""external_identity + seen_contacts — person-side identity (provider mapping + passive index)."""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class IdentityRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- external_identity ----------------------------------------------------

    async def resolve_or_create_person(
        self, provider: str, external_id: str, name: str = "", username: str = "",
    ) -> str:
        """Return internal_id (UUID) for (provider, external_id). Race-safe via UNIQUE."""
        async with self._db.execute(
            "SELECT internal_id FROM external_identity WHERE provider = ? AND external_id = ?",
            (provider, str(external_id)),
        ) as cur:
            row = await cur.fetchone()
        if row:
            if name or username:
                await self._db.execute(
                    """UPDATE external_identity
                       SET name = COALESCE(NULLIF(?, ''), name),
                           username = COALESCE(NULLIF(?, ''), username)
                       WHERE internal_id = ?""",
                    (name, username, row["internal_id"]),
                )
                await self._db.commit()
            return row["internal_id"]
        internal_id = str(uuid.uuid4())
        try:
            await self._db.execute(
                """INSERT INTO external_identity
                   (internal_id, provider, external_id, name, username, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (internal_id, provider, str(external_id), name or "", username or "",
                 int(time.time() * 1000)),
            )
            await self._db.commit()
            return internal_id
        except sqlite3.IntegrityError:
            async with self._db.execute(
                "SELECT internal_id FROM external_identity WHERE provider = ? AND external_id = ?",
                (provider, str(external_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise
            return row["internal_id"]

    async def lookup_external_for_person(self, internal_id: str) -> Optional[tuple[str, str]]:
        async with self._db.execute(
            "SELECT provider, external_id FROM external_identity WHERE internal_id = ?",
            (str(internal_id),),
        ) as cur:
            row = await cur.fetchone()
        return (row["provider"], row["external_id"]) if row else None

    # --- seen_contacts --------------------------------------------------------

    async def upsert_seen_contact(
        self, chat_id: str, display_name: str = "", username: str = "",
        last_seen_chat: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO seen_contacts (chat_id, display_name, username, last_seen_chat)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                display_name   = COALESCE(NULLIF(excluded.display_name, ''), seen_contacts.display_name),
                username       = COALESCE(NULLIF(excluded.username, ''), seen_contacts.username),
                last_seen_at   = CURRENT_TIMESTAMP,
                last_seen_chat = COALESCE(excluded.last_seen_chat, seen_contacts.last_seen_chat),
                seen_count     = seen_contacts.seen_count + 1
            """,
            (str(chat_id), display_name or "", username or "", last_seen_chat),
        )
        await self._db.commit()

    async def get_seen_contact(self, chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM seen_contacts WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def search_seen_contacts(self, query: str, limit: int = 20) -> list[dict]:
        like = f"%{query.lower()}%"
        async with self._db.execute(
            """SELECT * FROM seen_contacts
               WHERE lower(display_name) LIKE ? OR lower(username) LIKE ?
               ORDER BY last_seen_at DESC LIMIT ?""",
            (like, like, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_unlinked_seen_contacts(
        self, lark_people_chat_ids: set[str], days: int = 30, limit: int = 30,
    ) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM seen_contacts
               WHERE last_seen_at >= datetime('now', ? )
               ORDER BY last_seen_at DESC LIMIT ?""",
            (f"-{days} days", limit * 3),
        ) as cur:
            rows = await cur.fetchall()
        filtered: list[dict] = []
        for r in rows:
            d = dict(r)
            if d["chat_id"] not in lark_people_chat_ids:
                filtered.append(d)
                if len(filtered) >= limit:
                    break
        return filtered
```

- [ ] **Step 2: Implement `conversation_repo.py`**

Create `src/repositories/conversation_repo.py`:

```python
"""conversation + group_map — chat-side identity (provider mapping + group registry)."""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class ConversationRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- conversation (provider mapping) -------------------------------------

    async def resolve_or_create_conversation(
        self, provider: str, external_chat_id: str, chat_type: str, title: str = "",
    ) -> str:
        async with self._db.execute(
            "SELECT internal_chat_id FROM conversation WHERE provider = ? AND external_chat_id = ?",
            (provider, str(external_chat_id)),
        ) as cur:
            row = await cur.fetchone()
        if row:
            if title:
                await self._db.execute(
                    """UPDATE conversation
                       SET title = COALESCE(NULLIF(?, ''), title)
                       WHERE internal_chat_id = ?""",
                    (title, row["internal_chat_id"]),
                )
                await self._db.commit()
            return row["internal_chat_id"]
        internal_chat_id = str(uuid.uuid4())
        try:
            await self._db.execute(
                """INSERT INTO conversation
                   (internal_chat_id, provider, external_chat_id, chat_type, title, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (internal_chat_id, provider, str(external_chat_id), chat_type, title or "",
                 int(time.time() * 1000)),
            )
            await self._db.commit()
            return internal_chat_id
        except sqlite3.IntegrityError:
            async with self._db.execute(
                "SELECT internal_chat_id FROM conversation WHERE provider = ? AND external_chat_id = ?",
                (provider, str(external_chat_id)),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                raise
            return row["internal_chat_id"]

    async def lookup_external_for_conversation(
        self, internal_chat_id: str,
    ) -> Optional[tuple[str, str]]:
        async with self._db.execute(
            "SELECT provider, external_chat_id FROM conversation WHERE internal_chat_id = ?",
            (str(internal_chat_id),),
        ) as cur:
            row = await cur.fetchone()
        return (row["provider"], row["external_chat_id"]) if row else None

    # --- group_map ------------------------------------------------------------

    async def get_group(self, group_chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM group_map WHERE group_chat_id = ?", (str(group_chat_id),)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def add_group(
        self, group_chat_id: str, boss_chat_id: str, group_name: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO group_map (group_chat_id, boss_chat_id, group_name, project_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(group_chat_id) DO UPDATE SET
                boss_chat_id = excluded.boss_chat_id,
                group_name   = excluded.group_name,
                project_id   = excluded.project_id
            """,
            (str(group_chat_id), str(boss_chat_id), group_name, project_id),
        )
        await self._db.commit()
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.repositories.identity_repo import IdentityRepo; from src.repositories.conversation_repo import ConversationRepo; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/repositories/identity_repo.py src/repositories/conversation_repo.py
git commit -m "feat(repositories): IdentityRepo + ConversationRepo"
```

---

## Task 6 — `membership_repo.py` + `message_repo.py`

**Files:**
- Create: `src/repositories/membership_repo.py`
- Create: `src/repositories/message_repo.py`

- [ ] **Step 1: Implement `membership_repo.py`**

```python
"""memberships table + legacy people_map wrappers (delegate to memberships)."""
from __future__ import annotations

from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class MembershipRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_for_user(self, user_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE chat_id = ? AND status = 'active'",
            (str(user_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_for_boss(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE boss_chat_id = ?",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get(self, chat_id: str, boss_chat_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
            (str(chat_id), str(boss_chat_id)),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def upsert(
        self, chat_id: str, boss_chat_id: str, person_type: str, name: str,
        status: str = "active", request_info: Optional[str] = None,
        lark_record_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO memberships
                (chat_id, boss_chat_id, person_type, name, status,
                 request_info, lark_record_id, requested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, boss_chat_id) DO UPDATE SET
                person_type    = excluded.person_type,
                name           = excluded.name,
                status         = excluded.status,
                request_info   = COALESCE(excluded.request_info, request_info),
                lark_record_id = COALESCE(excluded.lark_record_id, lark_record_id),
                approved_at    = CASE WHEN excluded.status = 'active' THEN CURRENT_TIMESTAMP ELSE approved_at END
            """,
            (str(chat_id), str(boss_chat_id), person_type, name, status,
             request_info, lark_record_id),
        )
        await self._db.commit()

    async def delete(self, chat_id: str, boss_chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
            (str(chat_id), str(boss_chat_id)),
        )
        await self._db.commit()

    # --- Legacy people_map wrappers (Phase 2) --------------------------------

    async def get_person_legacy(self, chat_id: str) -> Optional[dict]:
        """Returns first active membership for this chat_id; legacy shape (`type` field)."""
        async with self._db.execute(
            "SELECT chat_id, boss_chat_id, person_type AS type, name FROM memberships "
            "WHERE chat_id = ? AND status = 'active' LIMIT 1",
            (str(chat_id),),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def delete_person_legacy(self, chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM memberships WHERE chat_id = ?", (str(chat_id),)
        )
        await self._db.commit()
```

- [ ] **Step 2: Implement `message_repo.py`**

```python
"""messages + outbound_messages — chat history + bot-initiated DM log."""
from __future__ import annotations

from typing import Optional

import aiosqlite


class MessageRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- messages ------------------------------------------------------------

    async def save(
        self, chat_id: str, role: str, content: str, sender_id: Optional[str] = None,
    ) -> int:
        cur = await self._db.execute(
            "INSERT INTO messages (chat_id, sender_id, role, content) VALUES (?, ?, ?, ?)",
            (str(chat_id), sender_id, role, content),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_recent(self, chat_id: str, limit: int = 8) -> list[dict]:
        async with self._db.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (str(chat_id), limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # --- outbound_messages ---------------------------------------------------

    async def log_outbound_dm(
        self, boss_chat_id: str, to_chat_id: str, to_name: str, content: str,
        trigger_type: str = "manual", task_id: str = "", project: str = "",
        workspace_id: str = "",
    ) -> None:
        await self._db.execute(
            """INSERT INTO outbound_messages
               (boss_chat_id, workspace_id, to_chat_id, to_name, content,
                trigger_type, task_id, project)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(boss_chat_id), workspace_id, str(to_chat_id), to_name, content,
             trigger_type, task_id or "", project or ""),
        )
        await self._db.commit()

    async def get_outbound_log(
        self, boss_chat_id: str, to_chat_id: Optional[str] = None,
        trigger_type: Optional[str] = None, limit: int = 50,
    ) -> list[dict]:
        conditions = ["boss_chat_id = ?"]
        params: list = [str(boss_chat_id)]
        if to_chat_id:
            conditions.append("to_chat_id = ?")
            params.append(str(to_chat_id))
        if trigger_type:
            conditions.append("trigger_type = ?")
            params.append(trigger_type)
        where = " AND ".join(conditions)
        async with self._db.execute(
            f"SELECT * FROM outbound_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.repositories.membership_repo import MembershipRepo; from src.repositories.message_repo import MessageRepo; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/repositories/membership_repo.py src/repositories/message_repo.py
git commit -m "feat(repositories): MembershipRepo + MessageRepo"
```

---

## Task 7 — `note_repo.py` + `reminder_repo.py` + `token_usage_repo.py`

**Files:**
- Create: `src/repositories/note_repo.py`
- Create: `src/repositories/reminder_repo.py`
- Create: `src/repositories/token_usage_repo.py`

- [ ] **Step 1: Implement `note_repo.py`**

```python
"""notes table — personal / project / group notes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class NoteRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(
        self, boss_chat_id: str, note_type: str, ref_id: str,
    ) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
            (str(boss_chat_id), note_type, ref_id),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def upsert(
        self, boss_chat_id: str, note_type: str, ref_id: str, content: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        await self._db.execute(
            """
            INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(boss_chat_id, type, ref_id) DO UPDATE SET
                content    = excluded.content,
                updated_at = excluded.updated_at
            """,
            (str(boss_chat_id), note_type, ref_id, content, now),
        )
        await self._db.commit()
```

- [ ] **Step 2: Implement `reminder_repo.py`**

```python
"""reminders table — pending DMs with optional target."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite


class ReminderRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create(
        self, boss_chat_id: str, content: str, remind_at: datetime,
        target_chat_id: Optional[str] = None, target_name: str = "",
    ) -> int:
        remind_at_str = remind_at.isoformat(sep=" ", timespec="seconds")
        cur = await self._db.execute(
            "INSERT INTO reminders (boss_chat_id, target_chat_id, target_name, content, remind_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(boss_chat_id), target_chat_id, target_name, content, remind_at_str),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_due(self, now: Optional[datetime] = None) -> list[dict]:
        if now is None:
            now = datetime.now(timezone.utc)
        now_str = now.isoformat(sep=" ", timespec="seconds")
        async with self._db.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ? ORDER BY remind_at",
            (now_str,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_done(self, reminder_id: int) -> None:
        await self._db.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?", (reminder_id,)
        )
        await self._db.commit()

    async def list_for_boss(
        self, boss_chat_id: str, status: str = "pending", limit: int = 50,
    ) -> list[dict]:
        lim = max(1, min(limit, 200))
        if status == "all":
            async with self._db.execute(
                """SELECT * FROM reminders
                   WHERE boss_chat_id = ?
                   ORDER BY remind_at ASC LIMIT ?""",
                (str(boss_chat_id), lim),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self._db.execute(
                """SELECT * FROM reminders
                   WHERE boss_chat_id = ? AND status = ?
                   ORDER BY remind_at ASC LIMIT ?""",
                (str(boss_chat_id), status, lim),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def update(
        self, reminder_id: int, boss_chat_id: str, *,
        content: Optional[str] = None, remind_at: Optional[datetime] = None,
        update_target: bool = False, target_chat_id: Optional[str] = None,
        target_name: str = "",
    ) -> bool:
        sets: list[str] = []
        params: list = []
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if remind_at is not None:
            sets.append("remind_at = ?")
            params.append(remind_at.isoformat(sep=" ", timespec="seconds"))
        if update_target:
            sets.append("target_chat_id = ?")
            params.append(target_chat_id)
            sets.append("target_name = ?")
            params.append(target_name)
        if not sets:
            return False
        params.extend([reminder_id, str(boss_chat_id)])
        sql = f"UPDATE reminders SET {', '.join(sets)} WHERE id = ? AND boss_chat_id = ?"
        cur = await self._db.execute(sql, params)
        await self._db.commit()
        return cur.rowcount > 0

    async def delete(self, reminder_id: int, boss_chat_id: str) -> bool:
        cur = await self._db.execute(
            "DELETE FROM reminders WHERE id = ? AND boss_chat_id = ?",
            (reminder_id, str(boss_chat_id)),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def sync_from_lark(self, sqlite_id: int, content: str, status: str) -> None:
        await self._db.execute(
            "UPDATE reminders SET content = ?, status = ? WHERE id = ?",
            (content, status, sqlite_id),
        )
        await self._db.commit()
```

- [ ] **Step 3: Implement `token_usage_repo.py`**

```python
"""token_usage table — per-boss LLM cost tracking."""
from __future__ import annotations

import aiosqlite


class TokenUsageRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def log(
        self, boss_chat_id: str, source: str,
        prompt_tokens: int, completion_tokens: int, total_tokens: int,
    ) -> None:
        await self._db.execute(
            "INSERT INTO token_usage "
            "(boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(boss_chat_id), source, prompt_tokens, completion_tokens, total_tokens),
        )
        await self._db.commit()
```

- [ ] **Step 4: Boot-check**

```bash
uv run python -c "from src.repositories.note_repo import NoteRepo; from src.repositories.reminder_repo import ReminderRepo; from src.repositories.token_usage_repo import TokenUsageRepo; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/note_repo.py src/repositories/reminder_repo.py src/repositories/token_usage_repo.py
git commit -m "feat(repositories): NoteRepo + ReminderRepo + TokenUsageRepo"
```

---

## Task 8 — `session_repo.py` + `approval_repo.py` + `review_repo.py`

**Files:**
- Create: `src/repositories/session_repo.py`
- Create: `src/repositories/approval_repo.py`
- Create: `src/repositories/review_repo.py`

- [ ] **Step 1: Implement `session_repo.py`**

Combines `sessions` (TTL key/value) and `onboarding_state` (per-user JSON state). Both are session-shaped per-user state.

```python
"""sessions + onboarding_state — short-lived per-user state (TTL or onboarding-flow)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite


class SessionRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- sessions (TTL key/value) --------------------------------------------

    async def set(
        self, user_id: str, key: str, value: str, ttl_minutes: int = 30,
    ) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO sessions (user_id, key, value, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (str(user_id), key, value, expires),
        )
        await self._db.commit()

    async def get(self, user_id: str, key: str) -> Optional[str]:
        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT value FROM sessions WHERE user_id = ? AND key = ? AND expires_at > ?",
            (str(user_id), key, now),
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else None

    async def delete(self, user_id: str, key: str) -> None:
        await self._db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND key = ?",
            (str(user_id), key),
        )
        await self._db.commit()

    # --- onboarding_state ----------------------------------------------------

    async def get_onboarding_state(self, chat_id: str) -> dict:
        async with self._db.execute(
            "SELECT state_json FROM onboarding_state WHERE chat_id = ?", (str(chat_id),)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["state_json"])
        except Exception:
            return {}

    async def save_onboarding_state(self, chat_id: str, state: dict) -> None:
        await self._db.execute(
            """INSERT INTO onboarding_state (chat_id, state_json, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(chat_id) DO UPDATE SET
                   state_json = excluded.state_json,
                   updated_at = CURRENT_TIMESTAMP""",
            (str(chat_id), json.dumps(state, ensure_ascii=False)),
        )
        await self._db.commit()

    async def clear_onboarding_state(self, chat_id: str) -> None:
        await self._db.execute(
            "DELETE FROM onboarding_state WHERE chat_id = ?", (str(chat_id),)
        )
        await self._db.commit()
```

- [ ] **Step 2: Implement `approval_repo.py`**

Combines `pending_approvals` and `task_notifications` (both workflow-state per task).

```python
"""pending_approvals + task_notifications — task-workflow state (approvals + notification ledger)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite


_NOTIFICATION_KIND_COL = {
    "assigned": "notified_assigned",
    "24h": "notified_24h",
    "2h":  "notified_2h",
}


def _notification_col(kind: str) -> str:
    col = _NOTIFICATION_KIND_COL.get(kind)
    if col is None:
        raise ValueError(f"Unknown notification kind: {kind!r}")
    return col


class ApprovalRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # --- pending_approvals ---------------------------------------------------

    async def create(
        self, boss_chat_id: str, requester_id: str,
        task_record_id: str, payload: str,
    ) -> int:
        expires = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
        async with self._db.execute(
            """INSERT INTO pending_approvals
               (boss_chat_id, requester_id, task_record_id, payload, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (str(boss_chat_id), str(requester_id), task_record_id, payload, expires),
        ) as cur:
            row_id = cur.lastrowid
        await self._db.commit()
        return row_id

    async def get_pending(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending' "
            "ORDER BY created_at",
            (str(boss_chat_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def update_status(self, approval_id: int, status: str) -> None:
        await self._db.execute(
            "UPDATE pending_approvals SET status = ? WHERE id = ?",
            (status, approval_id),
        )
        await self._db.commit()

    # --- task_notifications --------------------------------------------------

    async def upsert_task_notification(
        self, task_record_id: str, boss_chat_id: str,
        assignee_chat_id: Optional[str] = None,
    ) -> None:
        await self._db.execute(
            """INSERT OR IGNORE INTO task_notifications
               (task_record_id, boss_chat_id, assignee_chat_id)
               VALUES (?, ?, ?)""",
            (task_record_id, str(boss_chat_id),
             str(assignee_chat_id) if assignee_chat_id else None),
        )
        await self._db.commit()

    async def mark_notification_sent(
        self, task_record_id: str, boss_chat_id: str, kind: str,
    ) -> None:
        col = _notification_col(kind)
        await self._db.execute(
            f"UPDATE task_notifications SET {col} = 1 "
            f"WHERE task_record_id = ? AND boss_chat_id = ?",
            (task_record_id, str(boss_chat_id)),
        )
        await self._db.commit()

    async def get_unnotified(self, boss_chat_id: str, kind: str) -> list[dict]:
        col = _notification_col(kind)
        async with self._db.execute(
            f"SELECT * FROM task_notifications WHERE boss_chat_id = ? AND {col} = 0",
            (str(boss_chat_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_unnotified_overdue(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM task_notifications "
            "WHERE boss_chat_id = ? AND notified_overdue = 0",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_overdue_notified(
        self, task_record_id: str, boss_chat_id: str,
    ) -> None:
        await self._db.execute(
            "UPDATE task_notifications "
            "SET notified_overdue = 1, notified_overdue_at = CURRENT_TIMESTAMP "
            "WHERE task_record_id = ? AND boss_chat_id = ?",
            (task_record_id, str(boss_chat_id)),
        )
        await self._db.commit()
```

- [ ] **Step 3: Implement `review_repo.py`**

```python
"""scheduled_reviews — cron-driven LLM review jobs per boss."""
from __future__ import annotations

import aiosqlite


_REVIEW_ALLOWED_COLS = frozenset({
    "cron_time", "content_type", "custom_prompt", "enabled", "timezone",
})


class ReviewRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def list_for_owner(self, owner_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM scheduled_reviews WHERE owner_id = ? ORDER BY cron_time",
            (str(owner_id),),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def create(
        self, owner_id: str, cron_time: str, content_type: str,
        custom_prompt: str | None = None,
    ) -> int:
        async with self._db.execute(
            """INSERT INTO scheduled_reviews (owner_id, cron_time, content_type, custom_prompt)
               VALUES (?, ?, ?, ?)""",
            (str(owner_id), cron_time, content_type, custom_prompt),
        ) as cur:
            await self._db.commit()
            return cur.lastrowid

    async def update(
        self, review_id: int, owner_id: str | None = None, **kwargs,
    ) -> bool:
        invalid = set(kwargs) - _REVIEW_ALLOWED_COLS
        if invalid:
            raise ValueError(f"Invalid column(s) for scheduled_reviews: {invalid}")
        if not kwargs:
            return False
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        if owner_id is not None:
            async with self._db.execute(
                f"UPDATE scheduled_reviews SET {sets} WHERE id = ? AND owner_id = ?",
                (*kwargs.values(), review_id, str(owner_id)),
            ) as cur:
                await self._db.commit()
                return cur.rowcount > 0
        await self._db.execute(
            f"UPDATE scheduled_reviews SET {sets} WHERE id = ?",
            (*kwargs.values(), review_id),
        )
        await self._db.commit()
        return True

    async def delete(self, review_id: int, owner_id: str | None = None) -> bool:
        if owner_id is not None:
            async with self._db.execute(
                "DELETE FROM scheduled_reviews WHERE id = ? AND owner_id = ?",
                (review_id, str(owner_id)),
            ) as cur:
                await self._db.commit()
                return cur.rowcount > 0
        await self._db.execute(
            "DELETE FROM scheduled_reviews WHERE id = ?", (review_id,)
        )
        await self._db.commit()
        return True

    async def list_all_enabled(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM scheduled_reviews WHERE enabled = 1"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

- [ ] **Step 4: Boot-check**

```bash
uv run python -c "from src.repositories.session_repo import SessionRepo; from src.repositories.approval_repo import ApprovalRepo; from src.repositories.review_repo import ReviewRepo; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/session_repo.py src/repositories/approval_repo.py src/repositories/review_repo.py
git commit -m "feat(repositories): SessionRepo + ApprovalRepo + ReviewRepo"
```

---

## Task 9 — `audit_repo.py`

**Files:**
- Create: `src/repositories/audit_repo.py`

> No facade integration — `audit_log` is brand-new in Phase 3 and has no callers yet. The repo exists so Phase 4's `AuditService` can wire to it without schema work.

- [ ] **Step 1: Implement**

```python
"""audit_log table — append-only audit trail for boss-visible actions.

Wired but not actively written this phase — Phase 4's AuditService is the first caller.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite


class AuditRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def log(
        self, actor_internal_id: Optional[str], action: str,
        target_table: Optional[str] = None, target_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        cur = await self._db.execute(
            """INSERT INTO audit_log
               (actor_internal_id, action, target_table, target_id, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (actor_internal_id, action, target_table, target_id, payload_json),
        )
        await self._db.commit()
        return cur.lastrowid

    async def list_for_actor(
        self, actor_internal_id: str, limit: int = 50,
    ) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM audit_log
               WHERE actor_internal_id = ?
               ORDER BY ts DESC LIMIT ?""",
            (actor_internal_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
```

- [ ] **Step 2: Boot-check**

```bash
uv run python -c "from src.repositories.audit_repo import AuditRepo; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add src/repositories/audit_repo.py
git commit -m "feat(repositories): AuditRepo (used by Phase 4 AuditService)"
```

---

## Task 10 — Convert `src/db.py` into a thin facade

**Files:**
- Modify: `src/db.py` — replace each function body with a one-liner that delegates to a singleton repo instance.

**Strategy:** Keep `_init_schema`, `_notification_col` (used by approval_repo's helper), `get_db`, `close_db`, the constants and module-level state. Replace every other function with a delegating wrapper. Repo singletons are built lazily on first access using `get_db()`.

- [ ] **Step 1: Add repo accessor helpers**

After `close_db()` near the bottom of `src/db.py`, append:

```python
# ---------------------------------------------------------------------------
# Repository singletons — lazily built on first access.
# Phase 5 will replace these with AppContainer constructor injection.
# ---------------------------------------------------------------------------

from src.repositories.boss_repo         import BossRepo
from src.repositories.identity_repo     import IdentityRepo
from src.repositories.conversation_repo import ConversationRepo
from src.repositories.membership_repo   import MembershipRepo
from src.repositories.message_repo      import MessageRepo
from src.repositories.note_repo         import NoteRepo
from src.repositories.reminder_repo     import ReminderRepo
from src.repositories.token_usage_repo  import TokenUsageRepo
from src.repositories.session_repo      import SessionRepo
from src.repositories.approval_repo     import ApprovalRepo
from src.repositories.review_repo       import ReviewRepo
from src.repositories.audit_repo        import AuditRepo

_repos: dict[str, object] = {}


async def _repo(name: str, cls):
    """Return the singleton repo instance for `cls`, building it on first call."""
    if name not in _repos:
        db = await get_db()
        _repos[name] = cls(db)
    return _repos[name]
```

- [ ] **Step 2: Replace each delegating function body**

Walk the file from top to bottom. For each pre-Phase-3 function listed below, replace its body with a one-line repo call. Function names and signatures stay identical so callers are not affected.

Boss section:

```python
async def get_boss(db_or_chat_id, chat_id_or_path=None) -> Optional[dict]:
    """get_boss(chat_id) or get_boss(db, chat_id) — both calling styles supported."""
    import aiosqlite as _aiosqlite
    if isinstance(db_or_chat_id, _aiosqlite.Connection):
        chat_id = chat_id_or_path
    else:
        chat_id = db_or_chat_id
    repo: BossRepo = await _repo("boss", BossRepo)
    return await repo.get(chat_id)


async def create_boss(
    chat_id: str,
    name: str,
    company: str = "",
    lark_base_token: Optional[str] = None,
    lark_table_people: Optional[str] = None,
    lark_table_tasks: Optional[str] = None,
    lark_table_projects: Optional[str] = None,
    lark_table_ideas: Optional[str] = None,
    lark_table_reminders: Optional[str] = None,
    lark_table_notes: Optional[str] = None,
    email: str = "",
    db_path: str = "data/history.db",
) -> None:
    repo: BossRepo = await _repo("boss", BossRepo)
    await repo.create(
        chat_id=chat_id, name=name, company=company,
        lark_base_token=lark_base_token, lark_table_people=lark_table_people,
        lark_table_tasks=lark_table_tasks, lark_table_projects=lark_table_projects,
        lark_table_ideas=lark_table_ideas, lark_table_reminders=lark_table_reminders,
        lark_table_notes=lark_table_notes, email=email,
    )


async def get_all_bosses(db_path: str = "data/history.db") -> list[dict]:
    repo: BossRepo = await _repo("boss", BossRepo)
    return await repo.list_all()
```

Identity / conversation section (replaces resolve/lookup helpers):

```python
async def resolve_or_create_person(
    provider: str, external_id: str, name: str = "", username: str = "",
    db_path: str = "data/history.db",
) -> str:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.resolve_or_create_person(provider, external_id, name, username)


async def lookup_external_for_person(
    internal_id: str, db_path: str = "data/history.db",
) -> tuple[str, str] | None:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.lookup_external_for_person(internal_id)


async def resolve_or_create_conversation(
    provider: str, external_chat_id: str, chat_type: str, title: str = "",
    db_path: str = "data/history.db",
) -> str:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    return await repo.resolve_or_create_conversation(provider, external_chat_id, chat_type, title)


async def lookup_external_for_conversation(
    internal_chat_id: str, db_path: str = "data/history.db",
) -> tuple[str, str] | None:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    return await repo.lookup_external_for_conversation(internal_chat_id)
```

Legacy people_map wrappers:

```python
async def get_person(chat_id: str, db_path: str = "data/history.db") -> Optional[dict]:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    return await repo.get_person_legacy(chat_id)


async def add_person(
    chat_id: str, boss_chat_id: str, person_type: str, name: str = "",
    db_path: str = "data/history.db",
) -> None:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    await repo.upsert(chat_id, boss_chat_id, person_type, name, status="active")


async def delete_person(chat_id: str, db_path: str = "data/history.db") -> None:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    await repo.delete_person_legacy(chat_id)
```

Group:

```python
async def get_group(db_or_group_chat_id, group_chat_id_or_path=None) -> Optional[dict]:
    import aiosqlite as _aiosqlite
    if isinstance(db_or_group_chat_id, _aiosqlite.Connection):
        group_chat_id = group_chat_id_or_path
    else:
        group_chat_id = db_or_group_chat_id
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    return await repo.get_group(group_chat_id)


async def add_group(
    group_chat_id: str, boss_chat_id: str, group_name: str = "",
    project_id: str | None = None,
) -> None:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    await repo.add_group(group_chat_id, boss_chat_id, group_name, project_id)
```

Messages:

```python
async def save_message(
    chat_id: str, role: str, content: str, sender_id: Optional[str] = None,
    db_path: str = "data/history.db",
) -> int:
    repo: MessageRepo = await _repo("message", MessageRepo)
    return await repo.save(chat_id, role, content, sender_id)


async def get_recent(
    chat_id: str, limit: int = 8, db_path: str = "data/history.db",
) -> list[dict]:
    repo: MessageRepo = await _repo("message", MessageRepo)
    return await repo.get_recent(chat_id, limit)
```

Notes:

```python
async def get_note(
    boss_chat_id: str, note_type: str, ref_id: str,
    db_path: str = "data/history.db",
) -> Optional[dict]:
    repo: NoteRepo = await _repo("note", NoteRepo)
    return await repo.get(boss_chat_id, note_type, ref_id)


async def update_note(
    boss_chat_id: str, note_type: str, ref_id: str, content: str,
    db_path: str = "data/history.db",
) -> None:
    repo: NoteRepo = await _repo("note", NoteRepo)
    await repo.upsert(boss_chat_id, note_type, ref_id, content)
```

Reminders (signatures preserved exactly):

```python
async def create_reminder(
    boss_chat_id: str, content: str, remind_at: datetime,
    target_chat_id: Optional[str] = None, target_name: str = "",
    db_path: str = "data/history.db",
) -> int:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.create(boss_chat_id, content, remind_at, target_chat_id, target_name)


async def get_due_reminders(
    now: Optional[datetime] = None, db_path: str = "data/history.db",
) -> list[dict]:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.get_due(now)


async def mark_reminder_done(reminder_id: int, db_path: str = "data/history.db") -> None:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    await repo.mark_done(reminder_id)


async def list_reminders(
    boss_chat_id: str, status: str = "pending", limit: int = 50,
    db_path: str = "data/history.db",
) -> list[dict]:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.list_for_boss(boss_chat_id, status, limit)


async def update_reminder(
    reminder_id: int, boss_chat_id: str, *,
    content: Optional[str] = None, remind_at: Optional[datetime] = None,
    update_target: bool = False, target_chat_id: Optional[str] = None,
    target_name: str = "", db_path: str = "data/history.db",
) -> bool:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.update(
        reminder_id, boss_chat_id,
        content=content, remind_at=remind_at, update_target=update_target,
        target_chat_id=target_chat_id, target_name=target_name,
    )


async def delete_reminder(
    reminder_id: int, boss_chat_id: str, db_path: str = "data/history.db",
) -> bool:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.delete(reminder_id, boss_chat_id)


async def sync_reminder_from_lark(db, sqlite_id: int, content: str, status: str):
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    await repo.sync_from_lark(sqlite_id, content, status)
```

Token usage:

```python
async def log_token_usage(
    boss_chat_id: str, source: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    db_path: str = "data/history.db",
) -> None:
    repo: TokenUsageRepo = await _repo("token_usage", TokenUsageRepo)
    await repo.log(boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens)
```

Sessions + onboarding_state:

```python
async def set_session(user_id: str, key: str, value: str, ttl_minutes: int = 30) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.set(user_id, key, value, ttl_minutes)


async def get_session(user_id: str, key: str) -> str | None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    return await repo.get(user_id, key)


async def delete_session(user_id: str, key: str) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.delete(user_id, key)


async def get_onboarding_state(chat_id: str) -> dict:
    repo: SessionRepo = await _repo("session", SessionRepo)
    return await repo.get_onboarding_state(chat_id)


async def save_onboarding_state(chat_id: str, state: dict) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.save_onboarding_state(chat_id, state)


async def clear_onboarding_state(chat_id: str) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.clear_onboarding_state(chat_id)
```

Memberships (kept signatures with the awkward `db` first arg):

```python
async def get_memberships(user_id_or_db, user_id_str=None) -> list[dict]:
    """get_memberships(user_id_str) or get_memberships(db, user_id_str)."""
    import aiosqlite as _aiosqlite
    if isinstance(user_id_or_db, _aiosqlite.Connection):
        uid = user_id_str
    else:
        uid = user_id_or_db
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    return await repo.list_for_user(uid)


async def get_all_memberships_for_boss(boss_chat_id: str) -> list[dict]:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    return await repo.list_for_boss(boss_chat_id)


async def get_membership(db, chat_id: str, boss_chat_id: str) -> dict | None:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    return await repo.get(chat_id, boss_chat_id)


async def upsert_membership(db, chat_id: str, boss_chat_id: str, person_type: str,
                             name: str, status: str = "active",
                             request_info: str = None, lark_record_id: str = None):
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    await repo.upsert(chat_id, boss_chat_id, person_type, name, status, request_info, lark_record_id)


async def delete_membership(db, chat_id: str, boss_chat_id: str):
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    await repo.delete(chat_id, boss_chat_id)
```

Pending approvals + task notifications:

```python
async def create_approval(db, boss_chat_id: str, requester_id: str,
                           task_record_id: str, payload: str) -> int:
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    return await repo.create(boss_chat_id, requester_id, task_record_id, payload)


async def get_pending_approvals(db, boss_chat_id: str) -> list[dict]:
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    return await repo.get_pending(boss_chat_id)


async def update_approval_status(db, approval_id: int, status: str):
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    await repo.update_status(approval_id, status)


async def upsert_task_notification(db, task_record_id: str, boss_chat_id: str,
                                    assignee_chat_id: str = None):
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    await repo.upsert_task_notification(task_record_id, boss_chat_id, assignee_chat_id)


async def mark_notification_sent(db, task_record_id: str, boss_chat_id: str, kind: str):
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    await repo.mark_notification_sent(task_record_id, boss_chat_id, kind)


async def get_unnotified_tasks(db, boss_chat_id: str, kind: str) -> list[dict]:
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    return await repo.get_unnotified(boss_chat_id, kind)


async def get_unnotified_overdue_tasks(db_conn, boss_chat_id: str) -> list[dict]:
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    return await repo.get_unnotified_overdue(boss_chat_id)


async def mark_overdue_notified(db_conn, task_record_id: str, boss_chat_id: str) -> None:
    repo: ApprovalRepo = await _repo("approval", ApprovalRepo)
    await repo.mark_overdue_notified(task_record_id, boss_chat_id)
```

Scheduled reviews:

```python
async def list_scheduled_reviews(db, owner_id: str) -> list[dict]:
    repo: ReviewRepo = await _repo("review", ReviewRepo)
    return await repo.list_for_owner(owner_id)


async def create_scheduled_review(db, owner_id: str, cron_time: str,
                                   content_type: str, custom_prompt: str = None) -> int:
    repo: ReviewRepo = await _repo("review", ReviewRepo)
    return await repo.create(owner_id, cron_time, content_type, custom_prompt)


async def update_scheduled_review(db, review_id: int, owner_id: str = None, **kwargs) -> bool:
    repo: ReviewRepo = await _repo("review", ReviewRepo)
    return await repo.update(review_id, owner_id, **kwargs)


async def delete_scheduled_review(db, review_id: int, owner_id: str = None) -> bool:
    repo: ReviewRepo = await _repo("review", ReviewRepo)
    return await repo.delete(review_id, owner_id)


async def get_all_enabled_reviews(db) -> list[dict]:
    repo: ReviewRepo = await _repo("review", ReviewRepo)
    return await repo.list_all_enabled()
```

Outbound messages:

```python
async def log_outbound_dm(
    boss_chat_id: str, to_chat_id: str, to_name: str, content: str,
    trigger_type: str = "manual", task_id: str = "", project: str = "",
    workspace_id: str = "",
) -> None:
    repo: MessageRepo = await _repo("message", MessageRepo)
    await repo.log_outbound_dm(
        boss_chat_id, to_chat_id, to_name, content, trigger_type,
        task_id, project, workspace_id,
    )


async def get_outbound_log(
    boss_chat_id: str, to_chat_id: str | None = None,
    trigger_type: str | None = None, limit: int = 50,
) -> list[dict]:
    repo: MessageRepo = await _repo("message", MessageRepo)
    return await repo.get_outbound_log(boss_chat_id, to_chat_id, trigger_type, limit)
```

Seen contacts:

```python
async def upsert_seen_contact(
    chat_id: str, display_name: str = "", username: str = "",
    last_seen_chat: str | None = None,
) -> None:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    await repo.upsert_seen_contact(chat_id, display_name, username, last_seen_chat)


async def get_seen_contact(chat_id: str) -> dict | None:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.get_seen_contact(chat_id)


async def search_seen_contacts(query: str, limit: int = 20) -> list[dict]:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.search_seen_contacts(query, limit)


async def list_unlinked_seen_contacts(
    lark_people_chat_ids: set[str], days: int = 30, limit: int = 30,
) -> list[dict]:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.list_unlinked_seen_contacts(lark_people_chat_ids, days, limit)
```

- [ ] **Step 3: Reset `_repos` cache when DB closes**

Update `close_db`:

```python
async def close_db() -> None:
    global _db, _repos
    if _db is not None:
        await _db.close()
        _db = None
    _repos = {}
```

- [ ] **Step 4: Boot-check + smoke probe**

```bash
uv run python -c "import src.main; print('OK')"
```

Expected: `OK`.

```bash
uv run python <<'PY' 2>&1
import asyncio
from src import db
async def main():
    bosses = await db.get_all_bosses()
    print(f'bosses={len(bosses)}')
    if bosses:
        b = bosses[0]
        print(f'boss chat_id={b["chat_id"]} status={b.get("status")}')
        ext = await db.lookup_external_for_person(b["chat_id"])
        print(f'lookup={ext}')
        m = await db.get_all_memberships_for_boss(b["chat_id"])
        print(f'memberships={len(m)}')
asyncio.run(main())
PY
```

Expected:

```
bosses=1
boss chat_id=<UUID> status=active
lookup=('telegram', '5865065981')
memberships=2
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/unit/ -v 2>&1 | tail -30
```

Expected: every Phase 3 test passes (test_phase3_schema, test_crypto, test_boss_repo). Pre-existing tests should not regress.

- [ ] **Step 6: Commit**

```bash
git add src/db.py
git commit -m "refactor(db): convert to thin facade over repositories (zero behaviour change)"
```

---

## Task 11 — Review checkpoint (before booting bot)

**Files:** None.

- [ ] **Step 1: Run line-count check**

```bash
wc -l src/db.py src/repositories/*.py
```

`src/db.py` should drop from ~1177 lines to ~400 (mostly schema + facade wrappers + module-level state). Repos collectively cover the moved logic.

- [ ] **Step 2: Confirm zero stray references to db function bodies inside repos**

```bash
grep -n "from src import db\|from src.db" src/repositories/*.py
```

Expected: no matches. Repos must not depend on `src.db` (they take their connection through `__init__`).

- [ ] **Step 3: Manual review checklist**

Read through each new repo file and confirm:
- Every method's signature matches the parameter shape of the corresponding `db.py` function.
- Every method calls `await self._db.commit()` exactly when the original did (write paths only).
- No business logic leaked into repos (they should be pure SQL+row mapping).

- [ ] **Step 4: No commit needed unless changes were made.**

---

## Task 12 — Manual smoke test

**Files:** None.

- [ ] **Step 1: Boot the bot**

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Expected logs: `Application startup complete`, `Polling started as @<bot_username>`. No traceback.

- [ ] **Step 2: DM "hello"**

In Telegram, DM the bot: `hello`.

Expected: bot replies normally. Server log shows the `[chat:<UUID> ... sender:<UUID>] Received: hello` line and a successful `editMessageText 200`. No `AttributeError`, no `sqlite3.OperationalError`.

- [ ] **Step 3: Tool-using message**

DM the bot: `tạo nhắc nhở 1 phút nữa: phase 3 smoke test`. Wait one minute. Expected: bot DMs the reminder.

(Lark tools may still 403 — pre-existing token issue, ignore.)

- [ ] **Step 4: Stop the bot**

`Ctrl-C`.

- [ ] **Step 5: Final state check**

```bash
git log --oneline | head -15
git status
```

Expected: ~10 commits prefixed `feat(...)` / `refactor(...)`. Clean working tree.

---

## Done Criteria

- [ ] `src/repositories/` exists with `boss_repo.py`, `identity_repo.py`, `conversation_repo.py`, `membership_repo.py`, `message_repo.py`, `note_repo.py`, `reminder_repo.py`, `token_usage_repo.py`, `session_repo.py`, `approval_repo.py`, `review_repo.py`, `audit_repo.py`, plus `_base.py`.
- [ ] `src/db.py` is a thin facade — every original public function preserved, every body delegates to a repo.
- [ ] `bosses` table has `status`, `plan`, `expires_at`, `llm_provider`, `llm_model`, `llm_api_key_encrypted`, `embedding_provider`, `embedding_model`, `embedding_dim` columns.
- [ ] `audit_log` table exists.
- [ ] `Settings.boss_credential_encryption_key` field exists; `infrastructure/crypto.py` round-trip-tests pass.
- [ ] `python -c "import src.main"` succeeds.
- [ ] `pytest tests/unit/test_phase3_schema.py tests/unit/test_crypto.py tests/unit/test_boss_repo.py -v` is fully green.
- [ ] Manual smoke test (Task 12) passes for DM + reminder flow.
- [ ] Caller files (`agent.py`, `tools/*.py`, `onboarding.py`, `scheduler.py`, etc.) are unchanged. Phase 5 will rewire them via `AppContainer`.

When all checked, Phase 3 is done. Next: come back to writing-plans skill to draft Phase 4 (services + handlers + tool dispatcher + LLM provider abstraction).
