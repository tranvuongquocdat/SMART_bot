"""Thin facade over `src.repositories.*`.

Each public function preserves its pre-Phase-3 signature and behaviour but
delegates to a singleton repo instance. Phase 5 will replace the singleton
pattern with `AppContainer` constructor injection.

Schema definition (`_init_schema`) and connection lifecycle (`get_db`,
`close_db`) live here because they are owned by the application boot path.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

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


# Notification kind table — kept for any external code that imported it.
_NOTIFICATION_KIND_COL = {
    "assigned": "notified_assigned",
    "24h": "notified_24h",
    "2h": "notified_2h",
}


def _notification_col(kind: str) -> str:
    col = _NOTIFICATION_KIND_COL.get(kind)
    if col is None:
        raise ValueError(f"Unknown notification kind: {kind!r}")
    return col


_REVIEW_ALLOWED_COLS = frozenset({
    "cron_time", "content_type", "custom_prompt", "enabled", "timezone"
})


_db: Optional[aiosqlite.Connection] = None
_repos: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

async def get_db(db_path: str = "data/history.db") -> aiosqlite.Connection:
    global _db
    if _db is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        await _init_schema(_db)
    return _db


async def close_db() -> None:
    global _db, _repos
    if _db is not None:
        await _db.close()
        _db = None
    _repos = {}


async def _init_schema(db: aiosqlite.Connection) -> None:
    """Canonical post-Phase-3 schema. All chat-id-shaped columns are TEXT
    (UUID internal_id from external_identity / conversation mapping tables).
    `bosses` carries forward-compat columns (status, plan, llm_*) defaulted
    to no-op values so existing flows are unchanged.
    """
    # ---- Pre-init: migrate pre-multi-provider INTEGER chat_id tables to TEXT.
    # Tables below were created with INTEGER PRIMARY KEY back when only
    # Telegram (numeric chat_id) was supported. Multi-provider uses internal
    # UUIDs (TEXT), which raise `datatype mismatch` against rowid-aliased
    # INTEGER PRIMARY KEY columns. Rename the legacy table out of the way;
    # executescript below recreates it with the canonical TEXT schema, and we
    # copy data back after.
    legacy_renamed: list[str] = []
    for table in (
        "onboarding_state", "seen_contacts",
        "bosses", "people_map", "group_map",
    ):
        cur = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        row = await cur.fetchone()
        await cur.close()
        if row and "INTEGER PRIMARY KEY" in row[0]:
            await db.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy_int")
            legacy_renamed.append(table)

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

    # ---- Phase 3 forward-compat additions (idempotent ALTER for post-Phase-2 DBs) ----
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

    # `people_map` is legacy and not in the canonical schema (its responsibilities
    # moved to `memberships`), but a few legacy code paths still hit it. If we
    # renamed it above, recreate it with TEXT PK so legacy reads/writes stay
    # alive instead of failing.
    if "people_map" in legacy_renamed:
        await db.execute("""
            CREATE TABLE people_map (
                chat_id      TEXT PRIMARY KEY,
                boss_chat_id TEXT NOT NULL,
                type         TEXT NOT NULL CHECK (type IN ('boss', 'member', 'partner')),
                name         TEXT DEFAULT ''
            )
        """)

    # Copy data from legacy INTEGER tables into the new TEXT-typed ones, then drop.
    # SQLite auto-converts INTEGER values to TEXT during INSERT. Use explicit
    # column lists (derived from the new table) since column order can differ
    # between legacy and canonical schemas.
    for table in legacy_renamed:
        cur = await db.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in await cur.fetchall()]
        await cur.close()
        col_list = ", ".join(cols)
        await db.execute(
            f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {table}_legacy_int"
        )
        await db.execute(f"DROP TABLE {table}_legacy_int")

    await db.commit()


# ---------------------------------------------------------------------------
# Repository singletons (lazy-built). Phase 5 replaces this with AppContainer.
# ---------------------------------------------------------------------------

async def _repo(name: str, cls):
    """Singleton repo over the lazy-built global connection."""
    if name not in _repos:
        db = await get_db()
        _repos[name] = cls(db)
    return _repos[name]


def _ephemeral_repo(db_or_none, cls):
    """Repo bound to a caller-supplied connection.

    Some legacy facade signatures pass `db` as their first argument (e.g.
    `upsert_membership(db, ...)` in tests using an in-memory connection).
    For those, we construct a fresh repo around the caller's connection
    rather than the singleton so test isolation holds. If `db_or_none` is
    None or not a Connection, we fall back to the singleton.
    """
    if isinstance(db_or_none, aiosqlite.Connection):
        return cls(db_or_none)
    return None


# ---------------------------------------------------------------------------
# bosses
# ---------------------------------------------------------------------------

async def get_boss(db_or_chat_id, chat_id_or_path=None) -> Optional[dict]:
    """get_boss(chat_id) or get_boss(db, chat_id) — both calling styles supported."""
    if isinstance(db_or_chat_id, aiosqlite.Connection):
        chat_id = chat_id_or_path
        repo = BossRepo(db_or_chat_id)
    else:
        chat_id = db_or_chat_id
        repo = await _repo("boss", BossRepo)
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


# ---------------------------------------------------------------------------
# external_identity / conversation
# ---------------------------------------------------------------------------

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


async def get_conversation_kind(
    internal_chat_id: str, db_path: str = "data/history.db",
) -> str:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    return await repo.get_kind(internal_chat_id)


async def lookup_person_by_external(
    provider: str, external_id: str, db_path: str = "data/history.db",
) -> str | None:
    repo: IdentityRepo = await _repo("identity", IdentityRepo)
    return await repo.lookup_person_by_external(provider, external_id)


async def lookup_conversation_by_external(
    provider: str, external_id: str, db_path: str = "data/history.db",
) -> str | None:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    return await repo.lookup_conversation_by_external(provider, external_id)


# ---------------------------------------------------------------------------
# legacy people_map wrappers (delegate to memberships)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# group_map
# ---------------------------------------------------------------------------

async def get_group(db_or_group_chat_id, group_chat_id_or_path=None) -> Optional[dict]:
    """get_group(group_chat_id) or get_group(db, group_chat_id)."""
    if isinstance(db_or_group_chat_id, aiosqlite.Connection):
        group_chat_id = group_chat_id_or_path
        repo = ConversationRepo(db_or_group_chat_id)
    else:
        group_chat_id = db_or_group_chat_id
        repo = await _repo("conversation", ConversationRepo)
    return await repo.get_group(group_chat_id)


async def add_group(
    group_chat_id: str, boss_chat_id: str, group_name: str = "",
    project_id: str | None = None,
) -> None:
    repo: ConversationRepo = await _repo("conversation", ConversationRepo)
    await repo.add_group(group_chat_id, boss_chat_id, group_name, project_id)


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# reminders
# ---------------------------------------------------------------------------

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
    repo = _ephemeral_repo(db, ReminderRepo) or await _repo("reminder", ReminderRepo)
    await repo.sync_from_lark(sqlite_id, content, status)


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

async def log_token_usage(
    boss_chat_id: str, source: str,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    db_path: str = "data/history.db",
) -> None:
    repo: TokenUsageRepo = await _repo("token_usage", TokenUsageRepo)
    await repo.log(boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens)


# ---------------------------------------------------------------------------
# sessions + onboarding_state
# ---------------------------------------------------------------------------

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


async def has_onboarding_state(chat_id: str) -> bool:
    repo: SessionRepo = await _repo("session", SessionRepo)
    return await repo.has_onboarding_state(chat_id)


async def save_onboarding_state(chat_id: str, state: dict) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.save_onboarding_state(chat_id, state)


async def clear_onboarding_state(chat_id: str) -> None:
    repo: SessionRepo = await _repo("session", SessionRepo)
    await repo.clear_onboarding_state(chat_id)


# ---------------------------------------------------------------------------
# memberships
# ---------------------------------------------------------------------------

async def get_memberships(user_id_or_db, user_id_str=None) -> list[dict]:
    """get_memberships(user_id_str) or get_memberships(db, user_id_str)."""
    if isinstance(user_id_or_db, aiosqlite.Connection):
        uid = user_id_str
        repo = MembershipRepo(user_id_or_db)
    else:
        uid = user_id_or_db
        repo = await _repo("membership", MembershipRepo)
    return await repo.list_for_user(uid)


async def get_all_memberships_for_boss(boss_chat_id: str) -> list[dict]:
    repo: MembershipRepo = await _repo("membership", MembershipRepo)
    return await repo.list_for_boss(boss_chat_id)


async def get_membership(db, chat_id: str, boss_chat_id: str) -> dict | None:
    repo = _ephemeral_repo(db, MembershipRepo) or await _repo("membership", MembershipRepo)
    return await repo.get(chat_id, boss_chat_id)


async def upsert_membership(db, chat_id: str, boss_chat_id: str, person_type: str,
                             name: str, status: str = "active",
                             request_info: str = None, lark_record_id: str = None):
    repo = _ephemeral_repo(db, MembershipRepo) or await _repo("membership", MembershipRepo)
    await repo.upsert(chat_id, boss_chat_id, person_type, name, status, request_info, lark_record_id)


async def delete_membership(db, chat_id: str, boss_chat_id: str):
    repo = _ephemeral_repo(db, MembershipRepo) or await _repo("membership", MembershipRepo)
    await repo.delete(chat_id, boss_chat_id)


# ---------------------------------------------------------------------------
# pending_approvals + task_notifications
# ---------------------------------------------------------------------------

async def create_approval(db, boss_chat_id: str, requester_id: str,
                           task_record_id: str, payload: str) -> int:
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    return await repo.create(boss_chat_id, requester_id, task_record_id, payload)


async def get_pending_approvals(db, boss_chat_id: str) -> list[dict]:
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    return await repo.get_pending(boss_chat_id)


async def update_approval_status(db, approval_id: int, status: str):
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    await repo.update_status(approval_id, status)


async def upsert_task_notification(db, task_record_id: str, boss_chat_id: str,
                                    assignee_chat_id: str = None):
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    await repo.upsert_task_notification(task_record_id, boss_chat_id, assignee_chat_id)


async def mark_notification_sent(db, task_record_id: str, boss_chat_id: str, kind: str):
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    await repo.mark_notification_sent(task_record_id, boss_chat_id, kind)


async def get_unnotified_tasks(db, boss_chat_id: str, kind: str) -> list[dict]:
    repo = _ephemeral_repo(db, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    return await repo.get_unnotified(boss_chat_id, kind)


async def get_unnotified_overdue_tasks(db_conn, boss_chat_id: str) -> list[dict]:
    repo = _ephemeral_repo(db_conn, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    return await repo.get_unnotified_overdue(boss_chat_id)


async def mark_overdue_notified(db_conn, task_record_id: str, boss_chat_id: str) -> None:
    repo = _ephemeral_repo(db_conn, ApprovalRepo) or await _repo("approval", ApprovalRepo)
    await repo.mark_overdue_notified(task_record_id, boss_chat_id)


# ---------------------------------------------------------------------------
# scheduled_reviews
# ---------------------------------------------------------------------------

async def list_scheduled_reviews(db, owner_id: str) -> list[dict]:
    repo = _ephemeral_repo(db, ReviewRepo) or await _repo("review", ReviewRepo)
    return await repo.list_for_owner(owner_id)


async def create_scheduled_review(db, owner_id: str, cron_time: str,
                                   content_type: str, custom_prompt: str = None) -> int:
    repo = _ephemeral_repo(db, ReviewRepo) or await _repo("review", ReviewRepo)
    return await repo.create(owner_id, cron_time, content_type, custom_prompt)


async def update_scheduled_review(db, review_id: int, owner_id: str = None, **kwargs) -> bool:
    repo = _ephemeral_repo(db, ReviewRepo) or await _repo("review", ReviewRepo)
    return await repo.update(review_id, owner_id, **kwargs)


async def delete_scheduled_review(db, review_id: int, owner_id: str = None) -> bool:
    repo = _ephemeral_repo(db, ReviewRepo) or await _repo("review", ReviewRepo)
    return await repo.delete(review_id, owner_id)


async def get_all_enabled_reviews(db) -> list[dict]:
    repo = _ephemeral_repo(db, ReviewRepo) or await _repo("review", ReviewRepo)
    return await repo.list_all_enabled()


# ---------------------------------------------------------------------------
# outbound_messages
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# seen_contacts
# ---------------------------------------------------------------------------

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
