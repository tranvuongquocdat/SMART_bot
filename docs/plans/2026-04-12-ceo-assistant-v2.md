# CEO Assistant Agent V2 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Chuyển bot thư ký 1-1 sang hệ thống trợ lý giám đốc multi-user: 2 agents, 26 tools, group chat, auto-provision workspace, thinking UX.

**Architecture:** Secretary agent (realtime) + Advisor agent (chiến lược). Mỗi sếp 1 Lark Base riêng + Qdrant collections riêng. SQLite làm routing + notes + reminders. Telegram là kênh giao tiếp duy nhất (1-1 + group).

**Tech Stack:** Python 3.12, FastAPI, OpenAI GPT-5.4 (function calling), Qdrant (hybrid search), SQLite (aiosqlite), Lark Base API, Telegram Bot API, APScheduler, httpx, Cohere rerank, DuckDuckGo search.

**Design Doc:** `bàn luận logic.txt` — phần "BRAINSTORM V2" trở đi.

---

## Phase 1: Foundation — Database & Config Restructure

Mục tiêu: xây nền data layer mới, chưa đụng agent/tools.

---

### Task 1: Restructure SQLite schema

**Files:**
- Modify: `src/db.py` (toàn bộ file, viết lại)
- Modify: `src/config.py:4-27` (bỏ config Lark cứng)

**Step 1: Viết schema mới cho `src/db.py`**

Thay toàn bộ nội dung `src/db.py`. Bảng mới:

```python
import aiosqlite
from pathlib import Path

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS bosses (
    chat_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT DEFAULT '',
    lark_base_token TEXT NOT NULL,
    lark_table_people TEXT NOT NULL,
    lark_table_tasks TEXT NOT NULL,
    lark_table_projects TEXT NOT NULL,
    lark_table_ideas TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS people_map (
    chat_id INTEGER PRIMARY KEY,
    boss_chat_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('boss', 'member', 'partner')),
    name TEXT DEFAULT '',
    FOREIGN KEY (boss_chat_id) REFERENCES bosses(chat_id)
);

CREATE TABLE IF NOT EXISTS group_map (
    group_chat_id INTEGER PRIMARY KEY,
    boss_chat_id INTEGER NOT NULL,
    group_name TEXT DEFAULT '',
    FOREIGN KEY (boss_chat_id) REFERENCES bosses(chat_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    sender_id INTEGER,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_chat_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('personal', 'project', 'group')),
    ref_id TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(boss_chat_id, type, ref_id),
    FOREIGN KEY (boss_chat_id) REFERENCES bosses(chat_id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_chat_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    remind_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'done')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (boss_chat_id) REFERENCES bosses(chat_id)
);
"""


async def init_db(db_path: str):
    global _db
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    for statement in SCHEMA.split(";"):
        stmt = statement.strip()
        if stmt:
            await _db.execute(stmt)
    await _db.commit()


# --- Bosses ---

async def get_boss(chat_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM bosses WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_boss(chat_id: int, name: str, company: str,
                      lark_base_token: str, lark_table_people: str,
                      lark_table_tasks: str, lark_table_projects: str,
                      lark_table_ideas: str):
    await _db.execute(
        """INSERT INTO bosses (chat_id, name, company, lark_base_token,
           lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (chat_id, name, company, lark_base_token,
         lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas),
    )
    await _db.commit()


async def get_all_bosses() -> list[dict]:
    async with _db.execute("SELECT * FROM bosses") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- People Map ---

async def get_person(chat_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM people_map WHERE chat_id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def add_person(chat_id: int, boss_chat_id: int, person_type: str, name: str = ""):
    await _db.execute(
        """INSERT OR REPLACE INTO people_map (chat_id, boss_chat_id, type, name)
           VALUES (?, ?, ?, ?)""",
        (chat_id, boss_chat_id, person_type, name),
    )
    await _db.commit()


async def delete_person(chat_id: int):
    await _db.execute("DELETE FROM people_map WHERE chat_id = ?", (chat_id,))
    await _db.commit()


# --- Group Map ---

async def get_group(group_chat_id: int) -> dict | None:
    async with _db.execute("SELECT * FROM group_map WHERE group_chat_id = ?", (group_chat_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def add_group(group_chat_id: int, boss_chat_id: int, group_name: str = ""):
    await _db.execute(
        """INSERT OR REPLACE INTO group_map (group_chat_id, boss_chat_id, group_name)
           VALUES (?, ?, ?)""",
        (group_chat_id, boss_chat_id, group_name),
    )
    await _db.commit()


# --- Messages ---

async def save_message(chat_id: int, role: str, content: str, sender_id: int | None = None) -> int:
    cursor = await _db.execute(
        "INSERT INTO messages (chat_id, sender_id, role, content) VALUES (?, ?, ?, ?)",
        (chat_id, sender_id, role, content),
    )
    await _db.commit()
    return cursor.lastrowid


async def get_recent(chat_id: int, limit: int = 8) -> list[dict]:
    async with _db.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
        (chat_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# --- Notes ---

async def get_note(boss_chat_id: int, note_type: str, ref_id: str) -> str:
    async with _db.execute(
        "SELECT content FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
        (boss_chat_id, note_type, ref_id),
    ) as cur:
        row = await cur.fetchone()
    return row["content"] if row else ""


async def update_note(boss_chat_id: int, note_type: str, ref_id: str, content: str):
    await _db.execute(
        """INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(boss_chat_id, type, ref_id)
           DO UPDATE SET content = ?, updated_at = CURRENT_TIMESTAMP""",
        (boss_chat_id, note_type, ref_id, content, content),
    )
    await _db.commit()


# --- Reminders ---

async def create_reminder(boss_chat_id: int, content: str, remind_at: str):
    await _db.execute(
        "INSERT INTO reminders (boss_chat_id, content, remind_at) VALUES (?, ?, ?)",
        (boss_chat_id, content, remind_at),
    )
    await _db.commit()


async def get_due_reminders() -> list[dict]:
    async with _db.execute(
        "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= CURRENT_TIMESTAMP",
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def mark_reminder_done(reminder_id: int):
    await _db.execute(
        "UPDATE reminders SET status = 'done' WHERE id = ?", (reminder_id,)
    )
    await _db.commit()


async def close_db():
    if _db:
        await _db.close()
```

**Step 2: Update `src/config.py`**

Bỏ config Lark Base cứng (mỗi sếp có base riêng, lưu trong DB):

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str

    lark_app_id: str
    lark_app_secret: str
    # Bỏ: lark_base_app_token, lark_table_tasks, lark_table_ideas
    # Mỗi sếp có base riêng, lưu trong SQLite bosses table

    openai_api_key: str
    openai_chat_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"

    qdrant_url: str = "http://qdrant:6333"

    cohere_api_key: str

    db_path: str = "data/history.db"
    timezone: str = "Asia/Ho_Chi_Minh"
    recent_messages: int = 8
    rag_messages: int = 5

    model_config = {"env_file": ".env"}
```

**Step 3: Update `.env.example`**

```
TELEGRAM_BOT_TOKEN=
LARK_APP_ID=
LARK_APP_SECRET=
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-5.4
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
QDRANT_URL=http://qdrant:6333
COHERE_API_KEY=
DB_PATH=data/history.db
TIMEZONE=Asia/Ho_Chi_Minh
RECENT_MESSAGES=8
RAG_MESSAGES=5
```

**Step 4: Chạy thử khởi tạo DB**

Run: `python -c "import asyncio; from src.db import init_db; asyncio.run(init_db('data/test.db'))"`
Expected: không lỗi, file `data/test.db` được tạo với đúng schema.

**Step 5: Xóa test DB, commit**

```bash
rm data/test.db
git add src/db.py src/config.py .env.example
git commit -m "refactor: restructure SQLite schema for multi-boss support"
```

---

### Task 2: Lark Base provisioning service

**Files:**
- Modify: `src/services/lark.py` (thêm functions tạo base/table/fields, bỏ global _base_token)

**Step 1: Refactor `src/services/lark.py`**

Bỏ global `_base_token`. Mỗi function nhận `base_token` + `table_id` trực tiếp:

```python
import time
import httpx

_client: httpx.AsyncClient | None = None
_app_id: str = ""
_app_secret: str = ""

_tenant_token: str = ""
_token_expires: float = 0

LARK_API = "https://open.larksuite.com/open-apis"


async def init_lark(app_id: str, app_secret: str):
    global _client, _app_id, _app_secret
    _app_id = app_id
    _app_secret = app_secret
    _client = httpx.AsyncClient(timeout=15.0)


async def _get_token() -> str:
    global _tenant_token, _token_expires
    if time.time() < _token_expires:
        return _tenant_token
    resp = await _client.post(
        f"{LARK_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": _app_id, "app_secret": _app_secret},
    )
    resp.raise_for_status()
    data = resp.json()
    _tenant_token = data["tenant_access_token"]
    _token_expires = time.time() + data.get("expire", 7200) - 300
    return _tenant_token


async def _headers() -> dict:
    token = await _get_token()
    return {"Authorization": f"Bearer {token}"}


# --- Provisioning ---

async def create_base(name: str) -> dict:
    """Tạo Lark Base mới. Returns: {"app_token": "...", "default_table_id": "..."}"""
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps",
        headers=await _headers(),
        json={"name": name, "folder_token": ""},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark create_base error: {body}")
    return body["data"]["app"]


async def create_table(base_token: str, name: str, fields: list[dict]) -> str:
    """Tạo bảng trong base. Returns: table_id"""
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables",
        headers=await _headers(),
        json={"table": {"name": name, "default_view_name": f"All {name}", "fields": fields}},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark create_table error: {body}")
    return body["data"]["table_id"]


async def delete_table(base_token: str, table_id: str):
    """Xóa bảng (dùng để xóa default table sau khi provision)."""
    resp = await _client.delete(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}",
        headers=await _headers(),
    )
    resp.raise_for_status()


PEOPLE_FIELDS = [
    {"field_name": "Tên", "type": 1},
    {"field_name": "Tên gọi", "type": 1},
    {"field_name": "Chat ID", "type": 2},
    {"field_name": "Username", "type": 1},
    {"field_name": "Type", "type": 1},
    {"field_name": "Nhóm", "type": 1},
    {"field_name": "Vai trò", "type": 1},
    {"field_name": "Kỹ năng", "type": 1},
    {"field_name": "SĐT", "type": 1},
    {"field_name": "Ghi chú", "type": 1},
]

TASKS_FIELDS = [
    {"field_name": "Tên task", "type": 1},
    {"field_name": "Assignee", "type": 1},
    {"field_name": "Deadline", "type": 5},
    {"field_name": "Start time", "type": 5},
    {"field_name": "Location", "type": 1},
    {"field_name": "Priority", "type": 1},
    {"field_name": "Status", "type": 1},
    {"field_name": "Project", "type": 1},
    {"field_name": "Giao bởi", "type": 1},
    {"field_name": "Tin nhắn gốc", "type": 1},
    {"field_name": "Group ID", "type": 2},
]

PROJECTS_FIELDS = [
    {"field_name": "Tên dự án", "type": 1},
    {"field_name": "Mô tả", "type": 1},
    {"field_name": "Người phụ trách", "type": 1},
    {"field_name": "Thành viên", "type": 1},
    {"field_name": "Deadline", "type": 5},
    {"field_name": "Trạng thái", "type": 1},
]

IDEAS_FIELDS = [
    {"field_name": "Nội dung", "type": 1},
    {"field_name": "Tags", "type": 1},
    {"field_name": "Người tạo", "type": 1},
    {"field_name": "Project", "type": 1},
]


async def provision_workspace(company_name: str) -> dict:
    """
    Tạo workspace mới cho 1 sếp: base + 4 bảng.
    Returns: {
        "base_token": "...",
        "table_people": "...",
        "table_tasks": "...",
        "table_projects": "...",
        "table_ideas": "...",
    }
    """
    app = await create_base(f"{company_name} - AI Secretary")
    base_token = app["app_token"]
    default_table_id = app.get("default_table_id")

    table_people = await create_table(base_token, "People", PEOPLE_FIELDS)
    table_tasks = await create_table(base_token, "Tasks", TASKS_FIELDS)
    table_projects = await create_table(base_token, "Projects", PROJECTS_FIELDS)
    table_ideas = await create_table(base_token, "Ideas", IDEAS_FIELDS)

    # Xóa default table (Lark tự tạo 1 bảng mặc định khi tạo base)
    if default_table_id:
        try:
            await delete_table(base_token, default_table_id)
        except Exception:
            pass  # Không critical

    return {
        "base_token": base_token,
        "table_people": table_people,
        "table_tasks": table_tasks,
        "table_projects": table_projects,
        "table_ideas": table_ideas,
    }


# --- CRUD (nhận base_token + table_id) ---

async def create_record(base_token: str, table_id: str, fields: dict) -> dict:
    resp = await _client.post(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["record"]


async def search_records(base_token: str, table_id: str, filter_expr: str = "") -> list[dict]:
    params = {"page_size": 100}
    if filter_expr:
        params["filter"] = filter_expr
    resp = await _client.get(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
        headers=await _headers(),
        params=params,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {})
    items = data.get("items", [])
    return [{"record_id": r["record_id"], **r["fields"]} for r in items]


async def update_record(base_token: str, table_id: str, record_id: str, fields: dict) -> dict:
    resp = await _client.put(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    return resp.json()["data"]["record"]


async def delete_record(base_token: str, table_id: str, record_id: str):
    resp = await _client.delete(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
    )
    resp.raise_for_status()


async def close_lark():
    if _client:
        await _client.aclose()
```

**Step 2: Update `src/main.py` — bỏ params cũ khi init lark**

Thay `await lark.init_lark(settings.lark_app_id, settings.lark_app_secret, settings.lark_base_app_token)` thành:

```python
await lark.init_lark(settings.lark_app_id, settings.lark_app_secret)
```

**Step 3: Commit**

```bash
git add src/services/lark.py src/main.py
git commit -m "refactor: lark service supports multi-base provisioning"
```

---

### Task 3: Qdrant multi-collection support

**Files:**
- Modify: `src/services/qdrant.py` (bỏ global _collection, functions nhận collection name)

**Step 1: Refactor `src/services/qdrant.py`**

```python
import hashlib
import re
from collections import Counter

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, Fusion, FusionQuery,
    MatchValue, PointStruct, Prefetch, SparseVector,
    SparseVectorParams, VectorParams, models,
)
from src.services import openai_client

_qdrant: AsyncQdrantClient | None = None


def _word_hash(word: str) -> int:
    return int(hashlib.md5(word.encode()).hexdigest()[:8], 16)


def _tokenize_bm25(text: str) -> SparseVector:
    words = re.findall(r"\w+", text.lower())
    if not words:
        return SparseVector(indices=[0], values=[0.0])
    counts = Counter(words)
    total = len(words)
    indices = [_word_hash(w) for w in counts]
    values = [c / total for c in counts.values()]
    return SparseVector(indices=indices, values=values)


async def init_qdrant(qdrant_url: str):
    global _qdrant
    _qdrant = AsyncQdrantClient(url=qdrant_url)


async def ensure_collection(collection: str):
    """Tạo collection nếu chưa tồn tại."""
    existing = [c.name for c in (await _qdrant.get_collections()).collections]
    if collection not in existing:
        await _qdrant.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=1536, distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        await _qdrant.create_payload_index(
            collection_name=collection, field_name="chat_id", field_schema="integer"
        )


async def provision_collections(boss_chat_id: int):
    """Tạo 2 collections cho sếp mới: messages + tasks."""
    await ensure_collection(f"messages_{boss_chat_id}")
    await ensure_collection(f"tasks_{boss_chat_id}")


async def upsert(collection: str, point_id: int, chat_id: int,
                 role: str, text: str, vector: list[float]):
    sparse = _tokenize_bm25(text)
    point = PointStruct(
        id=point_id,
        vector={"dense": vector, "bm25": sparse},
        payload={"chat_id": chat_id, "role": role, "text": text},
    )
    await _qdrant.upsert(collection_name=collection, points=[point])


async def upsert_task(collection: str, record_id: str, text: str, vector: list[float]):
    """Upsert task vào Qdrant. Dùng hash record_id làm point id."""
    point_id = int(hashlib.md5(record_id.encode()).hexdigest()[:15], 16)
    sparse = _tokenize_bm25(text)
    point = PointStruct(
        id=point_id,
        vector={"dense": vector, "bm25": sparse},
        payload={"record_id": record_id, "text": text},
    )
    await _qdrant.upsert(collection_name=collection, points=[point])


async def delete_task(collection: str, record_id: str):
    """Xóa task khỏi Qdrant."""
    point_id = int(hashlib.md5(record_id.encode()).hexdigest()[:15], 16)
    await _qdrant.delete(collection_name=collection, points_selector=[point_id])


async def search(collection: str, query: str, chat_id: int | None = None,
                 top_n: int = 5) -> list[dict]:
    query_vector = await openai_client.embed(query)
    query_sparse = _tokenize_bm25(query)

    filter_cond = None
    if chat_id is not None:
        filter_cond = Filter(
            must=[FieldCondition(key="chat_id", match=MatchValue(value=chat_id))]
        )

    results = await _qdrant.query_points(
        collection_name=collection,
        prefetch=[
            Prefetch(query=query_vector, using="dense", limit=20, filter=filter_cond),
            Prefetch(query=query_sparse, using="bm25", limit=20, filter=filter_cond),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_n,
    )
    return [
        {"role": p.payload.get("role", ""), "content": p.payload.get("text", ""),
         "record_id": p.payload.get("record_id", "")}
        for p in results.points
    ]


async def close_qdrant():
    if _qdrant:
        await _qdrant.close()
```

**Step 2: Update `src/main.py`**

Thay `await qdrant.init_qdrant(settings.qdrant_url, settings.qdrant_collection)` thành:
```python
await qdrant.init_qdrant(settings.qdrant_url)
```

**Step 3: Commit**

```bash
git add src/services/qdrant.py src/main.py
git commit -m "refactor: qdrant supports multi-collection per boss"
```

---

### Task 4: Telegram service — group chat + thinking UX + send_message

**Files:**
- Modify: `src/services/telegram.py`

**Step 1: Refactor `src/services/telegram.py`**

Thêm: group chat parsing, editMessageText (thinking UX), send to specific user.

```python
import asyncio
import logging
import httpx

logger = logging.getLogger("telegram")

_client: httpx.AsyncClient | None = None
_token: str = ""
_polling: bool = False

API = "https://api.telegram.org"


async def init_telegram(token: str):
    global _client, _token
    _token = token
    _client = httpx.AsyncClient(timeout=30.0)
    await _client.post(f"{API}/bot{_token}/deleteWebhook")


async def send(chat_id: int, text: str, parse_mode: str = "Markdown") -> int | None:
    """Gửi tin nhắn, trả về message_id."""
    resp = await _client.post(
        f"{API}/bot{_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
    )
    data = resp.json()
    if data.get("ok"):
        return data["result"]["message_id"]
    return None


async def edit_message(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown"):
    """Sửa tin nhắn đã gửi (dùng cho thinking UX)."""
    await _client.post(
        f"{API}/bot{_token}/editMessageText",
        json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        },
    )


async def start_polling(on_message):
    """
    Long polling loop.
    on_message(text, chat_id, sender_id, is_group, bot_mentioned) callback.
    """
    global _polling
    _polling = True
    offset = 0
    # Get bot info for mention detection
    me_resp = await _client.get(f"{API}/bot{_token}/getMe")
    bot_username = me_resp.json().get("result", {}).get("username", "")
    logger.info(f"Polling started (bot: @{bot_username})")

    while _polling:
        try:
            resp = await _client.get(
                f"{API}/bot{_token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35.0,
            )
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "")
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                chat_type = chat.get("type", "private")  # private, group, supergroup
                sender_id = message.get("from", {}).get("id")

                if not text or not chat_id:
                    continue

                is_group = chat_type in ("group", "supergroup")
                bot_mentioned = f"@{bot_username}" in text if bot_username else False

                logger.info(
                    f"[chat:{chat_id}] {'GROUP' if is_group else '1-1'} "
                    f"sender:{sender_id} | {text[:100]}"
                )
                asyncio.create_task(
                    on_message(text, chat_id, sender_id, is_group, bot_mentioned)
                )

        except httpx.ReadTimeout:
            continue
        except Exception:
            logger.exception("Polling error, retrying in 3s")
            await asyncio.sleep(3)


def stop_polling():
    global _polling
    _polling = False
    logger.info("Polling stopped")


async def close_telegram():
    stop_polling()
    if _client:
        await _client.aclose()
```

**Step 2: Commit**

```bash
git add src/services/telegram.py
git commit -m "feat: telegram supports group chat, thinking UX, message editing"
```

---

## Phase 2: Tools — rebuild all 26 tools

Mục tiêu: viết lại toàn bộ tools, mỗi tool nhận `boss_chat_id` để biết query đúng Lark Base + Qdrant.

---

### Task 5: Context resolver module

**Files:**
- Create: `src/context.py`

Module trung tâm: từ chat_id → resolve ra boss, workspace, quyền, context notes.

**Step 1: Tạo `src/context.py`**

```python
"""
Context resolver: từ tin nhắn đến → xác định ai, thuộc sếp nào, quyền gì, notes nào.
"""
from dataclasses import dataclass
from src import db


@dataclass
class ChatContext:
    # Ai gửi
    sender_chat_id: int
    sender_name: str
    sender_type: str  # boss / member / partner / unknown

    # Thuộc workspace nào
    boss_chat_id: int | None
    boss_name: str

    # Lark Base
    lark_base_token: str
    lark_table_people: str
    lark_table_tasks: str
    lark_table_projects: str
    lark_table_ideas: str

    # Chat info
    chat_id: int  # conversation chat_id (có thể là group)
    is_group: bool
    group_name: str

    # Qdrant collections
    messages_collection: str
    tasks_collection: str


async def resolve(chat_id: int, sender_id: int, is_group: bool) -> ChatContext | None:
    """
    Resolve context từ tin nhắn đến.
    Returns None nếu người gửi chưa onboard (unknown).
    """
    boss = None
    sender_type = "unknown"
    sender_name = ""
    group_name = ""

    if is_group:
        # Group chat → tra group_map
        group = await db.get_group(chat_id)
        if not group:
            return None  # Group chưa đăng ký
        boss_chat_id = group["boss_chat_id"]
        group_name = group["group_name"]

        # Check sender trong group
        person = await db.get_person(sender_id)
        if person:
            sender_type = person["type"]
            sender_name = person["name"]
        else:
            sender_type = "unknown"
    else:
        # Chat 1-1 → sender = chat_id
        boss_data = await db.get_boss(sender_id)
        if boss_data:
            boss = boss_data
            sender_type = "boss"
            sender_name = boss_data["name"]
            boss_chat_id = sender_id
        else:
            person = await db.get_person(sender_id)
            if person:
                sender_type = person["type"]
                sender_name = person["name"]
                boss_chat_id = person["boss_chat_id"]
            else:
                return None  # Unknown person

    if not boss:
        boss = await db.get_boss(boss_chat_id)
        if not boss:
            return None

    return ChatContext(
        sender_chat_id=sender_id,
        sender_name=sender_name,
        sender_type=sender_type,
        boss_chat_id=boss["chat_id"],
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        chat_id=chat_id,
        is_group=is_group,
        group_name=group_name,
        messages_collection=f"messages_{boss['chat_id']}",
        tasks_collection=f"tasks_{boss['chat_id']}",
    )
```

**Step 2: Commit**

```bash
git add src/context.py
git commit -m "feat: context resolver - routes messages to correct workspace"
```

---

### Task 6: Rewrite all tools

**Files:**
- Rewrite: `src/tools/__init__.py` (tool registry + definitions cho 26 tools)
- Rewrite: `src/tools/tasks.py` (CRUD + semantic search + effort check)
- Rewrite: `src/tools/people.py` (mới, thay thế ko có file cũ)
- Rewrite: `src/tools/projects.py` (mới)
- Rewrite: `src/tools/ideas.py`
- Rewrite: `src/tools/note.py`
- Rewrite: `src/tools/memory.py`
- Rewrite: `src/tools/summary.py`
- Rewrite: `src/tools/workload.py`
- Create: `src/tools/messaging.py`
- Create: `src/tools/reminder.py`
- Create: `src/tools/web_search.py`
- Delete: `src/tools/note.py` (chức năng gom vào note mới)

Đây là task lớn nhất. Mỗi tool file nhận `ChatContext` từ agent, dùng context.lark_base_token + context.lark_table_* để query đúng workspace.

**Step 1: Viết `src/tools/people.py`**

```python
from src.context import ChatContext
from src.services import lark
from src import db


async def add_people(ctx: ChatContext, name: str, chat_id: int = 0,
                     username: str = "", group: str = "", person_type: str = "member",
                     role_desc: str = "", skills: str = "", note: str = "") -> str:
    fields = {"Tên": name, "Type": person_type}
    if chat_id:
        fields["Chat ID"] = chat_id
    if username:
        fields["Username"] = username
    if group:
        fields["Nhóm"] = group
    if role_desc:
        fields["Vai trò"] = role_desc
    if skills:
        fields["Kỹ năng"] = skills
    if note:
        fields["Ghi chú"] = note

    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)

    # Sync to SQLite people_map nếu có chat_id
    if chat_id:
        await db.add_person(chat_id, ctx.boss_chat_id, person_type, name)

    return f"Đã thêm {name} ({person_type}) vào hệ thống."


async def get_people(ctx: ChatContext, search_name: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search = search_name.lower()
    matched = [r for r in records
               if search in r.get("Tên", "").lower()
               or search in r.get("Tên gọi", "").lower()]

    if not matched:
        return f"Không tìm thấy ai tên '{search_name}'."

    lines = []
    for r in matched:
        lines.append(
            f"- {r.get('Tên', '?')} ({r.get('Tên gọi', '')}) | {r.get('Type', '')} | "
            f"Nhóm: {r.get('Nhóm', 'N/A')} | Vai trò: {r.get('Vai trò', 'N/A')} | "
            f"Kỹ năng: {r.get('Kỹ năng', 'N/A')} | Ghi chú: {r.get('Ghi chú', '')}"
        )
    return "\n".join(lines)


async def list_people(ctx: ChatContext, group: str = "", person_type: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    if group:
        records = [r for r in records if group.lower() in r.get("Nhóm", "").lower()]
    if person_type:
        records = [r for r in records if r.get("Type", "").lower() == person_type.lower()]

    if not records:
        return "Không có ai trong danh sách."

    lines = [f"Danh sách ({len(records)} người):"]
    for r in records:
        lines.append(f"- {r.get('Tên', '?')} | {r.get('Type', '')} | {r.get('Nhóm', 'N/A')} | {r.get('Vai trò', 'N/A')}")
    return "\n".join(lines)


async def update_people(ctx: ChatContext, search_name: str, **fields_to_update) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search = search_name.lower()
    matched = [r for r in records
               if search in r.get("Tên", "").lower()
               or search in r.get("Tên gọi", "").lower()]

    if not matched:
        return f"Không tìm thấy ai tên '{search_name}'."

    # Map param names → Lark field names
    field_map = {
        "name": "Tên", "nickname": "Tên gọi", "group": "Nhóm",
        "role_desc": "Vai trò", "skills": "Kỹ năng", "note": "Ghi chú",
        "phone": "SĐT", "username": "Username", "person_type": "Type",
    }
    lark_fields = {}
    for k, v in fields_to_update.items():
        if v and k in field_map:
            lark_fields[field_map[k]] = v

    if not lark_fields:
        return "Không có gì để cập nhật."

    for r in matched:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_people, r["record_id"], lark_fields)

    names = [r.get("Tên", "?") for r in matched]
    return f"Đã cập nhật: {', '.join(names)}"


async def delete_people(ctx: ChatContext, search_name: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search = search_name.lower()
    matched = [r for r in records
               if search in r.get("Tên", "").lower()
               or search in r.get("Tên gọi", "").lower()]

    if not matched:
        return f"Không tìm thấy ai tên '{search_name}'."

    for r in matched:
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_people, r["record_id"])
        # Xóa khỏi SQLite nếu có chat_id
        chat_id = r.get("Chat ID")
        if chat_id:
            await db.delete_person(int(chat_id))

    names = [r.get("Tên", "?") for r in matched]
    return f"Đã xóa: {', '.join(names)}"


async def check_effort(ctx: ChatContext, assignee: str, deadline: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    person_tasks = [r for r in records
                    if assignee.lower() in r.get("Assignee", "").lower()
                    and r.get("Status") in ("Mới", "Đang làm")]

    if not person_tasks:
        return f"{assignee} hiện không có task nào đang làm. Sẵn sàng nhận việc."

    lines = [f"{assignee} đang có {len(person_tasks)} task:"]
    conflict = False

    for t in person_tasks:
        dl = t.get("Deadline", "N/A")
        lines.append(f"  - {t.get('Tên task', '?')} | DL: {dl} | {t.get('Priority', '')}")
        # Check xung đột deadline
        if deadline and str(dl) == deadline:
            conflict = True
            lines.append(f"    ⚠ TRÙNG DEADLINE với task mới!")

    if len(person_tasks) >= 5:
        lines.append(f"\n⚠ {assignee} đang khá tải ({len(person_tasks)} task).")
    if conflict:
        lines.append(f"\n⚠ Có xung đột deadline ngày {deadline}.")

    return "\n".join(lines)
```

**Step 2: Viết `src/tools/tasks.py` (rewrite)**

```python
import asyncio
from datetime import datetime
from src.context import ChatContext
from src.services import lark, openai_client, qdrant


def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


async def _sync_task_to_qdrant(ctx: ChatContext, record_id: str, text: str):
    """Embed + upsert task vào Qdrant."""
    vector = await openai_client.embed(text)
    await qdrant.upsert_task(ctx.tasks_collection, record_id, text, vector)


async def create_task(ctx: ChatContext, name: str, assignee: str = "",
                      deadline: str = "", priority: str = "Trung bình",
                      project: str = "", start_time: str = "",
                      location: str = "", original_message: str = "") -> str:
    fields = {
        "Tên task": name,
        "Status": "Mới",
        "Priority": priority,
        "Giao bởi": ctx.sender_name or ctx.boss_name,
    }
    if assignee:
        fields["Assignee"] = assignee
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if start_time:
        fields["Start time"] = _date_to_ms(start_time)
    if location:
        fields["Location"] = location
    if project:
        fields["Project"] = project
    if original_message:
        fields["Tin nhắn gốc"] = original_message
    if ctx.is_group:
        fields["Group ID"] = ctx.chat_id

    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_tasks, fields)

    # Sync to Qdrant
    search_text = f"{name} {assignee} {project} {original_message}"
    asyncio.create_task(_sync_task_to_qdrant(ctx, record["record_id"], search_text))

    return f"Đã tạo task '{name}' (ID: {record['record_id']})"


async def list_tasks(ctx: ChatContext, assignee: str = "", status: str = "",
                     deadline_from: str = "", deadline_to: str = "",
                     project: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]
    if status:
        records = [r for r in records if r.get("Status") == status]
    if project:
        records = [r for r in records if project.lower() in r.get("Project", "").lower()]

    if not records:
        return "Không tìm thấy task nào."

    lines = []
    for r in records[:20]:
        lines.append(
            f"- {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | "
            f"{r.get('Status', '?')} | DL: {r.get('Deadline', 'N/A')} | "
            f"{r.get('Priority', '')}"
        )
    return "\n".join(lines)


async def update_task(ctx: ChatContext, search_keyword: str,
                      status: str = "", deadline: str = "", priority: str = "",
                      assignee: str = "", name: str = "", content: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    kw = search_keyword.lower()
    matched = [r for r in records if kw in r.get("Tên task", "").lower()]

    if not matched:
        return f"Không tìm thấy task nào chứa '{search_keyword}'."

    fields = {}
    if status:
        fields["Status"] = status
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if priority:
        fields["Priority"] = priority
    if assignee:
        fields["Assignee"] = assignee
    if name:
        fields["Tên task"] = name

    if not fields:
        return "Không có gì để cập nhật."

    updated = []
    for r in matched:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, r["record_id"], fields)
        # Sync Qdrant
        new_name = name or r.get("Tên task", "")
        new_assignee = assignee or r.get("Assignee", "")
        search_text = f"{new_name} {new_assignee} {r.get('Project', '')}"
        asyncio.create_task(_sync_task_to_qdrant(ctx, r["record_id"], search_text))
        updated.append(r.get("Tên task", "?"))

    return f"Đã cập nhật {len(updated)} task: {', '.join(updated)}"


async def delete_task(ctx: ChatContext, search_keyword: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    kw = search_keyword.lower()
    matched = [r for r in records if kw in r.get("Tên task", "").lower()]

    if not matched:
        return f"Không tìm thấy task nào chứa '{search_keyword}'."

    deleted = []
    for r in matched:
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_tasks, r["record_id"])
        await qdrant.delete_task(ctx.tasks_collection, r["record_id"])
        deleted.append(r.get("Tên task", "?"))

    return f"Đã xóa {len(deleted)} task: {', '.join(deleted)}"


async def search_tasks(ctx: ChatContext, query: str) -> str:
    """Semantic search qua Qdrant."""
    results = await qdrant.search(ctx.tasks_collection, query, top_n=10)

    if not results:
        return f"Không tìm thấy task nào liên quan '{query}'."

    # Lấy chi tiết từ Lark Base
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    record_map = {r["record_id"]: r for r in all_records}

    lines = [f"Kết quả tìm kiếm cho '{query}':"]
    for result in results:
        rid = result.get("record_id", "")
        r = record_map.get(rid, {})
        if r:
            lines.append(
                f"- {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | "
                f"{r.get('Status', '?')} | DL: {r.get('Deadline', 'N/A')}"
            )
    return "\n".join(lines) if len(lines) > 1 else f"Không tìm thấy task nào liên quan '{query}'."
```

**Step 3: Viết `src/tools/projects.py` (mới)**

```python
from src.context import ChatContext
from src.services import lark


async def create_project(ctx: ChatContext, name: str, description: str = "",
                         lead: str = "", members: str = "", deadline: str = "") -> str:
    fields = {"Tên dự án": name, "Trạng thái": "Planning"}
    if description:
        fields["Mô tả"] = description
    if lead:
        fields["Người phụ trách"] = lead
    if members:
        fields["Thành viên"] = members
    if deadline:
        from src.tools.tasks import _date_to_ms
        fields["Deadline"] = _date_to_ms(deadline)

    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_projects, fields)
    return f"Đã tạo dự án '{name}' (ID: {record['record_id']})"


async def get_project(ctx: ChatContext, search_name: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    search = search_name.lower()
    matched = [r for r in records if search in r.get("Tên dự án", "").lower()]

    if not matched:
        return f"Không tìm thấy dự án '{search_name}'."

    # Lấy tasks liên quan
    tasks = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    lines = []
    for r in matched:
        proj_name = r.get("Tên dự án", "?")
        lines.append(f"Dự án: {proj_name}")
        lines.append(f"  Mô tả: {r.get('Mô tả', 'N/A')}")
        lines.append(f"  Lead: {r.get('Người phụ trách', 'N/A')}")
        lines.append(f"  Thành viên: {r.get('Thành viên', 'N/A')}")
        lines.append(f"  Deadline: {r.get('Deadline', 'N/A')}")
        lines.append(f"  Trạng thái: {r.get('Trạng thái', 'N/A')}")

        related_tasks = [t for t in tasks if proj_name.lower() in t.get("Project", "").lower()]
        if related_tasks:
            lines.append(f"  Tasks ({len(related_tasks)}):")
            for t in related_tasks:
                lines.append(f"    - {t.get('Tên task', '?')} | {t.get('Assignee', '')} | {t.get('Status', '')}")

    return "\n".join(lines)


async def list_projects(ctx: ChatContext, status: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    if status:
        records = [r for r in records if r.get("Trạng thái", "").lower() == status.lower()]

    if not records:
        return "Không có dự án nào."

    lines = [f"Danh sách dự án ({len(records)}):"]
    for r in records:
        lines.append(
            f"- {r.get('Tên dự án', '?')} | Lead: {r.get('Người phụ trách', 'N/A')} | "
            f"{r.get('Trạng thái', '?')} | DL: {r.get('Deadline', 'N/A')}"
        )
    return "\n".join(lines)


async def update_project(ctx: ChatContext, search_name: str, **fields_to_update) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    search = search_name.lower()
    matched = [r for r in records if search in r.get("Tên dự án", "").lower()]

    if not matched:
        return f"Không tìm thấy dự án '{search_name}'."

    field_map = {
        "name": "Tên dự án", "description": "Mô tả", "lead": "Người phụ trách",
        "members": "Thành viên", "status": "Trạng thái",
    }
    lark_fields = {}
    for k, v in fields_to_update.items():
        if v and k in field_map:
            lark_fields[field_map[k]] = v
    if "deadline" in fields_to_update and fields_to_update["deadline"]:
        from src.tools.tasks import _date_to_ms
        lark_fields["Deadline"] = _date_to_ms(fields_to_update["deadline"])

    if not lark_fields:
        return "Không có gì để cập nhật."

    for r in matched:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"], lark_fields)

    names = [r.get("Tên dự án", "?") for r in matched]
    return f"Đã cập nhật dự án: {', '.join(names)}"


async def delete_project(ctx: ChatContext, search_name: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    search = search_name.lower()
    matched = [r for r in records if search in r.get("Tên dự án", "").lower()]

    if not matched:
        return f"Không tìm thấy dự án '{search_name}'."

    for r in matched:
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"])

    names = [r.get("Tên dự án", "?") for r in matched]
    return f"Đã xóa dự án: {', '.join(names)}"
```

**Step 4: Viết `src/tools/ideas.py` (rewrite)**

```python
import time
from src.context import ChatContext
from src.services import lark


async def create_idea(ctx: ChatContext, content: str, tags: str = "", project: str = "") -> str:
    fields = {
        "Nội dung": content,
        "Người tạo": ctx.sender_name or "Unknown",
    }
    if tags:
        fields["Tags"] = tags
    if project:
        fields["Project"] = project

    await lark.create_record(ctx.lark_base_token, ctx.lark_table_ideas, fields)
    return f"Đã lưu ý tưởng: {content}"
```

**Step 5: Viết `src/tools/note.py` (rewrite)**

```python
from src.context import ChatContext
from src import db


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    await db.update_note(ctx.boss_chat_id, note_type, ref_id, content)
    type_label = {"personal": "cá nhân", "project": "dự án", "group": "nhóm"}
    return f"Đã cập nhật note {type_label.get(note_type, note_type)}."


async def get_note(ctx: ChatContext, note_type: str, ref_id: str) -> str:
    content = await db.get_note(ctx.boss_chat_id, note_type, ref_id)
    if not content:
        return f"Chưa có note nào."
    return content
```

**Step 6: Viết `src/tools/memory.py` (rewrite)**

```python
from src.context import ChatContext
from src.services import qdrant


async def search_history(ctx: ChatContext, query: str, target_chat_id: int = 0) -> str:
    cid = target_chat_id or ctx.chat_id
    results = await qdrant.search(ctx.messages_collection, query, chat_id=cid, top_n=5)

    if not results:
        return f"Không tìm thấy lịch sử nào liên quan '{query}'."

    lines = [f"Kết quả tìm kiếm cho '{query}':"]
    for r in results:
        lines.append(f"  [{r['role']}]: {r['content']}")
    return "\n".join(lines)
```

**Step 7: Viết `src/tools/summary.py` (rewrite)**

```python
from datetime import date, datetime
from src.context import ChatContext
from src.services import lark


async def get_summary(ctx: ChatContext, summary_type: str = "today", assignee: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]

    if not records:
        return "Hiện chưa có task nào."

    today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)
    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]
    done = [r for r in records if r.get("Status") == "Xong"]
    overdue = [r for r in active
               if isinstance(r.get("Deadline"), (int, float)) and r["Deadline"] < today_ms]

    lines = []
    if summary_type == "week":
        lines.append("Báo cáo tuần:")
        lines.append(f"  Tổng: {len(records)} | Xong: {len(done)} | Đang làm: {len(active)} | Quá hạn: {len(overdue)}")
    else:
        lines.append(f"Tóm tắt hôm nay ({date.today().isoformat()}):")
        if active:
            lines.append(f"\nĐang làm ({len(active)}):")
            for r in active[:10]:
                lines.append(f"  - {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | DL: {r.get('Deadline', 'N/A')}")
        if overdue:
            lines.append(f"\nQuá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(f"  - {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')}")

    return "\n".join(lines)


async def get_workload(ctx: ChatContext, assignee: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]

    if assignee:
        active = [r for r in active if assignee.lower() in r.get("Assignee", "").lower()]

    if not active:
        return f"{assignee or 'Team'} hiện không có task nào đang làm." 

    # Group by assignee
    by_person = {}
    for r in active:
        name = r.get("Assignee", "Chưa giao")
        by_person.setdefault(name, []).append(r)

    lines = []
    for person, tasks in sorted(by_person.items(), key=lambda x: -len(x[1])):
        lines.append(f"{person}: {len(tasks)} task")
        for t in tasks[:5]:
            lines.append(f"  - {t.get('Tên task', '?')} | DL: {t.get('Deadline', 'N/A')}")

    return "\n".join(lines)
```

**Step 8: Viết `src/tools/messaging.py` (mới)**

```python
from src.context import ChatContext
from src.services import lark, telegram


async def send_message(ctx: ChatContext, to: str, content: str) -> str:
    """Gửi tin nhắn cho member/partner/group thay sếp."""
    # Tìm người nhận trong People
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search = to.lower()
    matched = [r for r in records
               if search in r.get("Tên", "").lower()
               or search in r.get("Tên gọi", "").lower()]

    if not matched:
        return f"Không tìm thấy người tên '{to}' trong hệ thống."

    person = matched[0]
    target_chat_id = person.get("Chat ID")

    if not target_chat_id:
        return f"{person.get('Tên', to)} chưa có Telegram chat ID trong hệ thống."

    # Format tin nhắn
    msg = f"📨 Tin nhắn từ {ctx.boss_name}:\n\n{content}"
    await telegram.send(int(target_chat_id), msg)

    return f"Đã gửi tin nhắn cho {person.get('Tên', to)}."
```

**Step 9: Viết `src/tools/reminder.py` (mới)**

```python
from src.context import ChatContext
from src import db


async def create_reminder(ctx: ChatContext, content: str, remind_at: str) -> str:
    """Tạo nhắc nhở. remind_at format: YYYY-MM-DD HH:MM"""
    await db.create_reminder(ctx.boss_chat_id, content, remind_at)
    return f"Đã đặt nhắc nhở: '{content}' vào lúc {remind_at}"
```

**Step 10: Viết `src/tools/web_search.py` (mới)**

```python
import httpx


async def web_search(query: str) -> str:
    """Tìm kiếm web qua DuckDuckGo Instant Answer API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        data = resp.json()

    results = []
    # Abstract
    if data.get("Abstract"):
        results.append(f"Tóm tắt: {data['Abstract']}")
        if data.get("AbstractURL"):
            results.append(f"Nguồn: {data['AbstractURL']}")

    # Related topics
    for topic in data.get("RelatedTopics", [])[:5]:
        if "Text" in topic:
            results.append(f"- {topic['Text']}")

    if not results:
        return f"Không tìm thấy kết quả cho '{query}'. Thử từ khóa khác."

    return "\n".join(results)
```

**Step 11: Viết `src/tools/__init__.py` (rewrite hoàn toàn)**

File này chứa 26 TOOL_DEFINITIONS + execute_tool router. File sẽ dài, đây là cấu trúc:

```python
import json
from src.context import ChatContext
from src.tools import tasks, people, projects, ideas, note, memory, summary, messaging, reminder, web_search

TOOL_DEFINITIONS = [
    # --- Task tools (5) ---
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Tạo task mới. Khi giao task → tự check effort trước.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên task"},
                    "assignee": {"type": "string", "description": "Người được giao"},
                    "deadline": {"type": "string", "description": "YYYY-MM-DD"},
                    "priority": {"type": "string", "enum": ["Cao", "Trung bình", "Thấp"]},
                    "project": {"type": "string", "description": "Thuộc dự án nào"},
                    "start_time": {"type": "string", "description": "YYYY-MM-DD (cho cuộc họp)"},
                    "location": {"type": "string", "description": "Địa điểm"},
                    "original_message": {"type": "string", "description": "Tin nhắn gốc"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Lọc danh sách task theo assignee, status, project, deadline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string"},
                    "status": {"type": "string", "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"]},
                    "project": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Cập nhật task: status, deadline, assignee, tên, nội dung.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm task"},
                    "status": {"type": "string", "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"]},
                    "deadline": {"type": "string"},
                    "priority": {"type": "string", "enum": ["Cao", "Trung bình", "Thấp"]},
                    "assignee": {"type": "string"},
                    "name": {"type": "string", "description": "Tên task mới"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Xóa task. LUÔN confirm với sếp trước khi gọi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Tìm task theo nội dung (semantic search). Cho query mơ hồ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    # --- People tools (6) ---
    {
        "type": "function",
        "function": {
            "name": "add_people",
            "description": "Thêm thành viên/đối tác vào hệ thống.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "chat_id": {"type": "integer", "description": "Telegram chat_id"},
                    "username": {"type": "string", "description": "Telegram @username"},
                    "group": {"type": "string", "description": "Nhóm/team"},
                    "person_type": {"type": "string", "enum": ["member", "partner"]},
                    "role_desc": {"type": "string", "description": "Vai trò (editor, designer...)"},
                    "skills": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_people",
            "description": "Xem thông tin chi tiết 1 người.",
            "parameters": {
                "type": "object",
                "properties": {"search_name": {"type": "string"}},
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_people",
            "description": "Danh sách nhân sự, filter theo nhóm hoặc type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {"type": "string"},
                    "person_type": {"type": "string", "enum": ["boss", "member", "partner"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_people",
            "description": "Cập nhật thông tin người.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string"},
                    "name": {"type": "string"},
                    "nickname": {"type": "string"},
                    "group": {"type": "string"},
                    "role_desc": {"type": "string"},
                    "skills": {"type": "string"},
                    "note": {"type": "string"},
                    "phone": {"type": "string"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_people",
            "description": "Xóa người khỏi hệ thống. LUÔN confirm trước.",
            "parameters": {
                "type": "object",
                "properties": {"search_name": {"type": "string"}},
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_effort",
            "description": "Check workload + xung đột deadline. Dùng trước khi giao task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string"},
                    "deadline": {"type": "string", "description": "Deadline task mới (YYYY-MM-DD)"},
                },
                "required": ["assignee"],
            },
        },
    },
    # --- Project tools (5) ---
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "Tạo dự án mới.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "lead": {"type": "string"},
                    "members": {"type": "string"},
                    "deadline": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "Xem chi tiết dự án + tasks liên quan.",
            "parameters": {
                "type": "object",
                "properties": {"search_name": {"type": "string"}},
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Danh sách dự án.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["Planning", "Active", "Done"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_project",
            "description": "Cập nhật dự án.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "lead": {"type": "string"},
                    "members": {"type": "string"},
                    "deadline": {"type": "string"},
                    "status": {"type": "string", "enum": ["Planning", "Active", "Done"]},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_project",
            "description": "Xóa dự án. LUÔN confirm trước.",
            "parameters": {
                "type": "object",
                "properties": {"search_name": {"type": "string"}},
                "required": ["search_name"],
            },
        },
    },
    # --- Note tools (2) ---
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Cập nhật note nội bộ bot (personal/project/group).",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {"type": "string", "enum": ["personal", "project", "group"]},
                    "ref_id": {"type": "string", "description": "chat_id hoặc project name hoặc group_chat_id"},
                    "content": {"type": "string"},
                },
                "required": ["note_type", "ref_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": "Đọc note nội bộ. Gọi khi cần thêm context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {"type": "string", "enum": ["personal", "project", "group"]},
                    "ref_id": {"type": "string"},
                },
                "required": ["note_type", "ref_id"],
            },
        },
    },
    # --- Memory tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "Hybrid search lịch sử chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "target_chat_id": {"type": "integer", "description": "Chat cụ thể (mặc định = chat hiện tại)"},
                },
                "required": ["query"],
            },
        },
    },
    # --- Summary tools (2) ---
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Tổng hợp task theo ngày/tuần.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_type": {"type": "string", "enum": ["today", "week"]},
                    "assignee": {"type": "string"},
                },
                "required": ["summary_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workload",
            "description": "Xem workload team/cá nhân.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    # --- Idea tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "create_idea",
            "description": "Lưu ý tưởng.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "tags": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["content"],
            },
        },
    },
    # --- Messaging tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Gửi tin nhắn cho member/partner thay sếp. 2 chiều.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Tên người nhận"},
                    "content": {"type": "string", "description": "Nội dung tin nhắn"},
                },
                "required": ["to", "content"],
            },
        },
    },
    # --- Reminder tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Tạo nhắc nhở cá nhân cho sếp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "remind_at": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
                },
                "required": ["content", "remind_at"],
            },
        },
    },
    # --- Web Search tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Tìm kiếm web khi cần thông tin bên ngoài.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    # --- Advisor tools (1) ---
    {
        "type": "function",
        "function": {
            "name": "escalate_to_advisor",
            "description": "Chuyển sang Advisor agent khi sếp cần: phân tích chiến lược, sắp xếp công việc tổng thể, đánh giá/đề xuất phương án. KHÔNG gọi cho CRUD đơn giản.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Tóm tắt tình huống"},
                    "question": {"type": "string", "description": "Câu hỏi cần Advisor phân tích"},
                },
                "required": ["context", "question"],
            },
        },
    },
]


async def execute_tool(name: str, arguments: str, ctx: ChatContext) -> str:
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    match name:
        # Task
        case "create_task":
            return await tasks.create_task(ctx, **args)
        case "list_tasks":
            return await tasks.list_tasks(ctx, **args)
        case "update_task":
            return await tasks.update_task(ctx, **args)
        case "delete_task":
            return await tasks.delete_task(ctx, **args)
        case "search_tasks":
            return await tasks.search_tasks(ctx, **args)
        # People
        case "add_people":
            return await people.add_people(ctx, **args)
        case "get_people":
            return await people.get_people(ctx, **args)
        case "list_people":
            return await people.list_people(ctx, **args)
        case "update_people":
            return await people.update_people(ctx, **args)
        case "delete_people":
            return await people.delete_people(ctx, **args)
        case "check_effort":
            return await people.check_effort(ctx, **args)
        # Project
        case "create_project":
            return await projects.create_project(ctx, **args)
        case "get_project":
            return await projects.get_project(ctx, **args)
        case "list_projects":
            return await projects.list_projects(ctx, **args)
        case "update_project":
            return await projects.update_project(ctx, **args)
        case "delete_project":
            return await projects.delete_project(ctx, **args)
        # Note
        case "update_note":
            return await note.update_note(ctx, **args)
        case "get_note":
            return await note.get_note(ctx, **args)
        # Memory
        case "search_history":
            return await memory.search_history(ctx, **args)
        # Summary
        case "get_summary":
            return await summary.get_summary(ctx, **args)
        case "get_workload":
            return await summary.get_workload(ctx, **args)
        # Idea
        case "create_idea":
            return await ideas.create_idea(ctx, **args)
        # Messaging
        case "send_message":
            return await messaging.send_message(ctx, **args)
        # Reminder
        case "create_reminder":
            return await reminder.create_reminder(ctx, **args)
        # Web Search
        case "web_search":
            return await web_search.web_search(**args)
        # Advisor (handled đặc biệt trong agent.py, không qua đây)
        case "escalate_to_advisor":
            return "__ESCALATE__"
        case _:
            return f"Tool '{name}' không tồn tại."
```

**Step 12: Xóa file workload.py cũ (gom vào summary.py)**

```bash
rm src/tools/workload.py
```

**Step 13: Commit**

```bash
git add src/tools/ src/context.py
git commit -m "feat: rewrite all 26 tools with multi-boss context support"
```

---

## Phase 3: Agents — Secretary + Advisor + Onboarding

---

### Task 7: Secretary agent (rewrite `src/agent.py`)

**Files:**
- Rewrite: `src/agent.py`

**Step 1: Viết lại `src/agent.py`**

```python
import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src import db
from src.config import Settings
from src.context import ChatContext, resolve
from src.services import lark, openai_client, qdrant, telegram
from src.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("agent")

_settings: Settings | None = None

# Tool name → thinking message
THINKING_MAP = {
    "create_task": "Đang tạo task...",
    "list_tasks": "Đang xem danh sách task...",
    "update_task": "Đang cập nhật task...",
    "delete_task": "Đang xóa task...",
    "search_tasks": "Đang tìm task...",
    "add_people": "Đang thêm người...",
    "get_people": "Đang tra thông tin...",
    "list_people": "Đang xem danh sách...",
    "check_effort": "Đang kiểm tra lịch...",
    "search_history": "Đang tra lịch sử...",
    "get_summary": "Đang tổng hợp...",
    "get_workload": "Đang xem workload...",
    "web_search": "Đang tìm kiếm web...",
    "send_message": "Đang gửi tin nhắn...",
    "escalate_to_advisor": "Đang phân tích chiến lược...",
}

SECRETARY_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}. Giao tiếp tiếng Việt, thân thiện, ngắn gọn, chuyên nghiệp.

## Personal Note:
{personal_note}

## Thời gian: {current_time}

## Nhân sự:
{people_summary}

## Đang nói chuyện với:
Chat: {chat_type}
Người: {sender_name} ({sender_type})
{context_note}

## Quy tắc phân quyền:
- Nếu đang nói với SẾP ({boss_name}):
  → Toàn quyền. Xưng hô theo personal note.
  → Khi giao task → check_effort trước → cảnh báo nếu xung đột → gợi ý giải pháp.
  → Khi sếp hỏi chiến lược / sắp xếp tổng thể → gọi escalate_to_advisor.
  → Mọi thao tác xóa → confirm trước.
  → Khi sếp bảo nhắn ai → gọi send_message.

- Nếu đang nói với MEMBER/PARTNER:
  → Xưng "em là trợ lý của {boss_name}".
  → Chỉ cho xem/cập nhật task của họ.
  → Được sửa: status, nội dung, tên task, đẩy lại assignee.
  → Khi đẩy lại assignee → ghi nhận, báo sếp qua send_message.
  → KHÔNG cho xem task người khác, giao task, xem tổng quan.
  → Không tự quyết thay sếp. "Em ghi nhận, báo lại {boss_name} nhé."

- Trong GROUP: chỉ phản hồi khi được tag. Quyền tùy người tag.

## Hướng dẫn:
- Trả lời ngắn gọn, đi thẳng vấn đề.
- Gọi nhiều tool liên tiếp nếu cần.
- Biết thêm thông tin → update_note.
- Cần context cũ → search_history.
- Nhận diện người bằng tên + context nhân sự. Không chắc → hỏi lại.
"""

MAX_TOOL_ROUNDS = 10


def init_agent(settings: Settings):
    global _settings
    _settings = settings


async def _build_people_summary(ctx: ChatContext) -> str:
    """Lấy danh sách People gọn để inject vào prompt."""
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    if not records:
        return "(Chưa có ai)"
    lines = []
    for r in records:
        lines.append(
            f"- {r.get('Tên', '?')} ({r.get('Tên gọi', '')}) | "
            f"{r.get('Type', '')} | {r.get('Nhóm', '')} | {r.get('Vai trò', '')}"
        )
    return "\n".join(lines)


async def handle_message(text: str, chat_id: int, sender_id: int,
                         is_group: bool, bot_mentioned: bool):
    start_time = time.time()

    # Group: chỉ lưu nếu không tag bot
    if is_group and not bot_mentioned:
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        # Resolve context để biết collection nào
        ctx = await resolve(chat_id, sender_id, is_group)
        if ctx:
            vector = await openai_client.embed(text)
            asyncio.create_task(
                qdrant.upsert(ctx.messages_collection, msg_id, chat_id, "user", text, vector)
            )
        return

    # Resolve context
    ctx = await resolve(chat_id, sender_id, is_group)

    if ctx is None:
        # Unknown user → onboard
        await _handle_onboard(text, chat_id, sender_id)
        return

    logger.info(
        f"[chat:{chat_id}] sender:{sender_id} ({ctx.sender_type}) >>> {text[:100]}"
    )

    try:
        # 1. Save message + embed
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        vector = await openai_client.embed(text)
        asyncio.create_task(
            qdrant.upsert(ctx.messages_collection, msg_id, chat_id, "user", text, vector)
        )

        # 2. Get context (parallel)
        personal_note, recent, relevant, people_summary = await asyncio.gather(
            db.get_note(ctx.boss_chat_id, "personal", str(ctx.sender_chat_id)),
            db.get_recent(chat_id, limit=_settings.recent_messages),
            qdrant.search(ctx.messages_collection, text, chat_id=chat_id,
                          top_n=_settings.rag_messages),
            _build_people_summary(ctx),
        )

        # Context note (group note hoặc personal note)
        context_note = ""
        if is_group:
            context_note = await db.get_note(ctx.boss_chat_id, "group", str(chat_id))
        if context_note:
            context_note = f"Group note:\n{context_note}"

        # 3. Build messages
        tz = ZoneInfo(_settings.timezone)
        current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

        company_info = ""
        boss = await db.get_boss(ctx.boss_chat_id)
        if boss and boss.get("company"):
            company_info = f", công ty {boss['company']}"

        messages = [
            {
                "role": "system",
                "content": SECRETARY_PROMPT.format(
                    boss_name=ctx.boss_name,
                    company_info=company_info,
                    personal_note=personal_note or "(Chưa biết gì)",
                    current_time=current_time,
                    people_summary=people_summary,
                    chat_type="Group: " + ctx.group_name if is_group else "Chat 1-1",
                    sender_name=ctx.sender_name or "Chưa biết",
                    sender_type=ctx.sender_type,
                    context_note=context_note,
                ),
            }
        ]

        if relevant:
            context_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in relevant)
            messages.append({"role": "system", "content": f"Lịch sử liên quan:\n{context_text}"})

        for msg in recent:
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": text})

        # 4. Thinking UX: send placeholder
        thinking_msg_id = await telegram.send(chat_id, "Đang xử lý...")

        # 5. Agent loop
        reply_text = ""
        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            response, usage = await openai_client.chat_with_tools(messages, TOOL_DEFINITIONS)

            if response.tool_calls:
                messages.append(response)
                for tool_call in response.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = tool_call.function.arguments
                    logger.info(f"[chat:{chat_id}] TOOL: {tool_name}({tool_args})")

                    # Update thinking message
                    thinking_text = THINKING_MAP.get(tool_name, "Đang xử lý...")
                    if thinking_msg_id:
                        asyncio.create_task(
                            telegram.edit_message(chat_id, thinking_msg_id, thinking_text)
                        )

                    # Handle escalate_to_advisor
                    if tool_name == "escalate_to_advisor":
                        import json as _json
                        advisor_args = _json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                        result = await _run_advisor(ctx, advisor_args, messages)
                    else:
                        result = await execute_tool(tool_name, tool_args, ctx)

                    logger.info(f"[chat:{chat_id}] RESULT: {result[:200]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue

            reply_text = response.content or "..."
            break

        # 6. Replace thinking message with final reply
        if thinking_msg_id:
            await telegram.edit_message(chat_id, thinking_msg_id, reply_text)
        else:
            await telegram.send(chat_id, reply_text)

        # 7. Save reply + embed
        reply_id = await db.save_message(chat_id, "assistant", reply_text)
        reply_vector = await openai_client.embed(reply_text)
        asyncio.create_task(
            qdrant.upsert(ctx.messages_collection, reply_id, chat_id, "assistant", reply_text, reply_vector)
        )

        elapsed = time.time() - start_time
        logger.info(f"[chat:{chat_id}] <<< {reply_text[:200]} | {elapsed:.1f}s")

    except Exception:
        logger.exception(f"[chat:{chat_id}] Error")
        await telegram.send(chat_id, "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.")


async def _run_advisor(ctx: ChatContext, args: dict, secretary_messages: list) -> str:
    """Chạy Advisor agent, trả kết quả về cho Secretary."""
    from src.advisor import run_advisor
    return await run_advisor(ctx, args.get("context", ""), args.get("question", ""), _settings)


async def _handle_onboard(text: str, chat_id: int, sender_id: int):
    """Xử lý người mới chưa onboard."""
    # Check if already in onboarding (dựa vào recent messages)
    # Simple: gửi tin nhắn chào + hướng dẫn
    await telegram.send(
        chat_id,
        "Chào bạn! Mình là trợ lý AI.\n\n"
        "Bạn là:\n"
        "1. Quản lý / Giám đốc muốn dùng dịch vụ\n"
        "2. Thành viên team\n"
        "3. Đối tác\n\n"
        "Trả lời 1, 2 hoặc 3 nhé!"
    )
    # TODO: implement full onboarding flow with state machine (Task 8)
```

**Step 2: Commit**

```bash
git add src/agent.py
git commit -m "feat: secretary agent with multi-user routing + thinking UX"
```

---

### Task 8: Advisor agent

**Files:**
- Create: `src/advisor.py`

**Step 1: Viết `src/advisor.py`**

```python
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import Settings
from src.context import ChatContext
from src.services import openai_client
from src.tools import execute_tool

logger = logging.getLogger("advisor")

# Advisor chỉ dùng tools đọc data, không CRUD
ADVISOR_TOOLS = [
    t for t in __import__("src.tools", fromlist=["TOOL_DEFINITIONS"]).TOOL_DEFINITIONS
    if t["function"]["name"] in (
        "list_tasks", "search_tasks", "list_people", "get_people",
        "check_effort", "list_projects", "get_project",
        "get_note", "search_history", "get_summary", "get_workload",
    )
]

ADVISOR_PROMPT = """Bạn là cố vấn chiến lược cho {boss_name}{company_info}.
Vai trò: phân tích tình hình, đề xuất giải pháp, giúp sếp ra quyết định.

## Thời gian: {current_time}

## Câu hỏi: {question}

## Context: {context}

## Hướng dẫn:
- Phân tích dựa trên DATA thực tế. Gọi tools để lấy data.
- Đề xuất cụ thể, có lý do, kèm phương án thay thế.
- Xem xét: workload, deadline, kỹ năng, xung đột lịch.
- Thiếu thông tin → nói rõ, đề xuất dựa trên cái đang có.
- Format: Tình hình → Phân tích → Đề xuất → Lý do.
- Tiếng Việt, chuyên nghiệp, ngắn gọn.
"""

DAILY_REVIEW_PROMPT = """Bạn là cố vấn AI của {boss_name}. Hôm nay {current_time}.
Soạn briefing sáng cho sếp.

Hãy:
1. Xem tasks hôm nay + quá hạn + deadline trong 3 ngày
2. Xem workload từng người
3. Xem dự án đang active
4. Phân tích: cảnh báo, quá tải, deadline nguy hiểm?
5. Đề xuất hành động cụ thể

Format:
- Chào sếp, tóm 1 câu tình hình
- Tasks hôm nay
- Cảnh báo (nếu có)
- Đề xuất (nếu có)
- Hỏi sếp muốn xử lý gì

Dưới 300 từ, chỉ nêu điều quan trọng.
"""

MAX_ADVISOR_ROUNDS = 8


async def run_advisor(ctx: ChatContext, context: str, question: str,
                      settings: Settings) -> str:
    """Advisor agent: phân tích + đề xuất."""
    tz = ZoneInfo(settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    from src import db
    boss = await db.get_boss(ctx.boss_chat_id)
    company_info = f", {boss['company']}" if boss and boss.get("company") else ""

    messages = [
        {
            "role": "system",
            "content": ADVISOR_PROMPT.format(
                boss_name=ctx.boss_name,
                company_info=company_info,
                current_time=current_time,
                question=question,
                context=context,
            ),
        },
        {"role": "user", "content": question},
    ]

    for _ in range(MAX_ADVISOR_ROUNDS):
        response, usage = await openai_client.chat_with_tools(messages, ADVISOR_TOOLS)

        if response.tool_calls:
            messages.append(response)
            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                logger.info(f"[advisor] TOOL: {tool_name}")
                result = await execute_tool(tool_name, tool_call.function.arguments, ctx)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue

        return response.content or "Không có phân tích."

    return "Advisor timeout — quá nhiều vòng phân tích."


async def run_daily_review(ctx: ChatContext, settings: Settings) -> str:
    """Smart daily review cho cron job sáng."""
    tz = ZoneInfo(settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    from src import db
    boss = await db.get_boss(ctx.boss_chat_id)
    company_info = f", {boss['company']}" if boss and boss.get("company") else ""

    messages = [
        {
            "role": "system",
            "content": DAILY_REVIEW_PROMPT.format(
                boss_name=ctx.boss_name,
                company_info=company_info,
                current_time=current_time,
            ),
        },
        {"role": "user", "content": "Soạn briefing sáng cho sếp."},
    ]

    for _ in range(MAX_ADVISOR_ROUNDS):
        response, usage = await openai_client.chat_with_tools(messages, ADVISOR_TOOLS)

        if response.tool_calls:
            messages.append(response)
            for tool_call in response.tool_calls:
                result = await execute_tool(
                    tool_call.function.name, tool_call.function.arguments, ctx
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue

        return response.content or "Không có gì đáng chú ý hôm nay."

    return "Daily review timeout."
```

**Step 2: Commit**

```bash
git add src/advisor.py
git commit -m "feat: advisor agent for strategy analysis + daily review"
```

---

### Task 9: Onboarding flow

**Files:**
- Create: `src/onboarding.py`

**Step 1: Viết `src/onboarding.py`**

Xử lý flow onboard sếp mới (tạo workspace) + member/partner mới (link vào workspace).

```python
import logging
from src import db
from src.services import lark, qdrant, telegram

logger = logging.getLogger("onboard")

# In-memory onboarding state (chat_id → state dict)
_onboarding: dict[int, dict] = {}


async def handle_onboard_message(text: str, chat_id: int):
    """Xử lý tin nhắn từ người đang onboard."""
    state = _onboarding.get(chat_id, {"step": "ask_type"})

    if state["step"] == "ask_type":
        text_lower = text.strip().lower()
        if text_lower in ("1", "sếp", "sep", "quản lý", "quan ly", "giám đốc"):
            _onboarding[chat_id] = {"step": "boss_name", "type": "boss"}
            await telegram.send(chat_id, "Tên anh/chị là gì ạ?")
        elif text_lower in ("2", "thành viên", "thanh vien", "member", "nhân viên"):
            _onboarding[chat_id] = {"step": "member_boss", "type": "member"}
            await telegram.send(chat_id, "Bạn thuộc team của ai? Cho mình tên sếp hoặc công ty.")
        elif text_lower in ("3", "đối tác", "doi tac", "partner"):
            _onboarding[chat_id] = {"step": "member_boss", "type": "partner"}
            await telegram.send(chat_id, "Bạn liên hệ với ai? Cho mình tên sếp hoặc công ty.")
        else:
            await telegram.send(chat_id, "Trả lời 1 (quản lý), 2 (thành viên), hoặc 3 (đối tác) nhé!")

    elif state["step"] == "boss_name":
        state["name"] = text.strip()
        state["step"] = "boss_company"
        _onboarding[chat_id] = state
        await telegram.send(chat_id, f"Chào {state['name']}! Công ty/tổ chức tên gì ạ?")

    elif state["step"] == "boss_company":
        state["company"] = text.strip()
        state["step"] = "boss_confirm"
        _onboarding[chat_id] = state
        await telegram.send(
            chat_id,
            f"OK! Mình tạo workspace cho {state['name']} - {state['company']} nhé?\n"
            f"Trả lời 'OK' để bắt đầu."
        )

    elif state["step"] == "boss_confirm":
        if text.strip().lower() in ("ok", "oke", "yes", "có", "ờ", "ừ", "đc", "được"):
            await telegram.send(chat_id, "Đang tạo workspace... (30s)")
            try:
                workspace = await lark.provision_workspace(state["company"])
                await db.create_boss(
                    chat_id=chat_id,
                    name=state["name"],
                    company=state["company"],
                    lark_base_token=workspace["base_token"],
                    lark_table_people=workspace["table_people"],
                    lark_table_tasks=workspace["table_tasks"],
                    lark_table_projects=workspace["table_projects"],
                    lark_table_ideas=workspace["table_ideas"],
                )
                await db.add_person(chat_id, chat_id, "boss", state["name"])
                await qdrant.provision_collections(chat_id)

                # Thêm sếp vào People trên Lark Base
                await lark.create_record(workspace["base_token"], workspace["table_people"], {
                    "Tên": state["name"],
                    "Chat ID": chat_id,
                    "Type": "boss",
                })

                del _onboarding[chat_id]
                await telegram.send(
                    chat_id,
                    f"Xong rồi {state['name']}! Workspace đã sẵn sàng.\n\n"
                    f"Anh/chị có thể:\n"
                    f"- Giao việc: 'Giao Bách task quay video'\n"
                    f"- Thêm người: 'Thêm Bách, editor, team media'\n"
                    f"- Xem task: 'Hôm nay có gì?'\n\n"
                    f"Bắt đầu thôi!"
                )
                logger.info(f"[onboard] Boss {state['name']} ({chat_id}) - workspace created")
            except Exception:
                logger.exception(f"[onboard] Failed to provision for {chat_id}")
                await telegram.send(chat_id, "Có lỗi khi tạo workspace. Thử lại nhé!")
        else:
            await telegram.send(chat_id, "OK, trả lời 'OK' khi sẵn sàng nhé!")

    elif state["step"] == "member_boss":
        # Tìm sếp theo tên/công ty
        bosses = await db.get_all_bosses()
        search = text.strip().lower()
        matched = [b for b in bosses
                   if search in b["name"].lower() or search in b.get("company", "").lower()]

        if not matched:
            await telegram.send(chat_id, "Không tìm thấy. Thử lại tên sếp hoặc công ty?")
        elif len(matched) > 1:
            names = ", ".join(f"{b['name']} ({b.get('company', '')})" for b in matched)
            await telegram.send(chat_id, f"Tìm thấy nhiều: {names}. Chọn cụ thể hơn?")
        else:
            state["boss"] = matched[0]
            state["step"] = "member_name"
            _onboarding[chat_id] = state
            await telegram.send(chat_id, f"OK, team của {matched[0]['name']}. Tên bạn là gì?")

    elif state["step"] == "member_name":
        state["name"] = text.strip()
        boss = state["boss"]
        person_type = state["type"]

        await db.add_person(chat_id, boss["chat_id"], person_type, state["name"])

        # Thêm vào Lark Base People
        await lark.create_record(boss["lark_base_token"], boss["lark_table_people"], {
            "Tên": state["name"],
            "Chat ID": chat_id,
            "Type": person_type,
        })

        del _onboarding[chat_id]
        type_label = "thành viên" if person_type == "member" else "đối tác"
        await telegram.send(
            chat_id,
            f"Chào {state['name']}! Đã liên kết với team {boss['name']} ({type_label}).\n"
            f"Khi có task mới mình sẽ nhắn bạn nhé!"
        )
        logger.info(f"[onboard] {person_type} {state['name']} ({chat_id}) → boss {boss['name']}")


def is_onboarding(chat_id: int) -> bool:
    return chat_id in _onboarding


def start_onboarding(chat_id: int):
    _onboarding[chat_id] = {"step": "ask_type"}
```

**Step 2: Update `src/agent.py` `_handle_onboard`**

Thay TODO bằng gọi onboarding module:

```python
async def _handle_onboard(text: str, chat_id: int, sender_id: int):
    from src.onboarding import handle_onboard_message, is_onboarding, start_onboarding
    if is_onboarding(chat_id):
        await handle_onboard_message(text, chat_id)
    else:
        start_onboarding(chat_id)
        await handle_onboard_message(text, chat_id)
```

**Step 3: Commit**

```bash
git add src/onboarding.py src/agent.py
git commit -m "feat: onboarding flow for boss, member, partner"
```

---

## Phase 4: Scheduler + Main App

---

### Task 10: Rewrite scheduler

**Files:**
- Rewrite: `src/scheduler.py`

**Step 1: Viết lại `src/scheduler.py`**

```python
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src import db
from src.config import Settings
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None
_settings: Settings | None = None


def _make_ctx(boss: dict) -> ChatContext:
    """Tạo ChatContext giả cho scheduler jobs."""
    return ChatContext(
        sender_chat_id=boss["chat_id"],
        sender_name=boss["name"],
        sender_type="boss",
        boss_chat_id=boss["chat_id"],
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        chat_id=boss["chat_id"],
        is_group=False,
        group_name="",
        messages_collection=f"messages_{boss['chat_id']}",
        tasks_collection=f"tasks_{boss['chat_id']}",
    )


async def _morning_review():
    """8h sáng: Advisor chạy smart daily review cho mỗi sếp."""
    from src.advisor import run_daily_review
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            review = await run_daily_review(ctx, _settings)
            await telegram.send(boss["chat_id"], review)
            logger.info(f"[scheduler] Morning review sent to {boss['name']}")
        except Exception:
            logger.exception(f"[scheduler] Morning review failed for {boss['name']}")


async def _evening_summary():
    """17h: tổng kết ngày."""
    from src.tools.summary import get_summary
    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            text = await get_summary(ctx, "today")
            await telegram.send(boss["chat_id"], f"*Tổng kết cuối ngày:*\n\n{text}")
        except Exception:
            logger.exception(f"[scheduler] Evening summary failed for {boss['name']}")


async def _check_deadlines():
    """Check deadline sắp tới → nhắn người được giao."""
    from datetime import date, datetime, timedelta

    bosses = await db.get_all_bosses()
    for boss in bosses:
        try:
            ctx = _make_ctx(boss)
            records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
            people = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
            people_map = {p.get("Tên", "").lower(): p for p in people}

            tomorrow = date.today() + timedelta(days=1)
            tomorrow_ms = int(datetime.combine(tomorrow, datetime.min.time()).timestamp() * 1000)
            tomorrow_end = tomorrow_ms + 86400 * 1000

            for r in records:
                if r.get("Status") not in ("Mới", "Đang làm"):
                    continue
                dl = r.get("Deadline")
                if not isinstance(dl, (int, float)):
                    continue

                assignee_name = r.get("Assignee", "").lower()
                person = people_map.get(assignee_name)

                # Deadline tomorrow
                if tomorrow_ms <= dl < tomorrow_end and person:
                    target_id = person.get("Chat ID")
                    if target_id:
                        await telegram.send(
                            int(target_id),
                            f"Nhắc nhở: Task '{r.get('Tên task', '?')}' deadline ngày mai!"
                        )

                # Overdue → nhắn assignee + báo boss
                today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)
                if dl < today_ms:
                    if person and person.get("Chat ID"):
                        await telegram.send(
                            int(person["Chat ID"]),
                            f"Task '{r.get('Tên task', '?')}' đã QUÁ HẠN! Cập nhật tiến độ nhé."
                        )
                    await telegram.send(
                        boss["chat_id"],
                        f"Task quá hạn: '{r.get('Tên task', '?')}' ({r.get('Assignee', 'N/A')})"
                    )
        except Exception:
            logger.exception(f"[scheduler] Deadline check failed for {boss['name']}")


async def _check_reminders():
    """Check reminders đến giờ → nhắn sếp."""
    reminders = await db.get_due_reminders()
    for r in reminders:
        try:
            await telegram.send(r["boss_chat_id"], f"Nhắc nhở: {r['content']}")
            await db.mark_reminder_done(r["id"])
            logger.info(f"[scheduler] Reminder {r['id']} sent")
        except Exception:
            logger.exception(f"[scheduler] Reminder {r['id']} failed")


async def _follow_up():
    """Check task giao > 2 ngày chưa update → hỏi assignee."""
    # TODO: implement follow-up logic
    # Cần track last_updated per task → so sánh với ngày hiện tại
    # Phase 2 sẽ thêm field updated_at vào Tasks
    pass


async def start(settings: Settings):
    global _scheduler, _settings
    _settings = settings
    tz = settings.timezone
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_morning_review, CronTrigger(hour=8, timezone=tz))
    _scheduler.add_job(_evening_summary, CronTrigger(hour=17, timezone=tz))
    _scheduler.add_job(_check_deadlines, CronTrigger(hour=9, minute=30, timezone=tz))
    _scheduler.add_job(_check_reminders, IntervalTrigger(minutes=1))
    _scheduler.start()
    logger.info("Scheduler started")


async def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)
```

**Step 2: Commit**

```bash
git add src/scheduler.py
git commit -m "feat: scheduler with smart review, deadline alerts, reminders"
```

---

### Task 11: Rewrite main.py

**Files:**
- Rewrite: `src/main.py`

**Step 1: Viết lại `src/main.py`**

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-10s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

from src import agent, db, scheduler
from src.config import Settings
from src.services import cohere, lark, openai_client, qdrant, telegram


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = Settings()

    # Init services
    await db.init_db(settings.db_path)
    openai_client.init_openai(
        settings.openai_api_key,
        settings.openai_chat_model,
        settings.openai_embedding_model,
    )
    await qdrant.init_qdrant(settings.qdrant_url)
    await cohere.init_cohere(settings.cohere_api_key)
    await lark.init_lark(settings.lark_app_id, settings.lark_app_secret)
    await telegram.init_telegram(settings.telegram_bot_token)

    # Init agent
    agent.init_agent(settings)

    # Start scheduler + polling
    await scheduler.start(settings)
    polling_task = asyncio.create_task(
        telegram.start_polling(agent.handle_message)
    )

    yield

    # Shutdown
    telegram.stop_polling()
    polling_task.cancel()
    await scheduler.stop()
    await telegram.close_telegram()
    await lark.close_lark()
    await cohere.close_cohere()
    await qdrant.close_qdrant()
    await db.close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: main app updated for v2 architecture"
```

---

## Phase 5: Integration & Polish

---

### Task 12: Update requirements + docker

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example` (đã làm ở Task 1)

**Step 1: Update `requirements.txt`**

```
fastapi==0.115.12
uvicorn==0.34.2
httpx==0.28.1
openai==1.82.0
aiosqlite==0.21.0
apscheduler==3.11.0
pydantic-settings==2.9.1
qdrant-client==1.14.2
```

Không cần thêm gì — DuckDuckGo dùng httpx gọi trực tiếp, không cần lib riêng.

**Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: update requirements for v2"
```

---

### Task 13: End-to-end smoke test

**Step 1: Start services**

```bash
docker compose up -d qdrant
```

**Step 2: Chạy app local**

```bash
python -m uvicorn src.main:app --port 8000
```

**Step 3: Test flow**

Trên Telegram:
1. Nhắn bot từ account mới → kiểm tra onboarding flow sếp
2. Nhắn bot từ account khác → onboard member
3. Sếp giao task → check create_task + thinking UX
4. Member xem task → check phân quyền
5. Sếp hỏi chiến lược → check escalate_to_advisor
6. Check summary sáng (trigger thủ công hoặc đợi cron)

**Step 4: Fix bugs nếu có**

**Step 5: Commit fixes**

```bash
git add -A
git commit -m "fix: integration fixes from smoke test"
```

---

### Task 14: SQLite backup cron

**Files:**
- Create: `scripts/backup.py`

**Step 1: Viết `scripts/backup.py`**

```python
"""Daily backup script cho SQLite. Chạy bằng cron hoặc APScheduler."""
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = "data/history.db"
BACKUP_DIR = Path("data/backups")
MAX_BACKUPS = 7


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"history_{timestamp}.db"
    shutil.copy2(DB_PATH, dest)
    print(f"Backup: {dest}")

    # Xóa backup cũ
    backups = sorted(BACKUP_DIR.glob("history_*.db"))
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        oldest.unlink()
        print(f"Deleted old backup: {oldest}")


if __name__ == "__main__":
    backup()
```

**Step 2: Commit**

```bash
git add scripts/backup.py
git commit -m "feat: add SQLite daily backup script"
```

---

## Summary — Execution Order

| Phase | Tasks | Mô tả |
|-------|-------|-------|
| 1. Foundation | 1-4 | DB schema, Lark provisioning, Qdrant multi-collection, Telegram upgrade |
| 2. Tools | 5-6 | Context resolver, tất cả 26 tools |
| 3. Agents | 7-9 | Secretary, Advisor, Onboarding |
| 4. App | 10-11 | Scheduler, Main app |
| 5. Polish | 12-14 | Requirements, smoke test, backup |

**Ước tính**: 14 tasks, ~2-3 ngày code nếu full-time.

**Lưu ý quan trọng:**
- Phase 1 phải xong trước khi đụng Phase 2 (tools phụ thuộc DB + services mới)
- Task 5 (context resolver) phải xong trước Task 6 (tools)
- Task 7 (secretary) phải xong trước Task 8 (advisor) vì advisor import từ tools
- Task 13 (smoke test) là critical — nhiều bug sẽ xuất hiện ở đây
