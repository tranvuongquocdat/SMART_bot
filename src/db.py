import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    """)
    await db.commit()


# ---------------------------------------------------------------------------
# bosses
# ---------------------------------------------------------------------------

async def get_boss(chat_id: int, db_path: str = "data/history.db") -> Optional[dict]:
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
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    await db.execute(
        """
        INSERT INTO bosses
            (chat_id, name, company, lark_base_token, lark_table_people,
             lark_table_tasks, lark_table_projects, lark_table_ideas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            name                = excluded.name,
            company             = excluded.company,
            lark_base_token     = excluded.lark_base_token,
            lark_table_people   = excluded.lark_table_people,
            lark_table_tasks    = excluded.lark_table_tasks,
            lark_table_projects = excluded.lark_table_projects,
            lark_table_ideas    = excluded.lark_table_ideas
        """,
        (chat_id, name, company, lark_base_token, lark_table_people,
         lark_table_tasks, lark_table_projects, lark_table_ideas),
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

async def get_group(group_chat_id: int, db_path: str = "data/history.db") -> Optional[dict]:
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
    db_path: str = "data/history.db",
) -> None:
    db = await get_db(db_path)
    await db.execute(
        """
        INSERT INTO group_map (group_chat_id, boss_chat_id, group_name)
        VALUES (?, ?, ?)
        ON CONFLICT(group_chat_id) DO UPDATE SET
            boss_chat_id = excluded.boss_chat_id,
            group_name   = excluded.group_name
        """,
        (group_chat_id, boss_chat_id, group_name),
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
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
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
        now = datetime.utcnow()
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


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------

async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
