import aiosqlite
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


async def get_db(db_path: str = "data/history.db") -> aiosqlite.Connection:
    global _db
    if _db is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        await _init_schema(_db)
    return _db


async def _init_schema(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS bosses (
            chat_id             INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            company             TEXT DEFAULT '',
            lark_base_token     TEXT,
            lark_table_people   TEXT,
            lark_table_tasks    TEXT,
            lark_table_projects TEXT,
            lark_table_ideas    TEXT,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS people_map (
            chat_id      INTEGER PRIMARY KEY,
            boss_chat_id INTEGER NOT NULL REFERENCES bosses(chat_id),
            type         TEXT NOT NULL CHECK (type IN ('boss', 'member', 'partner')),
            name         TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS group_map (
            group_chat_id INTEGER PRIMARY KEY,
            boss_chat_id  INTEGER NOT NULL REFERENCES bosses(chat_id),
            group_name    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id    INTEGER NOT NULL,
            sender_id  INTEGER,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_messages_chat_created
            ON messages (chat_id, created_at);

        CREATE TABLE IF NOT EXISTS notes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id INTEGER NOT NULL REFERENCES bosses(chat_id),
            type         TEXT NOT NULL CHECK (type IN ('personal', 'project', 'group')),
            ref_id       TEXT NOT NULL,
            content      TEXT NOT NULL,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (boss_chat_id, type, ref_id)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id    INTEGER NOT NULL REFERENCES bosses(chat_id),
            target_chat_id  INTEGER,
            target_name     TEXT DEFAULT '',
            content         TEXT NOT NULL,
            remind_at       TIMESTAMP NOT NULL,
            status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id      INTEGER NOT NULL,
            source            TEXT NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_token_usage_boss_created
            ON token_usage (boss_chat_id, created_at);
    """)

    # New tables for many-to-many memberships and additional features
    await db.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            chat_id         TEXT NOT NULL,
            boss_chat_id    TEXT NOT NULL,
            person_type     TEXT NOT NULL,
            name            TEXT,
            lark_record_id  TEXT,
            status          TEXT DEFAULT 'pending',
            request_info    TEXT,
            requested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at     TIMESTAMP,
            PRIMARY KEY (chat_id, boss_chat_id)
        )
    """)

    await db.execute("""
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
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS task_notifications (
            task_record_id      TEXT NOT NULL,
            boss_chat_id        TEXT NOT NULL,
            assignee_chat_id    TEXT,
            notified_assigned   INTEGER DEFAULT 0,
            notified_24h        INTEGER DEFAULT 0,
            notified_2h         INTEGER DEFAULT 0,
            PRIMARY KEY (task_record_id, boss_chat_id)
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reviews (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id      TEXT NOT NULL,
            cron_time     TEXT NOT NULL,
            content_type  TEXT NOT NULL,
            custom_prompt TEXT,
            enabled       INTEGER DEFAULT 1,
            timezone      TEXT DEFAULT 'Asia/Ho_Chi_Minh',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await _migrate_schema(db)
    await db.commit()


async def _migrate_schema(db: aiosqlite.Connection) -> None:
    """Apply additive SQLite migrations (CREATE IF NOT EXISTS does not alter old tables)."""
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'"
    ) as cur:
        if not await cur.fetchone():
            return
    async with db.execute("PRAGMA table_info(messages)") as cur:
        rows = await cur.fetchall()
    col_names = {r[1] for r in rows}
    if "sender_id" not in col_names:
        await db.execute("ALTER TABLE messages ADD COLUMN sender_id INTEGER")

    # Add new columns to bosses
    for col, definition in [
        ("lark_table_reminders", "TEXT DEFAULT ''"),
        ("lark_table_notes",     "TEXT DEFAULT ''"),
    ]:
        try:
            await db.execute(f"ALTER TABLE bosses ADD COLUMN {col} {definition}")
            await db.commit()
        except Exception as exc:
            if "duplicate column name" not in str(exc):
                raise

    # Migrate existing people_map -> memberships
    try:
        await db.execute("""
            INSERT OR IGNORE INTO memberships (chat_id, boss_chat_id, person_type, name, status)
            SELECT chat_id, boss_chat_id, type, name, 'active'
            FROM people_map
        """)
        await db.commit()
    except Exception as exc:
        # Only suppress if people_map doesn't exist yet (fresh install)
        if "no such table" not in str(exc).lower():
            raise

    # Add language to bosses
    for col, definition in [
        ("language", "TEXT DEFAULT 'en'"),
    ]:
        try:
            # f-string safe: col/definition are hardcoded above, SQLite doesn't support parameterized DDL
            await db.execute(f"ALTER TABLE bosses ADD COLUMN {col} {definition}")
            await db.commit()
        except Exception as exc:
            if "duplicate column name" not in str(exc):
                raise

    # Add language to memberships
    try:
        await db.execute("ALTER TABLE memberships ADD COLUMN language TEXT DEFAULT NULL")
        await db.commit()
    except Exception as exc:
        if "duplicate column name" not in str(exc):
            raise

    # Sessions table (workspace preference + reset flow state)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id     INTEGER NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
    """)

    # Add project_id to group_map
    try:
        await db.execute("ALTER TABLE group_map ADD COLUMN project_id TEXT DEFAULT NULL")
        await db.commit()
    except Exception as exc:
        if "duplicate column name" not in str(exc):
            raise

    # Add group_chat_id to scheduled_reviews
    try:
        await db.execute("ALTER TABLE scheduled_reviews ADD COLUMN group_chat_id INTEGER DEFAULT NULL")
        await db.commit()
    except Exception as exc:
        if "duplicate column name" not in str(exc):
            raise


# ---------------------------------------------------------------------------
# bosses
# ---------------------------------------------------------------------------

async def get_boss(db_or_chat_id, chat_id_or_path=None) -> Optional[dict]:
    """get_boss(chat_id) or get_boss(db, chat_id) — both calling styles supported."""
    import aiosqlite as _aiosqlite
    if isinstance(db_or_chat_id, _aiosqlite.Connection):
        db = db_or_chat_id
        chat_id = chat_id_or_path
    else:
        chat_id = db_or_chat_id
        db_path = chat_id_or_path if isinstance(chat_id_or_path, str) else "data/history.db"
        db = await get_db(db_path)
    async with db.execute("SELECT * FROM bosses WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_boss(
    chat_id: int,
    name: str,
    company: str = "",
    lark_base_token: Optional[str] = None,
    lark_table_people: Optional[str] = None,
    lark_table_tasks: Optional[str] = None,
    lark_table_projects: Optional[str] = None,
    lark_table_ideas: Optional[str] = None,
    lark_table_reminders: Optional[str] = None,
    lark_table_notes: Optional[str] = None,
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    await db.execute(
        """
        INSERT INTO bosses
            (chat_id, name, company, lark_base_token, lark_table_people,
             lark_table_tasks, lark_table_projects, lark_table_ideas,
             lark_table_reminders, lark_table_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            name                 = excluded.name,
            company              = excluded.company,
            lark_base_token      = excluded.lark_base_token,
            lark_table_people    = excluded.lark_table_people,
            lark_table_tasks     = excluded.lark_table_tasks,
            lark_table_projects  = excluded.lark_table_projects,
            lark_table_ideas     = excluded.lark_table_ideas,
            lark_table_reminders = excluded.lark_table_reminders,
            lark_table_notes     = excluded.lark_table_notes
        """,
        (chat_id, name, company, lark_base_token, lark_table_people,
         lark_table_tasks, lark_table_projects, lark_table_ideas,
         lark_table_reminders, lark_table_notes),
    )
    await db.commit()


async def get_all_bosses(db_path: str = "data/history.db") -> list[dict]:
    db = await get_db(db_path)
    async with db.execute("SELECT * FROM bosses ORDER BY created_at") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# people_map
# ---------------------------------------------------------------------------

async def get_person(chat_id: int, db_path: str = "data/history.db") -> Optional[dict]:
    db = await get_db(db_path)
    async with db.execute("SELECT * FROM people_map WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def add_person(
    chat_id: int,
    boss_chat_id: int,
    person_type: str,
    name: str = "",
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    await db.execute(
        """
        INSERT INTO people_map (chat_id, boss_chat_id, type, name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            boss_chat_id = excluded.boss_chat_id,
            type         = excluded.type,
            name         = excluded.name
        """,
        (chat_id, boss_chat_id, person_type, name),
    )
    await db.commit()


async def delete_person(chat_id: int, db_path: str = "data/history.db") -> None:
    db = await get_db(db_path)
    await db.execute("DELETE FROM people_map WHERE chat_id = ?", (chat_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# group_map
# ---------------------------------------------------------------------------

async def get_group(db_or_group_chat_id, group_chat_id_or_path=None) -> Optional[dict]:
    """get_group(group_chat_id) or get_group(db, group_chat_id) — both calling styles supported."""
    import aiosqlite as _aiosqlite
    if isinstance(db_or_group_chat_id, _aiosqlite.Connection):
        db = db_or_group_chat_id
        group_chat_id = group_chat_id_or_path
    else:
        group_chat_id = db_or_group_chat_id
        db_path = group_chat_id_or_path if isinstance(group_chat_id_or_path, str) else "data/history.db"
        db = await get_db(db_path)
    async with db.execute(
        "SELECT * FROM group_map WHERE group_chat_id = ?", (group_chat_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def add_group(
    group_chat_id: int,
    boss_chat_id: int,
    group_name: str = "",
    project_id: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO group_map (group_chat_id, boss_chat_id, group_name, project_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(group_chat_id) DO UPDATE SET
            boss_chat_id = excluded.boss_chat_id,
            group_name   = excluded.group_name,
            project_id   = excluded.project_id
        """,
        (group_chat_id, boss_chat_id, group_name, project_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

async def save_message(
    chat_id: int,
    role: str,
    content: str,
    sender_id: Optional[int] = None,
    db_path: str = "data/history.db",
) -> int:
    db = await get_db(db_path)
    cur = await db.execute(
        "INSERT INTO messages (chat_id, sender_id, role, content) VALUES (?, ?, ?, ?)",
        (chat_id, sender_id, role, content),
    )
    await db.commit()
    return cur.lastrowid


async def get_recent(
    chat_id: int,
    limit: int = 8,
    db_path: str = "data/history.db",
) -> list[dict]:
    db = await get_db(db_path)
    async with db.execute(
        """
        SELECT * FROM (
            SELECT * FROM messages
            WHERE chat_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ) ORDER BY created_at ASC
        """,
        (chat_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

async def get_note(
    boss_chat_id: int,
    note_type: str,
    ref_id: str,
    db_path: str = "data/history.db",
) -> Optional[dict]:
    db = await get_db(db_path)
    async with db.execute(
        "SELECT * FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
        (boss_chat_id, note_type, ref_id),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def update_note(
    boss_chat_id: int,
    note_type: str,
    ref_id: str,
    content: str,
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    await db.execute(
        """
        INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(boss_chat_id, type, ref_id) DO UPDATE SET
            content    = excluded.content,
            updated_at = excluded.updated_at
        """,
        (boss_chat_id, note_type, ref_id, content, now),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# reminders
# ---------------------------------------------------------------------------

async def create_reminder(
    boss_chat_id: int,
    content: str,
    remind_at: datetime,
    target_chat_id: Optional[int] = None,
    target_name: str = "",
    db_path: str = "data/history.db",
) -> int:
    db = await get_db(db_path)
    remind_at_str = remind_at.isoformat(sep=" ", timespec="seconds")
    cur = await db.execute(
        "INSERT INTO reminders (boss_chat_id, target_chat_id, target_name, content, remind_at) VALUES (?, ?, ?, ?, ?)",
        (boss_chat_id, target_chat_id, target_name, content, remind_at_str),
    )
    await db.commit()
    return cur.lastrowid


async def get_due_reminders(
    now: Optional[datetime] = None,
    db_path: str = "data/history.db",
) -> list[dict]:
    db = await get_db(db_path)
    if now is None:
        now = datetime.now(timezone.utc)
    now_str = now.isoformat(sep=" ", timespec="seconds")
    async with db.execute(
        "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ? ORDER BY remind_at",
        (now_str,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def mark_reminder_done(reminder_id: int, db_path: str = "data/history.db") -> None:
    db = await get_db(db_path)
    await db.execute(
        "UPDATE reminders SET status = 'done' WHERE id = ?",
        (reminder_id,),
    )
    await db.commit()


async def list_reminders(
    boss_chat_id: int,
    status: str = "pending",
    limit: int = 50,
    db_path: str = "data/history.db",
) -> list[dict]:
    db = await get_db(db_path)
    lim = max(1, min(limit, 200))
    if status == "all":
        async with db.execute(
            """
            SELECT * FROM reminders
            WHERE boss_chat_id = ?
            ORDER BY remind_at ASC
            LIMIT ?
            """,
            (boss_chat_id, lim),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            """
            SELECT * FROM reminders
            WHERE boss_chat_id = ? AND status = ?
            ORDER BY remind_at ASC
            LIMIT ?
            """,
            (boss_chat_id, status, lim),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def update_reminder(
    reminder_id: int,
    boss_chat_id: int,
    *,
    content: Optional[str] = None,
    remind_at: Optional[datetime] = None,
    update_target: bool = False,
    target_chat_id: Optional[int] = None,
    target_name: str = "",
    db_path: str = "data/history.db",
) -> bool:
    db = await get_db(db_path)
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
    params.extend([reminder_id, boss_chat_id])
    sql = f"UPDATE reminders SET {', '.join(sets)} WHERE id = ? AND boss_chat_id = ?"
    cur = await db.execute(sql, params)
    await db.commit()
    return cur.rowcount > 0


async def delete_reminder(
    reminder_id: int,
    boss_chat_id: int,
    db_path: str = "data/history.db",
) -> bool:
    db = await get_db(db_path)
    cur = await db.execute(
        "DELETE FROM reminders WHERE id = ? AND boss_chat_id = ?",
        (reminder_id, boss_chat_id),
    )
    await db.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# token_usage
# ---------------------------------------------------------------------------

async def log_token_usage(
    boss_chat_id: int,
    source: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    await db.execute(
        "INSERT INTO token_usage (boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens) VALUES (?, ?, ?, ?, ?)",
        (boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

async def set_session(user_id: int, key: str, value: str, ttl_minutes: int = 30) -> None:
    from datetime import datetime, timedelta, timezone
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO sessions (user_id, key, value, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, key, value, expires),
    )
    await db.commit()


async def get_session(user_id: int, key: str) -> str | None:
    from datetime import datetime, timezone
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    async with db.execute(
        "SELECT value FROM sessions WHERE user_id = ? AND key = ? AND expires_at > ?",
        (user_id, key, now),
    ) as cur:
        row = await cur.fetchone()
    return row["value"] if row else None


async def delete_session(user_id: int, key: str) -> None:
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE user_id = ? AND key = ?", (user_id, key))
    await db.commit()


# ---------------------------------------------------------------------------
# memberships
# ---------------------------------------------------------------------------

async def get_memberships(user_id_or_db, user_id_str=None) -> list[dict]:
    """get_memberships(user_id_str) or get_memberships(db, user_id_str)."""
    import aiosqlite as _aiosqlite
    if isinstance(user_id_or_db, _aiosqlite.Connection):
        db = user_id_or_db
        uid = user_id_str
    else:
        db = await get_db()
        uid = user_id_or_db
    async with db.execute(
        "SELECT * FROM memberships WHERE chat_id = ? AND status = 'active'",
        (str(uid),),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_memberships_for_boss(boss_chat_id: str) -> list[dict]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM memberships WHERE boss_chat_id = ?",
        (str(boss_chat_id),),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_membership(db, chat_id: str, boss_chat_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
        (str(chat_id), str(boss_chat_id))
    ) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_membership(db, chat_id: str, boss_chat_id: str, person_type: str,
                             name: str, status: str = "active",
                             request_info: str = None, lark_record_id: str = None):
    await db.execute("""
        INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status, request_info, lark_record_id, requested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id, boss_chat_id) DO UPDATE SET
            person_type = excluded.person_type,
            name = excluded.name,
            status = excluded.status,
            request_info = COALESCE(excluded.request_info, request_info),
            lark_record_id = COALESCE(excluded.lark_record_id, lark_record_id),
            approved_at = CASE WHEN excluded.status = 'active' THEN CURRENT_TIMESTAMP ELSE approved_at END
    """, (str(chat_id), str(boss_chat_id), person_type, name, status, request_info, lark_record_id))
    await db.commit()


async def delete_membership(db, chat_id: str, boss_chat_id: str):
    await db.execute(
        "DELETE FROM memberships WHERE chat_id = ? AND boss_chat_id = ?",
        (str(chat_id), str(boss_chat_id))
    )
    await db.commit()


# ---------------------------------------------------------------------------
# pending_approvals
# ---------------------------------------------------------------------------

async def create_approval(db, boss_chat_id: str, requester_id: str,
                           task_record_id: str, payload: str) -> int:
    from datetime import datetime, timedelta, timezone
    expires = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    async with db.execute("""
        INSERT INTO pending_approvals (boss_chat_id, requester_id, task_record_id, payload, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(boss_chat_id), str(requester_id), task_record_id, payload, expires)) as cur:
        row_id = cur.lastrowid
    await db.commit()
    return row_id


async def get_pending_approvals(db, boss_chat_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending' ORDER BY created_at",
        (str(boss_chat_id),)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def update_approval_status(db, approval_id: int, status: str):
    await db.execute(
        "UPDATE pending_approvals SET status = ? WHERE id = ?",
        (status, approval_id)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# task_notifications
# ---------------------------------------------------------------------------

async def upsert_task_notification(db, task_record_id: str, boss_chat_id: str,
                                    assignee_chat_id: str = None):
    await db.execute("""
        INSERT OR IGNORE INTO task_notifications (task_record_id, boss_chat_id, assignee_chat_id)
        VALUES (?, ?, ?)
    """, (task_record_id, str(boss_chat_id), str(assignee_chat_id) if assignee_chat_id else None))
    await db.commit()


async def mark_notification_sent(db, task_record_id: str, boss_chat_id: str, kind: str):
    col = _notification_col(kind)
    await db.execute(
        f"UPDATE task_notifications SET {col} = 1 WHERE task_record_id = ? AND boss_chat_id = ?",
        (task_record_id, str(boss_chat_id))
    )
    await db.commit()


async def get_unnotified_tasks(db, boss_chat_id: str, kind: str) -> list[dict]:
    col = _notification_col(kind)
    async with db.execute(
        f"SELECT * FROM task_notifications WHERE boss_chat_id = ? AND {col} = 0",
        (str(boss_chat_id),)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ---------------------------------------------------------------------------
# scheduled_reviews
# ---------------------------------------------------------------------------

async def list_scheduled_reviews(db, owner_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM scheduled_reviews WHERE owner_id = ? ORDER BY cron_time",
        (str(owner_id),)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def create_scheduled_review(db, owner_id: str, cron_time: str,
                                   content_type: str, custom_prompt: str = None) -> int:
    async with db.execute("""
        INSERT INTO scheduled_reviews (owner_id, cron_time, content_type, custom_prompt)
        VALUES (?, ?, ?, ?)
    """, (str(owner_id), cron_time, content_type, custom_prompt)) as cur:
        await db.commit()
        return cur.lastrowid


async def update_scheduled_review(db, review_id: int, owner_id: str = None, **kwargs) -> bool:
    invalid = set(kwargs) - _REVIEW_ALLOWED_COLS
    if invalid:
        raise ValueError(f"Invalid column(s) for scheduled_reviews: {invalid}")
    if not kwargs:
        return False
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    if owner_id is not None:
        async with db.execute(
            f"UPDATE scheduled_reviews SET {sets} WHERE id = ? AND owner_id = ?",
            (*kwargs.values(), review_id, str(owner_id))
        ) as cur:
            await db.commit()
            return cur.rowcount > 0
    await db.execute(
        f"UPDATE scheduled_reviews SET {sets} WHERE id = ?",
        (*kwargs.values(), review_id)
    )
    await db.commit()
    return True


async def delete_scheduled_review(db, review_id: int, owner_id: str = None) -> bool:
    if owner_id is not None:
        async with db.execute(
            "DELETE FROM scheduled_reviews WHERE id = ? AND owner_id = ?",
            (review_id, str(owner_id))
        ) as cur:
            await db.commit()
            return cur.rowcount > 0
    await db.execute("DELETE FROM scheduled_reviews WHERE id = ?", (review_id,))
    await db.commit()
    return True


async def get_all_enabled_reviews(db) -> list[dict]:
    async with db.execute(
        "SELECT * FROM scheduled_reviews WHERE enabled = 1"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def sync_reminder_from_lark(db, sqlite_id: int, content: str, status: str):
    await db.execute(
        "UPDATE reminders SET content = ?, status = ? WHERE id = ?",
        (content, status, sqlite_id)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
