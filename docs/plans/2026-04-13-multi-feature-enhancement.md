# Multi-Feature Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 9 major feature groups: multi-membership/unified identity, reminder+note Lark sync (2-way), auto-notification on task assignment, task update approval flow, deadline push, dynamic daily review config, safe /reset mechanism, group message improvements, and unit+integration tests.

**Architecture:** All schema changes are additive via `_migrate_schema()`. New features extend the existing tool-based agent pattern. Lark gains 2 new tables per workspace (Reminders, Notes). SQLite gains 4 new tables. No breaking changes to existing tools — intercept logic added at agent routing layer.

**Tech Stack:** Python 3.11+, FastAPI, APScheduler, aiosqlite, Anthropic SDK (tool use), Lark Bitable API, httpx, pytest + pytest-asyncio

---

## Task 1: Schema Migration — New SQLite Tables

**Files:**
- Modify: `src/db.py`
- Test: `tests/unit/test_db_migration.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_db_migration.py
import pytest, aiosqlite, asyncio
from src.db import get_db, _init_schema

@pytest.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield conn

@pytest.mark.asyncio
async def test_memberships_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memberships'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_memberships_composite_pk(db):
    await db.execute("INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) VALUES ('111', '222', 'member', 'Test', 'active')")
    await db.commit()
    with pytest.raises(Exception):
        await db.execute("INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) VALUES ('111', '222', 'partner', 'Test2', 'active')")
        await db.commit()

@pytest.mark.asyncio
async def test_pending_approvals_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_task_notifications_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_notifications'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_scheduled_reviews_table_exists(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_reviews'") as cur:
        row = await cur.fetchone()
    assert row is not None

@pytest.mark.asyncio
async def test_bosses_has_lark_table_reminders(db):
    async with db.execute("PRAGMA table_info(bosses)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_table_reminders" in cols
    assert "lark_table_notes" in cols
```

**Step 2: Run test to verify it fails**

```bash
cd "/Users/dat_macbook/Documents/2025/ý tưởng mới/Dự án hỗ trợ thứ ký giám đốc ảo"
pytest tests/unit/test_db_migration.py -v
```
Expected: FAIL — tables not found

**Step 3: Implement schema changes in `src/db.py`**

In `_init_schema()`, after existing CREATE TABLE statements, add:

```python
# Replaces people_map (keep people_map for backward compat during migration)
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
```

In `_migrate_schema()`, add:

```python
for col, definition in [
    ("lark_table_reminders", "TEXT DEFAULT ''"),
    ("lark_table_notes",     "TEXT DEFAULT ''"),
]:
    try:
        await db.execute(f"ALTER TABLE bosses ADD COLUMN {col} {definition}")
        await db.commit()
    except Exception:
        pass

# Migrate existing people_map → memberships
try:
    await db.execute("""
        INSERT OR IGNORE INTO memberships (chat_id, boss_chat_id, person_type, name, status)
        SELECT chat_id, boss_chat_id, type, name, 'active'
        FROM people_map
    """)
    await db.commit()
except Exception:
    pass
```

Also add CRUD functions for new tables at bottom of `src/db.py`:

```python
# --- Memberships ---

async def get_memberships(db, chat_id: str) -> list[dict]:
    """All active workspaces a user belongs to."""
    async with db.execute(
        "SELECT * FROM memberships WHERE chat_id = ? AND status = 'active'",
        (str(chat_id),)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]

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
            request_info = excluded.request_info,
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

# --- Pending Approvals ---

async def create_approval(db, boss_chat_id: str, requester_id: str,
                           task_record_id: str, payload: str) -> int:
    import json
    from datetime import datetime, timedelta
    expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()
    async with db.execute("""
        INSERT INTO pending_approvals (boss_chat_id, requester_id, task_record_id, payload, expires_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(boss_chat_id), str(requester_id), task_record_id, payload, expires)) as cur:
        await db.commit()
        return cur.lastrowid

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

# --- Task Notifications ---

async def upsert_task_notification(db, task_record_id: str, boss_chat_id: str,
                                    assignee_chat_id: str = None):
    await db.execute("""
        INSERT OR IGNORE INTO task_notifications (task_record_id, boss_chat_id, assignee_chat_id)
        VALUES (?, ?, ?)
    """, (task_record_id, str(boss_chat_id), str(assignee_chat_id) if assignee_chat_id else None))
    await db.commit()

async def mark_notification_sent(db, task_record_id: str, boss_chat_id: str, kind: str):
    """kind: 'assigned' | '24h' | '2h'"""
    col = {"assigned": "notified_assigned", "24h": "notified_24h", "2h": "notified_2h"}[kind]
    await db.execute(
        f"UPDATE task_notifications SET {col} = 1 WHERE task_record_id = ? AND boss_chat_id = ?",
        (task_record_id, str(boss_chat_id))
    )
    await db.commit()

async def get_unnotified_tasks(db, boss_chat_id: str, kind: str) -> list[dict]:
    col = {"assigned": "notified_assigned", "24h": "notified_24h", "2h": "notified_2h"}[kind]
    async with db.execute(
        f"SELECT * FROM task_notifications WHERE boss_chat_id = ? AND {col} = 0",
        (str(boss_chat_id),)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]

# --- Scheduled Reviews ---

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

async def update_scheduled_review(db, review_id: int, **kwargs):
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    await db.execute(
        f"UPDATE scheduled_reviews SET {sets} WHERE id = ?",
        (*kwargs.values(), review_id)
    )
    await db.commit()

async def delete_scheduled_review(db, review_id: int):
    await db.execute("DELETE FROM scheduled_reviews WHERE id = ?", (review_id,))
    await db.commit()

async def get_all_enabled_reviews(db) -> list[dict]:
    async with db.execute(
        "SELECT * FROM scheduled_reviews WHERE enabled = 1"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_db_migration.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/db.py tests/unit/test_db_migration.py tests/unit/__init__.py tests/__init__.py
git commit -m "feat: add memberships, pending_approvals, task_notifications, scheduled_reviews schema"
```

---

## Task 2: Lark Provisioning — Reminders & Notes Tables

**Files:**
- Modify: `src/services/lark.py`
- Modify: `src/onboarding.py` (provision call)
- Test: `tests/unit/test_lark_provision.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_lark_provision.py
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from src.services import lark as lark_svc

@pytest.mark.asyncio
async def test_provision_workspace_creates_6_tables():
    """provision_workspace should create People, Tasks, Projects, Ideas, Reminders, Notes"""
    with patch.object(lark_svc, "create_base", new_callable=AsyncMock) as mock_base, \
         patch.object(lark_svc, "create_table", new_callable=AsyncMock) as mock_table, \
         patch.object(lark_svc, "delete_table", new_callable=AsyncMock), \
         patch.object(lark_svc, "_get_token", new_callable=AsyncMock, return_value="tok"):
        mock_base.return_value = {"app_token": "base1", "default_table_id": "tbl0"}
        mock_table.side_effect = [
            {"table_id": "tbl1"},
            {"table_id": "tbl2"},
            {"table_id": "tbl3"},
            {"table_id": "tbl4"},
            {"table_id": "tbl5"},
            {"table_id": "tbl6"},
        ]
        result = await lark_svc.provision_workspace("Test Co")
    assert mock_table.call_count == 6
    assert "table_reminders" in result
    assert "table_notes" in result
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_lark_provision.py -v
```

**Step 3: Implement in `src/services/lark.py`**

Add after IDEAS_FIELDS:

```python
REMINDERS_FIELDS = [
    {"field_name": "Nội dung",      "type": 1},
    {"field_name": "Thời gian nhắc","type": 1},
    {"field_name": "Người nhận",    "type": 1},
    {"field_name": "Trạng thái",    "type": 1},
    {"field_name": "SQLite ID",     "type": 2},
    {"field_name": "Cập nhật lúc",  "type": 1},
]

NOTES_FIELDS = [
    {"field_name": "Loại",          "type": 1},
    {"field_name": "Ref ID",        "type": 1},
    {"field_name": "Nội dung",      "type": 1},
    {"field_name": "SQLite ID",     "type": 2},
    {"field_name": "Cập nhật lúc",  "type": 1},
]
```

Update `provision_workspace()` to create 6 tables and return 2 extra keys:

```python
async def provision_workspace(company_name: str) -> dict:
    base = await create_base(f"{company_name} - AI Secretary")
    base_token = base["app_token"]
    default_tbl = base["default_table_id"]

    people_tbl    = (await create_table(base_token, "People",    PEOPLE_FIELDS))["table_id"]
    tasks_tbl     = (await create_table(base_token, "Tasks",     TASKS_FIELDS))["table_id"]
    projects_tbl  = (await create_table(base_token, "Projects",  PROJECTS_FIELDS))["table_id"]
    ideas_tbl     = (await create_table(base_token, "Ideas",     IDEAS_FIELDS))["table_id"]
    reminders_tbl = (await create_table(base_token, "Reminders", REMINDERS_FIELDS))["table_id"]
    notes_tbl     = (await create_table(base_token, "Notes",     NOTES_FIELDS))["table_id"]

    await delete_table(base_token, default_tbl)

    return {
        "base_token":        base_token,
        "table_people":      people_tbl,
        "table_tasks":       tasks_tbl,
        "table_projects":    projects_tbl,
        "table_ideas":       ideas_tbl,
        "table_reminders":   reminders_tbl,
        "table_notes":       notes_tbl,
    }
```

**Step 4: Update `src/onboarding.py` `_step_boss_confirm()`**

Where `provision_workspace` result is used to call `db.create_boss()`, add the two new table IDs:

```python
ws = await lark.provision_workspace(company)
await db.create_boss(
    db=_db,
    chat_id=chat_id,
    name=state["name"],
    company=company,
    lark_base_token=ws["base_token"],
    lark_table_people=ws["table_people"],
    lark_table_tasks=ws["table_tasks"],
    lark_table_projects=ws["table_projects"],
    lark_table_ideas=ws["table_ideas"],
    lark_table_reminders=ws["table_reminders"],
    lark_table_notes=ws["table_notes"],
)
```

Also update `db.create_boss()` in `src/db.py` to accept and store these fields.

**Step 5: Run tests**

```bash
pytest tests/unit/test_lark_provision.py -v
```

**Step 6: Commit**

```bash
git add src/services/lark.py src/onboarding.py src/db.py tests/unit/test_lark_provision.py
git commit -m "feat: add Reminders and Notes tables to Lark workspace provisioning"
```

---

## Task 3: Multi-Workspace Context Resolution

**Files:**
- Modify: `src/context.py`
- Test: `tests/unit/test_context.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_context.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.context import resolve

def make_membership(boss_chat_id, person_type="member"):
    return {"chat_id": "111", "boss_chat_id": str(boss_chat_id), "person_type": person_type,
            "name": "Test User", "status": "active"}

def make_boss(chat_id="222"):
    return {"chat_id": str(chat_id), "name": "Boss", "company": "Co A",
            "lark_base_token": "tok", "lark_table_people": "t1",
            "lark_table_tasks": "t2", "lark_table_projects": "t3",
            "lark_table_ideas": "t4", "lark_table_reminders": "t5", "lark_table_notes": "t6"}

@pytest.mark.asyncio
async def test_single_workspace_resolves_directly():
    with patch("src.context.db.get_memberships", new_callable=AsyncMock,
               return_value=[make_membership("222")]) as mock_mem, \
         patch("src.context.db.get_boss", new_callable=AsyncMock,
               return_value=make_boss("222")):
        ctx = await resolve(chat_id=111, sender_id=111, is_group=False)
    assert ctx is not None
    assert ctx.boss_chat_id == 222

@pytest.mark.asyncio
async def test_unknown_user_returns_none():
    with patch("src.context.db.get_memberships", new_callable=AsyncMock, return_value=[]), \
         patch("src.context.db.get_group", new_callable=AsyncMock, return_value=None), \
         patch("src.context.db.get_boss", new_callable=AsyncMock, return_value=None):
        ctx = await resolve(chat_id=999, sender_id=999, is_group=False)
    assert ctx is None
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_context.py -v
```

**Step 3: Rewrite `src/context.py`**

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from src import db as db_mod
from src.config import get_settings

_db = None

def init_context(database):
    global _db
    _db = database

@dataclass
class ChatContext:
    sender_chat_id: int
    sender_name: str
    sender_type: str          # boss | member | partner | unknown
    boss_chat_id: int | None
    boss_name: str
    lark_base_token: str
    lark_table_people: str
    lark_table_tasks: str
    lark_table_projects: str
    lark_table_ideas: str
    lark_table_reminders: str
    lark_table_notes: str
    chat_id: int
    is_group: bool
    group_name: str
    messages_collection: str
    tasks_collection: str
    all_memberships: list[dict] = field(default_factory=list)  # all workspaces user belongs to

async def resolve(chat_id: int, sender_id: int, is_group: bool,
                  preferred_boss_id: int | None = None) -> ChatContext | None:
    """
    Resolve context for a message.
    preferred_boss_id: if set, use that workspace (for explicit workspace selection).
    """
    settings = get_settings()
    
    # Group chat: resolve via group_map
    if is_group:
        group = await db_mod.get_group(_db, chat_id)
        if not group:
            return None
        boss = await db_mod.get_boss(_db, group["boss_chat_id"])
        if not boss:
            return None
        membership = await db_mod.get_membership(_db, str(sender_id), str(boss["chat_id"]))
        sender_type = membership["person_type"] if membership else "unknown"
        sender_name = membership["name"] if membership else str(sender_id)
        return _build_ctx(boss, sender_id, sender_name, sender_type,
                          chat_id, is_group, group.get("group_name", ""), [])

    # Direct message: get all memberships
    memberships = await db_mod.get_memberships(_db, str(sender_id))
    
    # Also check if sender is a boss themselves
    boss_self = await db_mod.get_boss(_db, str(sender_id))
    if boss_self:
        self_membership = {"chat_id": str(sender_id), "boss_chat_id": str(sender_id),
                           "person_type": "boss", "name": boss_self["name"], "status": "active"}
        if not any(m["boss_chat_id"] == str(sender_id) for m in memberships):
            memberships.insert(0, self_membership)

    if not memberships:
        return None

    # Preferred workspace (explicit selection)
    if preferred_boss_id:
        m = next((m for m in memberships if m["boss_chat_id"] == str(preferred_boss_id)), None)
        if m:
            boss = await db_mod.get_boss(_db, m["boss_chat_id"])
            return _build_ctx(boss, sender_id, m["name"], m["person_type"],
                              chat_id, is_group, "", memberships)

    # Single workspace: use directly
    if len(memberships) == 1:
        m = memberships[0]
        boss = await db_mod.get_boss(_db, m["boss_chat_id"])
        return _build_ctx(boss, sender_id, m["name"], m["person_type"],
                          chat_id, is_group, "", memberships)

    # Multiple workspaces: return with all_memberships populated, let agent decide
    # Default to first (boss's own workspace if exists, else first)
    primary = next((m for m in memberships if m["person_type"] == "boss"), memberships[0])
    boss = await db_mod.get_boss(_db, primary["boss_chat_id"])
    return _build_ctx(boss, sender_id, primary["name"], primary["person_type"],
                      chat_id, is_group, "", memberships)


def _build_ctx(boss, sender_id, sender_name, sender_type,
               chat_id, is_group, group_name, all_memberships) -> ChatContext:
    return ChatContext(
        sender_chat_id=int(sender_id),
        sender_name=sender_name,
        sender_type=sender_type,
        boss_chat_id=int(boss["chat_id"]),
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        lark_table_reminders=boss.get("lark_table_reminders", ""),
        lark_table_notes=boss.get("lark_table_notes", ""),
        chat_id=int(chat_id),
        is_group=is_group,
        group_name=group_name,
        messages_collection=f"messages_{boss['chat_id']}",
        tasks_collection=f"tasks_{boss['chat_id']}",
        all_memberships=all_memberships,
    )
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_context.py -v
```

**Step 5: Commit**

```bash
git add src/context.py tests/unit/test_context.py
git commit -m "feat: multi-workspace context resolution with unified identity"
```

---

## Task 4: Join Request Flow (Onboarding Update)

**Files:**
- Modify: `src/onboarding.py`
- Modify: `src/agent.py` (handle boss approval reply)
- Test: `tests/unit/test_onboarding_join.py`

**Step 1: Write failing test**

```python
# tests/unit/test_onboarding_join.py
import pytest
from unittest.mock import AsyncMock, patch
from src import onboarding

@pytest.mark.asyncio
async def test_list_companies_starts_join_flow():
    onboarding._onboarding.clear()
    with patch("src.onboarding._db"), \
         patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock,
               return_value=[{"chat_id": "1", "name": "Anh X", "company": "Công ty A"}]):
        reply = await onboarding.handle_join_inquiry(chat_id=999)
    assert "Công ty A" in reply
    assert 999 in onboarding._join_sessions

@pytest.mark.asyncio
async def test_join_session_stores_target_boss():
    onboarding._join_sessions[999] = {"step": "pick_company", "bosses": [
        {"chat_id": "1", "name": "Anh X", "company": "Công ty A"}
    ]}
    with patch("src.onboarding._ai_classify", new_callable=AsyncMock,
               return_value={"index": 0}):
        reply = await onboarding.handle_join_message("Công ty A", chat_id=999)
    assert onboarding._join_sessions[999]["step"] == "pick_role"
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_onboarding_join.py -v
```

**Step 3: Add join flow to `src/onboarding.py`**

Add after existing imports and `_onboarding` dict:

```python
_join_sessions: dict[int, dict] = {}  # chat_id → join session state

_CLASSIFY_BOSS_PICK_PROMPT = """
Người dùng đang chọn công ty trong danh sách. Trả về JSON {"index": N} với N là index (0-based) của công ty được chọn, hoặc {"index": -1} nếu không rõ.
Danh sách: {boss_list}
"""

async def handle_join_inquiry(chat_id: int) -> str:
    """Called when user asks about joining a company. Returns listing message."""
    bosses = await db.get_all_bosses(_db)
    if not bosses:
        return "Hiện chưa có tổ chức nào được đăng ký trên hệ thống."
    
    lines = ["Các tổ chức hiện đang hoạt động:\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} — sếp: {b['name']}")
    lines.append("\nBạn muốn join tổ chức nào với tư cách nào (nhân viên/đối tác)?")
    
    _join_sessions[chat_id] = {"step": "pick_company", "bosses": bosses}
    return "\n".join(lines)

async def is_join_session(chat_id: int) -> bool:
    return chat_id in _join_sessions

async def handle_join_message(text: str, chat_id: int) -> str:
    session = _join_sessions.get(chat_id)
    if not session:
        return ""
    
    step = session["step"]

    if step == "pick_company":
        bosses = session["bosses"]
        boss_list = [f"{i}: {b['company']}" for i, b in enumerate(bosses)]
        result = await _ai_classify(
            _CLASSIFY_BOSS_PICK_PROMPT.format(boss_list=boss_list), text
        )
        idx = result.get("index", -1)
        if idx < 0 or idx >= len(bosses):
            return "Tôi chưa rõ bạn muốn join tổ chức nào. Bạn có thể nói lại không?"
        session["target_boss"] = bosses[idx]
        session["step"] = "pick_role"
        return f"Bạn muốn join {bosses[idx]['company']} với tư cách nhân viên hay đối tác?"

    if step == "pick_role":
        lower = text.lower()
        if "đối tác" in lower or "partner" in lower:
            session["role"] = "partner"
        elif "nhân viên" in lower or "member" in lower:
            session["role"] = "member"
        else:
            return "Bạn muốn join với tư cách nhân viên hay đối tác?"
        session["step"] = "get_info"
        return "Bạn có thể giới thiệu về bản thân không? (tên, vai trò, lý do muốn join...)"

    if step == "get_info":
        session["request_info"] = text
        session["step"] = "done"
        
        # Extract name
        name_result = await _ai_classify(_EXTRACT_NAME_PROMPT, text)
        session["name"] = name_result.get("name", "Không rõ")
        
        boss = session["target_boss"]
        role = session["role"]
        
        # Save pending membership
        import json
        await db.upsert_membership(
            _db,
            chat_id=str(chat_id),
            boss_chat_id=str(boss["chat_id"]),
            person_type=role,
            name=session["name"],
            status="pending",
            request_info=text,
        )
        
        # Notify boss
        request_msg = (
            f"📩 Yêu cầu join tổ chức mới!\n\n"
            f"Người dùng chat_id={chat_id} muốn join với tư cách **{role}**.\n"
            f"Thông tin: {text}\n\n"
            f"Reply 'approve {chat_id}', 'reject {chat_id}', hoặc "
            f"'approve {chat_id} nhân viên nhóm Marketing' để điều chỉnh."
        )
        from src.services import telegram as tg
        await tg.send_message(boss["chat_id"], request_msg)
        
        del _join_sessions[chat_id]
        return (f"Yêu cầu của bạn đã được gửi đến {boss['company']}. "
                f"Bạn sẽ được thông báo khi sếp xử lý.")
```

Add boss approval handler (called from `agent.py` when boss replies with approve/reject pattern):

```python
async def handle_boss_join_decision(text: str, boss_chat_id: str) -> str | None:
    """
    Returns response string if handled, None if not a join decision.
    Patterns: 'approve <chat_id>', 'reject <chat_id>', 'approve <chat_id> <adjustments>'
    """
    import re
    m = re.match(r'(approve|reject)\s+(\d+)(.*)?', text.strip().lower())
    if not m:
        return None
    
    action, target_id, adjustments = m.group(1), m.group(2), m.group(3).strip()
    membership = await db.get_membership(_db, target_id, boss_chat_id)
    if not membership or membership["status"] != "pending":
        return None
    
    from src.services import telegram as tg
    boss = await db.get_boss(_db, boss_chat_id)
    
    if action == "reject":
        await db.upsert_membership(_db, target_id, boss_chat_id,
                                   membership["person_type"], membership["name"], "rejected")
        await tg.send_message(target_id,
            f"Yêu cầu join {boss['company']} của bạn đã bị từ chối.")
        return f"Đã từ chối yêu cầu của user {target_id}."
    
    # Approve — parse adjustments if any
    person_type = membership["person_type"]
    if adjustments:
        if "đối tác" in adjustments or "partner" in adjustments:
            person_type = "partner"
        elif "nhân viên" in adjustments or "member" in adjustments:
            person_type = "member"
    
    # Add to Lark People table
    from src.services import lark as lark_svc
    fields = {
        "Tên": membership["name"],
        "Chat ID": int(target_id),
        "Type": person_type,
        "Ghi chú": membership.get("request_info", ""),
    }
    rec = await lark_svc.create_record(boss["lark_base_token"], boss["lark_table_people"], fields)
    
    await db.upsert_membership(_db, target_id, boss_chat_id, person_type,
                               membership["name"], "active",
                               lark_record_id=rec.get("record_id"))
    
    await tg.send_message(target_id,
        f"Chúc mừng! Bạn đã được chấp nhận vào {boss['company']} với tư cách {person_type}. "
        f"Hãy bắt đầu trò chuyện với thư ký AI của tổ chức.")
    
    return f"Đã approve user {target_id} với tư cách {person_type}."
```

**Step 4: Wire join flow into `src/agent.py`**

In `handle_message()`, before context resolve, add:

```python
# Check join session
from src import onboarding
if await onboarding.is_join_session(sender_id):
    reply = await onboarding.handle_join_message(text, sender_id)
    await tg.send_or_edit(chat_id, reply)
    return

# Check boss join decision  
if ctx and ctx.sender_type == "boss":
    decision = await onboarding.handle_boss_join_decision(text, str(ctx.boss_chat_id))
    if decision:
        await tg.send_or_edit(chat_id, decision)
        return

# Detect join inquiry intent (via simple keyword check, AI handles nuance)
join_keywords = ["xem danh sách công ty", "muốn join", "muốn đăng ký", "danh sách tổ chức"]
if any(k in text.lower() for k in join_keywords):
    reply = await onboarding.handle_join_inquiry(sender_id)
    await tg.send_or_edit(chat_id, reply)
    return
```

**Step 5: Run tests**

```bash
pytest tests/unit/test_onboarding_join.py -v
```

**Step 6: Commit**

```bash
git add src/onboarding.py src/agent.py tests/unit/test_onboarding_join.py
git commit -m "feat: join request flow with boss approve/reject/adjust"
```

---

## Task 5: Task Assignment Validation + Auto-Notification

**Files:**
- Modify: `src/tools/tasks.py`
- Modify: `src/agent.py` (send notification after task creation)
- Test: `tests/unit/test_task_notification.py`

**Step 1: Write failing test**

```python
# tests/unit/test_task_notification.py
import pytest, json
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_create_task_notifies_assignee(monkeypatch):
    from src.tools import tasks as tasks_mod
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.lark_table_tasks = "tbl"
    ctx.lark_base_token = "tok"
    ctx.tasks_collection = "col"
    ctx.sender_name = "Sếp"

    with patch("src.tools.tasks.lark.create_record", new_callable=AsyncMock,
               return_value={"record_id": "rec1", "Tên task": "Fix bug"}), \
         patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock,
               return_value=[{"Tên": "Anh Minh", "Chat ID": 456}]), \
         patch("src.tools.tasks.db.upsert_task_notification", new_callable=AsyncMock), \
         patch("src.tools.tasks.notify_assignee", new_callable=AsyncMock) as mock_notify, \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("src.tools.tasks.db.get_memberships", new_callable=AsyncMock,
               return_value=[{"boss_chat_id": "1"}]):

        result = await tasks_mod.create_task(
            ctx, name="Fix bug", assignee="Anh Minh",
            deadline="2026-04-20", priority="Cao"
        )
    mock_notify.assert_called_once()

@pytest.mark.asyncio
async def test_create_task_warns_unknown_assignee():
    from src.tools import tasks as tasks_mod
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.lark_table_tasks = "tbl"
    ctx.lark_base_token = "tok"
    ctx.tasks_collection = "col"
    ctx.sender_name = "Sếp"

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[]), \
         patch("src.tools.tasks.lark.create_record", new_callable=AsyncMock,
               return_value={"record_id": "rec1"}), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("src.tools.tasks.db.upsert_task_notification", new_callable=AsyncMock):
        result = await tasks_mod.create_task(
            ctx, name="Fix bug", assignee="Người lạ", deadline="2026-04-20"
        )
    assert "không tìm thấy" in result.lower() or "chưa có tài khoản" in result.lower()
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_task_notification.py -v
```

**Step 3: Update `src/tools/tasks.py`**

Add at top:

```python
from src import db as db_mod
from src.services import telegram as tg
```

Add helper function:

```python
async def _find_assignee_chat_id(ctx, assignee_name: str) -> tuple[str | None, bool]:
    """
    Returns (chat_id_or_None, found_in_people_table).
    Searches Lark People table for assignee, then checks memberships for chat_id.
    """
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    for r in records:
        if assignee_name.lower() in (r.get("Tên", "") + r.get("Tên gọi", "")).lower():
            chat_id = r.get("Chat ID")
            return (str(int(chat_id)) if chat_id else None, True)
    return (None, False)

async def notify_assignee(chat_id: str, task_name: str, deadline: str,
                           assigner_name: str, record_id: str, boss_chat_id: str):
    """Send task assignment notification to assignee."""
    msg = (
        f"📋 Bạn vừa được giao task mới!\n\n"
        f"Task: {task_name}\n"
        f"Deadline: {deadline or 'Chưa xác định'}\n"
        f"Giao bởi: {assigner_name}\n\n"
        f"Reply để xác nhận đã nhận, hỏi thêm thông tin, hoặc đề xuất thay đổi nhé."
    )
    await tg.send_message(int(chat_id), msg)
```

Update `create_task()` to add validation and notification:

```python
async def create_task(ctx, name: str, assignee: str = "", deadline: str = "",
                      priority: str = "Trung bình", project: str = "",
                      start_time: str = "", location: str = "",
                      original_message: str = "") -> str:
    
    # Validate assignee
    warning = ""
    assignee_chat_id = None
    if assignee:
        assignee_chat_id, found = await _find_assignee_chat_id(ctx, assignee)
        if not found:
            warning = (f"\n\n⚠️ Không tìm thấy '{assignee}' trong danh sách nhân sự. "
                      f"Task vẫn được tạo nhưng sẽ không tự động thông báo được.")
        elif not assignee_chat_id:
            warning = (f"\n\n⚠️ '{assignee}' có trong danh sách nhân sự nhưng chưa có tài khoản liên kết — "
                      f"sẽ không tự động nhận thông báo.")

    # ... existing create logic ...
    deadline_ms = _date_to_ms(deadline) if deadline else None
    fields = {
        "Tên task": name,
        "Assignee": assignee,
        "Deadline": deadline_ms,
        "Priority": priority,
        "Project": project,
        "Start time": _date_to_ms(start_time) if start_time else None,
        "Location": location,
        "Tin nhắn gốc": original_message,
        "Giao bởi": ctx.sender_name,
        "Status": "Chưa làm",
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_tasks, fields)
    record_id = record["record_id"]

    asyncio.create_task(_embed_and_upsert(ctx, record_id, fields))
    
    # Track notification
    await db_mod.upsert_task_notification(
        _db, record_id, str(ctx.boss_chat_id), assignee_chat_id
    )
    
    # Notify assignee
    if assignee_chat_id:
        asyncio.create_task(notify_assignee(
            assignee_chat_id, name, deadline,
            ctx.sender_name, record_id, str(ctx.boss_chat_id)
        ))
    
    return f"✅ Đã tạo task '{name}' (ID: {record_id}).{warning}"
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_task_notification.py -v
```

**Step 5: Commit**

```bash
git add src/tools/tasks.py tests/unit/test_task_notification.py
git commit -m "feat: task assignment validation and auto-notification to assignee"
```

---

## Task 6: Task Update Approval Flow

**Files:**
- Modify: `src/tools/tasks.py`
- Modify: `src/agent.py`
- Test: `tests/unit/test_approval_flow.py`

**Step 1: Write failing test**

```python
# tests/unit/test_approval_flow.py
import pytest, json
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_member_update_creates_pending_approval():
    from src.tools import tasks as tasks_mod
    ctx = MagicMock()
    ctx.sender_type = "member"
    ctx.sender_chat_id = 456
    ctx.boss_chat_id = 1
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"
    ctx.sender_name = "Anh Minh"

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock,
               return_value=[{"record_id": "rec1", "Tên task": "Fix bug", "Status": "Chưa làm"}]), \
         patch("src.tools.tasks.db.create_approval", new_callable=AsyncMock, return_value=1) as mock_approval, \
         patch("src.tools.tasks.tg.send_message", new_callable=AsyncMock):
        
        result = await tasks_mod.update_task(ctx, search_keyword="Fix bug", status="Đang làm")
    
    mock_approval.assert_called_once()
    assert "chờ" in result.lower() or "sếp" in result.lower()

@pytest.mark.asyncio
async def test_boss_update_applies_directly():
    from src.tools import tasks as tasks_mod
    ctx = MagicMock()
    ctx.sender_type = "boss"
    ctx.boss_chat_id = 1
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock,
               return_value=[{"record_id": "rec1", "Tên task": "Fix bug"}]), \
         patch("src.tools.tasks.lark.update_record", new_callable=AsyncMock), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock):
        result = await tasks_mod.update_task(ctx, search_keyword="Fix bug", status="Đang làm")
    
    assert "cập nhật" in result.lower() or "updated" in result.lower()
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_approval_flow.py -v
```

**Step 3: Update `update_task()` in `src/tools/tasks.py`**

```python
async def update_task(ctx, search_keyword: str, status: str = None, deadline: str = None,
                      priority: str = None, assignee: str = None, name: str = None) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    matches = [r for r in records if search_keyword.lower() in r.get("Tên task", "").lower()]
    
    if not matches:
        return f"Không tìm thấy task nào khớp với '{search_keyword}'."
    
    updates = {}
    if status:   updates["Status"] = status
    if deadline: updates["Deadline"] = _date_to_ms(deadline)
    if priority: updates["Priority"] = priority
    if assignee: updates["Assignee"] = assignee
    if name:     updates["Tên task"] = name

    # Non-boss: create pending approval
    if ctx.sender_type in ("member", "partner"):
        import json
        record = matches[0]
        payload = json.dumps({
            "record_id": record["record_id"],
            "task_name": record.get("Tên task", ""),
            "changes": updates,
        })
        approval_id = await db_mod.create_approval(
            _db, str(ctx.boss_chat_id), str(ctx.sender_chat_id),
            record["record_id"], payload
        )
        
        # Get boss to notify
        boss = await db_mod.get_boss(_db, str(ctx.boss_chat_id))
        changes_str = ", ".join(f"{k}: {v}" for k, v in updates.items())
        msg = (
            f"📝 Yêu cầu cập nhật task từ {ctx.sender_name}:\n\n"
            f"Task: {record.get('Tên task')}\n"
            f"Thay đổi: {changes_str}\n\n"
            f"Reply 'approve #{approval_id}', 'reject #{approval_id}', "
            f"hoặc điều chỉnh và approve."
        )
        asyncio.create_task(tg.send_message(ctx.boss_chat_id, msg))
        
        return (f"Yêu cầu cập nhật task '{record.get('Tên task')}' đã gửi đến sếp. "
                f"Bạn sẽ được thông báo khi được xử lý.")
    
    # Boss: apply directly
    updated = 0
    for record in matches:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks,
                                  record["record_id"], updates)
        asyncio.create_task(_embed_and_upsert(ctx, record["record_id"],
                                               {**record, **updates}))
        updated += 1
    return f"✅ Đã cập nhật {updated} task."
```

Add approval decision handler in `src/agent.py` (in boss message handling):

```python
async def _handle_approval_decision(text: str, ctx) -> str | None:
    """Returns response if handled, None otherwise."""
    import re, json
    m = re.match(r'(approve|reject)\s+#(\d+)(.*)?', text.strip().lower())
    if not m:
        return None
    
    action, approval_id, adjustments = m.group(1), int(m.group(2)), m.group(3).strip()
    
    approvals = await db_mod.get_pending_approvals(_db, str(ctx.boss_chat_id))
    approval = next((a for a in approvals if a["id"] == approval_id), None)
    if not approval:
        return None
    
    payload = json.loads(approval["payload"])
    requester_id = approval["requester_id"]
    
    if action == "reject":
        await db_mod.update_approval_status(_db, approval_id, "rejected")
        await tg.send_message(int(requester_id),
            f"Yêu cầu cập nhật task '{payload['task_name']}' của bạn đã bị từ chối.")
        return f"Đã từ chối yêu cầu #{approval_id}."
    
    # Apply changes
    changes = payload["changes"]
    await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks,
                              payload["record_id"], changes)
    await db_mod.update_approval_status(_db, approval_id, "approved")
    
    changes_str = ", ".join(f"{k}: {v}" for k, v in changes.items())
    await tg.send_message(int(requester_id),
        f"✅ Yêu cầu cập nhật task '{payload['task_name']}' đã được sếp chấp nhận. "
        f"Thay đổi: {changes_str}")
    
    return f"Đã approve và áp dụng thay đổi cho task '{payload['task_name']}'."
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_approval_flow.py -v
```

**Step 5: Commit**

```bash
git add src/tools/tasks.py src/agent.py tests/unit/test_approval_flow.py
git commit -m "feat: task update approval flow for non-boss users"
```

---

## Task 7: Deadline Push Notifications

**Files:**
- Modify: `src/scheduler.py`
- Test: `tests/unit/test_deadline_push.py`

**Step 1: Write failing test**

```python
# tests/unit/test_deadline_push.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

@pytest.mark.asyncio
async def test_deadline_push_sends_24h_notification():
    from src import scheduler
    
    deadline_ms = int((datetime.utcnow() + timedelta(hours=20)).timestamp() * 1000)
    mock_boss = {"chat_id": "1", "lark_base_token": "tok", "lark_table_tasks": "tbl"}
    mock_task = {"record_id": "rec1", "Tên task": "Fix bug",
                 "Deadline": deadline_ms, "Status": "Chưa làm", "Assignee": "Anh Minh"}
    mock_notif = {"task_record_id": "rec1", "boss_chat_id": "1",
                  "assignee_chat_id": "456", "notified_24h": 0, "notified_2h": 0}

    with patch("src.scheduler.db.get_all_bosses", new_callable=AsyncMock, return_value=[mock_boss]), \
         patch("src.scheduler.lark.search_records", new_callable=AsyncMock, return_value=[mock_task]), \
         patch("src.scheduler.db.get_unnotified_tasks", new_callable=AsyncMock, return_value=[mock_notif]), \
         patch("src.scheduler.db.mark_notification_sent", new_callable=AsyncMock) as mock_mark, \
         patch("src.scheduler.tg.send_message", new_callable=AsyncMock) as mock_send:
        
        await scheduler._check_deadline_push()
    
    mock_send.assert_called()
    mock_mark.assert_called()
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_deadline_push.py -v
```

**Step 3: Add `_check_deadline_push()` to `src/scheduler.py`**

```python
async def _check_deadline_push():
    """Check for tasks approaching deadline and notify assignees."""
    from datetime import datetime, timezone
    settings = get_settings()
    bosses = await db.get_all_bosses(_db)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    h24_ms = now_ms + 24 * 3600 * 1000
    h2_ms  = now_ms + 2  * 3600 * 1000

    for boss in bosses:
        tasks = await lark.search_records(boss["lark_base_token"], boss["lark_table_tasks"])
        open_tasks = [t for t in tasks if t.get("Status") not in ("Hoàn thành", "Huỷ")]
        
        for task in open_tasks:
            deadline = task.get("Deadline")
            if not deadline:
                continue
            record_id = task["record_id"]
            
            # Determine which kind of notification is due
            kind = None
            if deadline <= h2_ms:
                kind = "2h"
            elif deadline <= h24_ms:
                kind = "24h"
            if not kind:
                continue
            
            # Check if already notified
            notifs = await db.get_unnotified_tasks(_db, boss["chat_id"], kind)
            notif = next((n for n in notifs if n["task_record_id"] == record_id), None)
            if not notif:
                continue
            
            assignee_chat_id = notif.get("assignee_chat_id")
            if assignee_chat_id:
                label = "2 tiếng" if kind == "2h" else "24 tiếng"
                msg = (
                    f"⏰ Nhắc nhở deadline!\n\n"
                    f"Task '{task.get('Tên task')}' còn khoảng {label} nữa đến hạn.\n"
                    f"Hãy cập nhật tiến độ nhé!"
                )
                await tg.send_message(int(assignee_chat_id), msg)
            
            await db.mark_notification_sent(_db, record_id, boss["chat_id"], kind)
```

Add job in `start()`:

```python
scheduler.add_job(_check_deadline_push, IntervalTrigger(minutes=30), id="deadline_push")
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_deadline_push.py -v
```

**Step 5: Commit**

```bash
git add src/scheduler.py tests/unit/test_deadline_push.py
git commit -m "feat: deadline push notifications at 24h and 2h before due"
```

---

## Task 8: Reminder & Note Lark Sync (2-way)

**Files:**
- Modify: `src/services/lark.py`
- Modify: `src/tools/reminder.py`
- Modify: `src/tools/note.py`
- Modify: `src/scheduler.py`
- Test: `tests/unit/test_lark_sync.py`

**Step 1: Write failing test**

```python
# tests/unit/test_lark_sync.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_create_reminder_syncs_to_lark():
    from src.tools import reminder as reminder_mod
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.lark_base_token = "tok"
    ctx.lark_table_reminders = "tbl_rem"
    ctx.sender_name = "Sếp"

    with patch("src.tools.reminder.db.create_reminder", new_callable=AsyncMock, return_value=42), \
         patch("src.tools.reminder.lark.create_record", new_callable=AsyncMock,
               return_value={"record_id": "lrec1"}) as mock_lark, \
         patch("src.tools.reminder.db.get_boss", new_callable=AsyncMock,
               return_value={"lark_table_reminders": "tbl_rem", "lark_base_token": "tok"}), \
         patch("src.tools.reminder._resolve_target", new_callable=AsyncMock, return_value=(None, "Sếp")):
        await reminder_mod.create_reminder(ctx, "Họp lúc 3h", "2026-04-14 15:00")
    
    mock_lark.assert_called_once()
    call_fields = mock_lark.call_args[0][2]
    assert "SQLite ID" in call_fields
    assert call_fields["SQLite ID"] == 42
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_lark_sync.py -v
```

**Step 3: Add sync helpers to `src/services/lark.py`**

```python
async def sync_reminder_to_lark(base_token: str, table_id: str,
                                  reminder: dict, sqlite_id: int) -> str | None:
    """Create or update reminder record in Lark. Returns lark record_id."""
    if not table_id:
        return None
    fields = {
        "Nội dung":      reminder["content"],
        "Thời gian nhắc": reminder.get("remind_at_local", ""),
        "Người nhận":    reminder.get("target_name", ""),
        "Trạng thái":    reminder.get("status", "pending"),
        "SQLite ID":     sqlite_id,
        "Cập nhật lúc":  str(reminder.get("updated_at", "")),
    }
    # Check if already exists by SQLite ID
    existing = await search_records(base_token, table_id,
                                     f'CurrentValue.[SQLite ID] = {sqlite_id}')
    if existing:
        await update_record(base_token, table_id, existing[0]["record_id"], fields)
        return existing[0]["record_id"]
    rec = await create_record(base_token, table_id, fields)
    return rec.get("record_id")

async def sync_note_to_lark(base_token: str, table_id: str,
                              note: dict, sqlite_id: int) -> str | None:
    if not table_id:
        return None
    fields = {
        "Loại":          note.get("type", ""),
        "Ref ID":        str(note.get("ref_id", "")),
        "Nội dung":      note.get("content", ""),
        "SQLite ID":     sqlite_id,
        "Cập nhật lúc":  str(note.get("updated_at", "")),
    }
    existing = await search_records(base_token, table_id,
                                     f'CurrentValue.[SQLite ID] = {sqlite_id}')
    if existing:
        await update_record(base_token, table_id, existing[0]["record_id"], fields)
        return existing[0]["record_id"]
    rec = await create_record(base_token, table_id, fields)
    return rec.get("record_id")
```

**Step 4: Update `create_reminder()` in `src/tools/reminder.py`**

After creating SQLite record, fire-and-forget sync to Lark:

```python
sqlite_id = await db.create_reminder(...)

# Sync to Lark (async, non-blocking)
boss = await db.get_boss(_db, str(ctx.boss_chat_id))
if boss and boss.get("lark_table_reminders"):
    asyncio.create_task(lark.sync_reminder_to_lark(
        boss["lark_base_token"],
        boss["lark_table_reminders"],
        {"content": content, "remind_at_local": remind_at,
         "target_name": target_name, "status": "pending"},
        sqlite_id
    ))
```

Similarly update `update_reminder()` and `delete_reminder()` to sync.

**Step 5: Add Lark→SQLite poll job in `src/scheduler.py`**

```python
async def _sync_lark_to_sqlite():
    """Poll Lark Reminders table and sync changes back to SQLite."""
    bosses = await db.get_all_bosses(_db)
    for boss in bosses:
        if not boss.get("lark_table_reminders"):
            continue
        records = await lark.search_records(
            boss["lark_base_token"], boss["lark_table_reminders"]
        )
        for rec in records:
            sqlite_id = rec.get("SQLite ID")
            if not sqlite_id:
                continue
            # Only update if Lark record is newer (simple: just update content+status)
            await db.sync_reminder_from_lark(
                _db, int(sqlite_id),
                content=rec.get("Nội dung", ""),
                status=rec.get("Trạng thái", "pending"),
            )
```

Add to `start()`:

```python
scheduler.add_job(_sync_lark_to_sqlite, IntervalTrigger(seconds=30), id="lark_sync")
```

Add `sync_reminder_from_lark()` to `src/db.py`:

```python
async def sync_reminder_from_lark(db, sqlite_id: int, content: str, status: str):
    await db.execute(
        "UPDATE reminders SET content = ?, status = ? WHERE id = ?",
        (content, status, sqlite_id)
    )
    await db.commit()
```

**Step 6: Run tests**

```bash
pytest tests/unit/test_lark_sync.py -v
```

**Step 7: Commit**

```bash
git add src/services/lark.py src/tools/reminder.py src/tools/note.py src/scheduler.py src/db.py tests/unit/test_lark_sync.py
git commit -m "feat: 2-way reminder and note sync between SQLite and Lark Base"
```

---

## Task 9: Dynamic Daily Review Config

**Files:**
- Create: `src/tools/review_config.py`
- Modify: `src/scheduler.py`
- Modify: `src/tools/__init__.py`
- Test: `tests/unit/test_review_config.py`

**Step 1: Write failing test**

```python
# tests/unit/test_review_config.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_create_scheduled_review():
    from src.tools import review_config
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.sender_type = "boss"

    with patch("src.tools.review_config.db.create_scheduled_review",
               new_callable=AsyncMock, return_value=1) as mock_create:
        result = await review_config.add_review_schedule(
            ctx, cron_time="15:00", content_type="custom",
            custom_prompt="review tiến độ dự án"
        )
    mock_create.assert_called_once()
    assert "15:00" in result or "thêm" in result.lower()

@pytest.mark.asyncio
async def test_toggle_review_disabled():
    from src.tools import review_config
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.sender_type = "boss"

    with patch("src.tools.review_config.db.list_scheduled_reviews",
               new_callable=AsyncMock,
               return_value=[{"id": 1, "cron_time": "08:00",
                               "content_type": "morning_brief", "enabled": 1}]), \
         patch("src.tools.review_config.db.update_scheduled_review",
               new_callable=AsyncMock) as mock_update:
        result = await review_config.toggle_review(ctx, review_id=1, enabled=False)
    mock_update.assert_called_with(ANY, 1, enabled=0)
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_review_config.py -v
```

**Step 3: Create `src/tools/review_config.py`**

```python
from src import db as db_mod
from src.services import lark

_db = None

def init_review_config(database):
    global _db
    _db = database

async def add_review_schedule(ctx, cron_time: str, content_type: str = "custom",
                               custom_prompt: str = None) -> str:
    if ctx.sender_type != "boss":
        return "Chỉ sếp mới có thể cấu hình lịch review."
    
    # Validate time format HH:MM
    import re
    if not re.match(r'^\d{2}:\d{2}$', cron_time):
        return f"Định dạng giờ không hợp lệ: '{cron_time}'. Dùng định dạng HH:MM (VD: 08:00)."
    
    review_id = await db_mod.create_scheduled_review(
        _db, str(ctx.boss_chat_id), cron_time, content_type, custom_prompt
    )
    return (f"✅ Đã thêm lịch review lúc {cron_time} "
            f"({'tùy chỉnh: ' + custom_prompt if custom_prompt else content_type}). "
            f"ID: #{review_id}")

async def list_review_schedules(ctx) -> str:
    reviews = await db_mod.list_scheduled_reviews(_db, str(ctx.boss_chat_id))
    if not reviews:
        return "Chưa có lịch review nào được cấu hình."
    lines = ["Lịch review hiện tại:\n"]
    for r in reviews:
        status = "✅" if r["enabled"] else "⏸️"
        desc = r.get("custom_prompt") or r["content_type"]
        lines.append(f"{status} #{r['id']} — {r['cron_time']}: {desc}")
    return "\n".join(lines)

async def toggle_review(ctx, review_id: int, enabled: bool) -> str:
    if ctx.sender_type != "boss":
        return "Chỉ sếp mới có thể cấu hình lịch review."
    await db_mod.update_scheduled_review(_db, review_id, enabled=1 if enabled else 0)
    state = "bật" if enabled else "tắt"
    return f"Đã {state} lịch review #{review_id}."

async def delete_review_schedule(ctx, review_id: int) -> str:
    if ctx.sender_type != "boss":
        return "Chỉ sếp mới có thể cấu hình lịch review."
    await db_mod.delete_scheduled_review(_db, review_id)
    return f"Đã xóa lịch review #{review_id}."
```

**Step 4: Update `src/scheduler.py` to load reviews dynamically**

Replace hardcoded morning/evening jobs with dynamic loader:

```python
async def _run_dynamic_reviews():
    """Check all enabled scheduled reviews and fire those matching current time."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    reviews = await db.get_all_enabled_reviews(_db)
    bosses_cache = {}
    
    for review in reviews:
        tz = ZoneInfo(review.get("timezone", "Asia/Ho_Chi_Minh"))
        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")
        if current_time != review["cron_time"]:
            continue
        
        owner_id = review["owner_id"]
        if owner_id not in bosses_cache:
            bosses_cache[owner_id] = await db.get_boss(_db, owner_id)
        boss = bosses_cache[owner_id]
        if not boss:
            continue
        
        content_type = review["content_type"]
        custom_prompt = review.get("custom_prompt", "")
        
        if content_type == "morning_brief":
            await _run_morning_brief(boss, settings)
        elif content_type == "evening_summary":
            await _run_evening_summary(boss, settings)
        elif content_type == "custom" and custom_prompt:
            await _run_custom_review(boss, custom_prompt, settings)

# Replace existing 8am/5pm jobs with:
scheduler.add_job(_run_dynamic_reviews, IntervalTrigger(minutes=1), id="dynamic_reviews")
```

Seed default reviews for existing bosses in migration (one-time, via scheduler startup):

```python
async def _seed_default_reviews():
    bosses = await db.get_all_bosses(_db)
    for boss in bosses:
        existing = await db.list_scheduled_reviews(_db, boss["chat_id"])
        if not existing:
            await db.create_scheduled_review(_db, boss["chat_id"], "08:00", "morning_brief")
            await db.create_scheduled_review(_db, boss["chat_id"], "17:00", "evening_summary")
```

**Step 5: Run tests**

```bash
pytest tests/unit/test_review_config.py -v
```

**Step 6: Commit**

```bash
git add src/tools/review_config.py src/scheduler.py src/tools/__init__.py tests/unit/test_review_config.py
git commit -m "feat: dynamic daily review scheduling with per-user config"
```

---

## Task 10: /reset Workspace — Safe 2-Step Flow

**Files:**
- Create: `src/tools/reset.py`
- Modify: `src/agent.py`
- Test: `tests/unit/test_reset.py`

**Step 1: Write failing test**

```python
# tests/unit/test_reset.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_reset_step1_asks_for_reversed_name():
    from src.tools import reset as reset_mod
    ctx = MagicMock()
    ctx.boss_chat_id = 1
    ctx.boss_name = "Anh Đạt"
    ctx.sender_type = "boss"

    with patch("src.tools.reset.db.get_boss", new_callable=AsyncMock,
               return_value={"company": "CÔNG TY ALPHA", "chat_id": "1"}):
        result, session = await reset_mod.start_reset(ctx)
    
    assert session is not None
    assert "AHPLA" in result  # ALPHA reversed

@pytest.mark.asyncio
async def test_reset_step1_wrong_code_cancels():
    from src.tools import reset as reset_mod
    reset_mod._reset_sessions[1] = {
        "step": 1, "expected": "AHPLA YTGNOOC", "boss_chat_id": 1, "expires": 9999999999
    }
    result = await reset_mod.handle_reset_message("WRONG", boss_chat_id=1)
    assert "sai" in result.lower() or "hủy" in result.lower()
    assert 1 not in reset_mod._reset_sessions

@pytest.mark.asyncio
async def test_reset_step2_executes_on_confirm():
    from src.tools import reset as reset_mod
    import time
    reset_mod._reset_sessions[1] = {
        "step": 2, "boss_chat_id": 1, "expires": time.time() + 300
    }
    with patch("src.tools.reset.lark.search_records", new_callable=AsyncMock, return_value=[]), \
         patch("src.tools.reset.qdrant.delete_collection", new_callable=AsyncMock), \
         patch("src.tools.reset.db.get_boss", new_callable=AsyncMock,
               return_value={"lark_base_token": "tok", "lark_table_people": "t1",
                             "lark_table_tasks": "t2", "lark_table_projects": "t3",
                             "lark_table_ideas": "t4", "lark_table_reminders": "t5",
                             "lark_table_notes": "t6", "chat_id": "1"}):
        result = await reset_mod.handle_reset_message("tôi chắc chắn", boss_chat_id=1)
    assert "hoàn tất" in result.lower() or "xong" in result.lower()
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_reset.py -v
```

**Step 3: Create `src/tools/reset.py`**

```python
import time
from src import db as db_mod
from src.services import lark, qdrant

_db = None
_reset_sessions: dict[int, dict] = {}  # boss_chat_id → session
SESSION_TTL = 300  # 5 minutes

def init_reset(database):
    global _db
    _db = database

def _reverse_upper(text: str) -> str:
    return text.upper()[::-1]

async def start_reset(ctx) -> tuple[str, dict | None]:
    """Initiate reset flow. Returns (message_to_show, session_dict)."""
    if ctx.sender_type != "boss":
        return "Chỉ sếp mới có thể thực hiện reset.", None
    
    boss = await db_mod.get_boss(_db, str(ctx.boss_chat_id))
    company = boss["company"]
    expected = _reverse_upper(company)
    
    session = {
        "step": 1,
        "expected": expected,
        "boss_chat_id": ctx.boss_chat_id,
        "expires": time.time() + SESSION_TTL,
    }
    _reset_sessions[ctx.boss_chat_id] = session
    
    msg = (
        f"⚠️ CẢNH BÁO: Thao tác này sẽ xóa TOÀN BỘ dữ liệu Lark Base của workspace "
        f"'{company}' (Tasks, Projects, People, Ideas, Notes, Reminders).\n"
        f"Dữ liệu SQLite sẽ được giữ nguyên.\n\n"
        f"Bước 1/2: Gõ tên công ty bằng CHỮ HOA và ĐẢO NGƯỢC để xác nhận.\n"
        f"(Ví dụ: 'ABC Corp' → 'PROC CBA')\n\n"
        f"Phiên này sẽ hết hạn sau 5 phút."
    )
    return msg, session

async def handle_reset_message(text: str, boss_chat_id: int) -> str | None:
    """Returns response if handled, None if not a reset session."""
    session = _reset_sessions.get(boss_chat_id)
    if not session:
        return None
    
    # Check expiry
    if time.time() > session["expires"]:
        del _reset_sessions[boss_chat_id]
        return "Phiên xác nhận đã hết hạn. Vui lòng bắt đầu lại."
    
    step = session["step"]
    
    if step == 1:
        if text.strip() != session["expected"]:
            del _reset_sessions[boss_chat_id]
            return (f"❌ Chuỗi xác nhận không đúng. Thao tác đã hủy.\n"
                    f"(Nhập lại /reset nếu muốn thử lại)")
        
        session["step"] = 2
        session["expires"] = time.time() + SESSION_TTL
        return (f"✅ Bước 1 xác nhận thành công.\n\n"
                f"Bước 2/2: Gõ chính xác câu sau để hoàn tất:\n"
                f"tôi chắc chắn")
    
    if step == 2:
        if text.strip().lower() != "tôi chắc chắn":
            del _reset_sessions[boss_chat_id]
            return "❌ Xác nhận không đúng. Thao tác đã hủy."
        
        del _reset_sessions[boss_chat_id]
        await _execute_reset(boss_chat_id)
        return "✅ Reset hoàn tất. Toàn bộ dữ liệu Lark Base đã được xóa. Workspace vẫn hoạt động bình thường."
    
    return None

async def _execute_reset(boss_chat_id: int):
    boss = await db_mod.get_boss(_db, str(boss_chat_id))
    tables = [
        boss.get("lark_table_people"),
        boss.get("lark_table_tasks"),
        boss.get("lark_table_projects"),
        boss.get("lark_table_ideas"),
        boss.get("lark_table_reminders"),
        boss.get("lark_table_notes"),
    ]
    base_token = boss["lark_base_token"]
    
    # Delete all records in each table
    for table_id in tables:
        if not table_id:
            continue
        records = await lark.search_records(base_token, table_id)
        for rec in records:
            try:
                await lark.delete_record(base_token, table_id, rec["record_id"])
            except Exception:
                pass
    
    # Delete Qdrant collections
    for collection in [f"tasks_{boss_chat_id}", f"messages_{boss_chat_id}"]:
        try:
            await qdrant.delete_collection(collection)
        except Exception:
            pass
```

**Step 4: Wire into `src/agent.py`**

In `handle_message()`, near the top (after context resolve), add:

```python
from src.tools import reset as reset_mod

# Check active reset session
if ctx and ctx.sender_type == "boss":
    reset_reply = await reset_mod.handle_reset_message(text, ctx.boss_chat_id)
    if reset_reply:
        await tg.send_or_edit(chat_id, reset_reply)
        return

# Detect /reset trigger
if text.strip().lower() in ("/reset", "reset workspace", "xóa workspace"):
    msg, _ = await reset_mod.start_reset(ctx)
    await tg.send_or_edit(chat_id, msg)
    return
```

**Step 5: Run tests**

```bash
pytest tests/unit/test_reset.py -v
```

**Step 6: Commit**

```bash
git add src/tools/reset.py src/agent.py tests/unit/test_reset.py
git commit -m "feat: safe 2-step /reset workspace flow"
```

---

## Task 11: Group Message — Save All, Process on @mention

**Files:**
- Modify: `src/agent.py`
- Test: `tests/unit/test_group_handling.py`

**Step 1: Write failing test**

```python
# tests/unit/test_group_handling.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_group_message_without_mention_saves_but_no_reply():
    from src import agent
    with patch("src.agent.db.save_message", new_callable=AsyncMock) as mock_save, \
         patch("src.agent.context.resolve", new_callable=AsyncMock, return_value=MagicMock()), \
         patch("src.agent.tg.send_or_edit", new_callable=AsyncMock) as mock_send, \
         patch("src.agent._embed_message", new_callable=AsyncMock):
        
        await agent.handle_message(
            text="bạn ơi hôm nay làm gì",
            chat_id=-100123,
            sender_id=456,
            is_group=True,
            bot_mentioned=False,
        )
    
    mock_save.assert_called_once()
    mock_send.assert_not_called()

@pytest.mark.asyncio
async def test_group_message_with_mention_processes():
    from src import agent
    ctx = MagicMock()
    ctx.sender_type = "member"
    ctx.is_group = True
    
    with patch("src.agent.context.resolve", new_callable=AsyncMock, return_value=ctx), \
         patch("src.agent.db.save_message", new_callable=AsyncMock), \
         patch("src.agent.db.get_recent", new_callable=AsyncMock, return_value=[]), \
         patch("src.agent._embed_message", new_callable=AsyncMock), \
         patch("src.agent.tg.send_or_edit", new_callable=AsyncMock) as mock_send, \
         patch("src.agent._run_agent_loop", new_callable=AsyncMock, return_value="Xin chào!"):
        
        await agent.handle_message(
            text="@ceo_companion_bot bạn khỏe không",
            chat_id=-100123,
            sender_id=456,
            is_group=True,
            bot_mentioned=True,
        )
    
    mock_send.assert_called()
```

**Step 2: Run to verify fails**

```bash
pytest tests/unit/test_group_handling.py -v
```

**Step 3: Review and update group handling in `src/agent.py`**

In `handle_message()`, the existing check at line ~156-174 already handles the basic case. Verify and update to match the spec:

```python
async def handle_message(text: str, chat_id: int, sender_id: int,
                          is_group: bool, bot_mentioned: bool = False):
    settings = get_settings()
    
    # Group message not mentioning bot: save to DB only, no response
    if is_group and not bot_mentioned:
        ctx = await context.resolve(chat_id, sender_id, is_group)
        if ctx:
            await db.save_message(_db, chat_id, sender_id, "user", text)
            asyncio.create_task(_embed_message(ctx, text, "user"))
        return  # No reply
    
    # All other cases: resolve context and process
    # ... rest of existing logic
```

Verify RAG uses 8 results and recent history uses 15:

```python
# In the context gathering section:
rag_results = await qdrant.search(ctx.messages_collection, text, limit=8)  # was potentially different
recent_msgs = await db.get_recent(_db, chat_id, limit=15)  # was potentially different
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_group_handling.py -v
```

**Step 5: Commit**

```bash
git add src/agent.py tests/unit/test_group_handling.py
git commit -m "feat: group chat saves all messages, processes only on @mention with 15+8 context"
```

---

## Task 12: Qdrant ulimits Fix

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Apply fix**

In `docker-compose.yml`, add `ulimits` to the `qdrant` service:

```yaml
  qdrant:
    image: qdrant/qdrant:v1.13.2
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
```

**Step 2: Verify file**

```bash
docker compose config | grep -A5 ulimits
```
Expected: see `nofile: {soft: 65536, hard: 65536}`

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: raise Qdrant file descriptor limit to 65536 to prevent 'too many open files' crash"
```

---

## Task 13: Integration Tests — Key Flows

**Files:**
- Create: `tests/integration/test_task_flow.py`
- Create: `tests/integration/test_membership_flow.py`
- Create: `tests/conftest.py`

**Step 1: Create `tests/conftest.py`**

```python
import pytest
import aiosqlite
from src.db import _init_schema, _migrate_schema

@pytest.fixture
async def test_db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        await _migrate_schema(conn)
        yield conn

@pytest.fixture
def mock_lark():
    from unittest.mock import AsyncMock, MagicMock
    m = MagicMock()
    m.create_record = AsyncMock(return_value={"record_id": "rec_test"})
    m.search_records = AsyncMock(return_value=[])
    m.update_record = AsyncMock()
    m.delete_record = AsyncMock()
    return m

@pytest.fixture
def mock_tg():
    from unittest.mock import AsyncMock
    m = AsyncMock()
    m.send_message = AsyncMock()
    return m
```

**Step 2: Create `tests/integration/test_membership_flow.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch
from src import db as db_mod, onboarding

@pytest.mark.asyncio
async def test_full_join_and_approve_flow(test_db):
    onboarding._db = test_db
    onboarding._join_sessions.clear()
    
    # Seed a boss
    await test_db.execute("""
        INSERT INTO bosses (chat_id, name, company, lark_base_token,
            lark_table_people, lark_table_tasks, lark_table_projects,
            lark_table_ideas, lark_table_reminders, lark_table_notes)
        VALUES ('100', 'Anh Sếp', 'Công ty Alpha', 'tok',
                'tp', 'tt', 'tpr', 'ti', 'tr', 'tn')
    """)
    await test_db.commit()
    
    with patch("src.onboarding.tg.send_message", new_callable=AsyncMock), \
         patch("src.onboarding.lark.create_record", new_callable=AsyncMock,
               return_value={"record_id": "lr1"}):
        
        # Step 1: User asks for company list
        reply = await onboarding.handle_join_inquiry(chat_id=999)
        assert "Công ty Alpha" in reply
        assert onboarding._join_sessions[999]["step"] == "pick_company"
        
        # Step 2: User picks company
        with patch("src.onboarding._ai_classify", new_callable=AsyncMock,
                   return_value={"index": 0}):
            reply = await onboarding.handle_join_message("Công ty Alpha", chat_id=999)
        assert onboarding._join_sessions[999]["step"] == "pick_role"
        
        # Step 3: Pick role
        reply = await onboarding.handle_join_message("đối tác", chat_id=999)
        assert onboarding._join_sessions[999]["step"] == "get_info"
        
        # Step 4: Submit info
        with patch("src.onboarding._ai_classify", new_callable=AsyncMock,
                   return_value={"name": "Anh Bình"}):
            reply = await onboarding.handle_join_message("Tên tôi là Bình, làm freelance design", chat_id=999)
        assert "gửi" in reply.lower()
        
        # Verify pending membership created
        membership = await db_mod.get_membership(test_db, "999", "100")
        assert membership is not None
        assert membership["status"] == "pending"
        assert membership["person_type"] == "partner"
        
        # Step 5: Boss approves
        reply = await onboarding.handle_boss_join_decision("approve 999", boss_chat_id="100")
        assert reply is not None
        assert "approve" in reply.lower() or "999" in reply
        
        # Verify active membership
        membership = await db_mod.get_membership(test_db, "999", "100")
        assert membership["status"] == "active"

@pytest.mark.asyncio
async def test_multi_workspace_membership(test_db):
    """One user active in 2 workspaces."""
    await test_db.execute("""
        INSERT INTO bosses (chat_id, name, company, lark_base_token,
            lark_table_people, lark_table_tasks, lark_table_projects,
            lark_table_ideas, lark_table_reminders, lark_table_notes)
        VALUES ('100', 'Sếp A', 'Công ty A', 'tokA', 'tp', 'tt', 'tpr', 'ti', 'tr', 'tn'),
               ('200', 'Sếp B', 'Công ty B', 'tokB', 'tp', 'tt', 'tpr', 'ti', 'tr', 'tn')
    """)
    await db_mod.upsert_membership(test_db, "999", "100", "member", "Anh Đạt", "active")
    await db_mod.upsert_membership(test_db, "999", "200", "partner", "Anh Đạt", "active")
    
    memberships = await db_mod.get_memberships(test_db, "999")
    assert len(memberships) == 2
    boss_ids = {m["boss_chat_id"] for m in memberships}
    assert "100" in boss_ids
    assert "200" in boss_ids
```

**Step 3: Run integration tests**

```bash
pytest tests/integration/ -v
```

**Step 4: Commit**

```bash
git add tests/ 
git commit -m "test: unit and integration tests for membership, task, approval, group flows"
```

---

## Final Verification

**Run full test suite:**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASS

**Run type check (if mypy configured):**

```bash
mypy src/ --ignore-missing-imports
```

**Smoke test with Docker:**

```bash
docker compose up --build -d
docker compose logs app --tail=50
```

Expected: No errors, scheduler starts, bot polling begins.

**Commit summary tag:**

```bash
git tag v2.0.0-multi-feature
```
