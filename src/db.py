import aiosqlite
from pathlib import Path

_db: aiosqlite.Connection | None = None

INITIAL_NOTE = """=== PERSONAL NOTE ===

Sếp:
  Tên: (chưa biết)
  Xưng hô: (chưa biết)
  Vai trò: (chưa biết)

Công ty:
  Tên: (chưa biết)
  Lĩnh vực: (chưa biết)

Team:
  (chưa biết)

Thói quen & lưu ý:
  (chưa biết)
""".strip()


async def init_db(db_path: str):
    global _db
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await _db.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at)"
    )
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS personal_note (
            chat_id INTEGER PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await _db.commit()


async def save_message(chat_id: int, role: str, content: str) -> int:
    cursor = await _db.execute(
        "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
        (chat_id, role, content),
    )
    await _db.commit()
    return cursor.lastrowid


async def get_recent(chat_id: int, limit: int = 5) -> list[dict]:
    async with _db.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def get_personal_note(chat_id: int) -> str:
    async with _db.execute(
        "SELECT content FROM personal_note WHERE chat_id = ?", (chat_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row["content"] if row else INITIAL_NOTE


async def update_personal_note(chat_id: int, content: str):
    await _db.execute(
        """INSERT INTO personal_note (chat_id, content, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(chat_id) DO UPDATE SET content = ?, updated_at = CURRENT_TIMESTAMP""",
        (chat_id, content, content),
    )
    await _db.commit()


async def get_all_chat_ids() -> list[int]:
    async with _db.execute(
        "SELECT DISTINCT chat_id FROM messages"
    ) as cursor:
        rows = await cursor.fetchall()
    return [r["chat_id"] for r in rows]


async def close_db():
    if _db:
        await _db.close()
