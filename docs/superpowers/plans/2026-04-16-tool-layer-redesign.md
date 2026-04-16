# Tool Layer Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the tool layer to 36 context-aware tools with fat returns, fix Lark sync, add outbound DM logging, communication domain, replace in-memory onboarding state machine, and add proactive scheduler jobs.

**Architecture:** Approach B — thin verbs, fat returns. `workspace_ids` standardized across all tools. Error handling centralized in `execute_tool`. Lark as write-first source of truth. Agent driven by tool descriptions, not hardcoded flows. New `communication.py` and `search.py` domains.

**Tech Stack:** Python 3.11+/asyncio, aiosqlite, Lark Base API (`src/services/lark.py`), Qdrant (`src/services/qdrant.py`), OpenAI embeddings, APScheduler, Telegram Bot API

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/db.py` | Modify | New tables + migration columns |
| `src/tools/_workspace.py` | Modify | `active_workspace_id` resolution |
| `src/tools/__init__.py` | Modify | `execute_tool` error wrapper + all 36 tool definitions |
| `src/tools/communication.py` | **Create** | `send_dm`, `broadcast`, `get_communication_log` |
| `src/tools/search.py` | **Create** | `search_notes` |
| `src/tools/tasks.py` | Modify | Multiple assignees, fat returns, reassign notification, enum validation |
| `src/tools/people.py` | Modify | `get_person` fat return, `check_team_engagement` |
| `src/tools/projects.py` | Modify | Fat return for `get_project`, enum fix, `workspace_ids` |
| `src/tools/reminder.py` | Modify | `task_keyword` param |
| `src/tools/note.py` | Modify | Lark sync on write |
| `src/tools/summary.py` | Modify | `get_workload` cross-workspace, `get_project_report` |
| `src/tools/workspace.py` | Modify | `manage_join` → Lark People sync |
| `src/onboarding.py` | Modify | Replace in-memory dict with DB-persisted state |
| `src/group_onboarding.py` | Modify | Replace in-memory dict with DB-persisted state |
| `src/scheduler.py` | Modify | `_after_deadline_check`, extend `_sync_lark_to_sqlite`, group context fix |

---

## Phase 1: Foundation

### Task 1: DB Schema Migrations

**Files:**
- Modify: `src/db.py`

- [ ] **Step 1: Add new tables and columns to `_migrate_schema`**

In `src/db.py`, add to `_migrate_schema` after the existing migrations:

```python
    # outbound_messages — log all bot-initiated DMs
    await db.execute("""
        CREATE TABLE IF NOT EXISTS outbound_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            boss_chat_id  INTEGER NOT NULL,
            workspace_id  TEXT,
            to_chat_id    INTEGER NOT NULL,
            to_name       TEXT,
            content       TEXT NOT NULL,
            trigger_type  TEXT DEFAULT 'manual',
            task_id       TEXT,
            project       TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_outbound_boss_to
            ON outbound_messages (boss_chat_id, to_chat_id, created_at DESC)
    """)

    # onboarding_state — replaces in-memory _onboarding dict
    await db.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_state (
            chat_id    INTEGER PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # notified_overdue columns on task_notifications
    for col, definition in [
        ("notified_overdue",    "INTEGER DEFAULT 0"),
        ("notified_overdue_at", "TIMESTAMP"),
    ]:
        try:
            await db.execute(f"ALTER TABLE task_notifications ADD COLUMN {col} {definition}")
            await db.commit()
        except Exception as exc:
            if "duplicate column name" not in str(exc):
                raise

    # active_workspace_id on memberships (which replaced people_map)
    try:
        await db.execute("ALTER TABLE memberships ADD COLUMN active_workspace_id TEXT DEFAULT NULL")
        await db.commit()
    except Exception as exc:
        if "duplicate column name" not in str(exc):
            raise
```

- [ ] **Step 2: Add DB helper functions for outbound_messages and onboarding_state**

Still in `src/db.py`, add these functions:

```python
# ---------------------------------------------------------------------------
# outbound_messages
# ---------------------------------------------------------------------------

async def log_outbound_dm(
    boss_chat_id: int,
    to_chat_id: int,
    to_name: str,
    content: str,
    trigger_type: str = "manual",
    task_id: str = "",
    project: str = "",
    workspace_id: str = "",
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO outbound_messages
           (boss_chat_id, workspace_id, to_chat_id, to_name, content, trigger_type, task_id, project)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (boss_chat_id, workspace_id, to_chat_id, to_name, content, trigger_type, task_id or "", project or ""),
    )
    await db.commit()


async def get_outbound_log(
    boss_chat_id: int,
    to_chat_id: int | None = None,
    trigger_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = await get_db()
    conditions = ["boss_chat_id = ?"]
    params: list = [boss_chat_id]
    if to_chat_id:
        conditions.append("to_chat_id = ?")
        params.append(to_chat_id)
    if trigger_type:
        conditions.append("trigger_type = ?")
        params.append(trigger_type)
    where = " AND ".join(conditions)
    async with db.execute(
        f"SELECT * FROM outbound_messages WHERE {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# onboarding_state
# ---------------------------------------------------------------------------

async def get_onboarding_state(chat_id: int) -> dict:
    import json as _json
    db = await get_db()
    async with db.execute(
        "SELECT state_json FROM onboarding_state WHERE chat_id = ?", (chat_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return {}
    try:
        return _json.loads(row["state_json"])
    except Exception:
        return {}


async def save_onboarding_state(chat_id: int, state: dict) -> None:
    import json as _json
    db = await get_db()
    await db.execute(
        """INSERT INTO onboarding_state (chat_id, state_json, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(chat_id) DO UPDATE SET state_json=excluded.state_json, updated_at=CURRENT_TIMESTAMP""",
        (chat_id, _json.dumps(state, ensure_ascii=False)),
    )
    await db.commit()


async def clear_onboarding_state(chat_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM onboarding_state WHERE chat_id = ?", (chat_id,))
    await db.commit()
```

- [ ] **Step 3: Add helper for notified_overdue**

In `src/db.py`, add:

```python
async def get_unnotified_overdue_tasks(db_conn, boss_chat_id: str) -> list[dict]:
    async with db_conn.execute(
        """SELECT * FROM task_notifications
           WHERE boss_chat_id = ? AND notified_overdue = 0""",
        (boss_chat_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def mark_overdue_notified(db_conn, task_record_id: str, boss_chat_id: str) -> None:
    await db_conn.execute(
        """UPDATE task_notifications
           SET notified_overdue = 1, notified_overdue_at = CURRENT_TIMESTAMP
           WHERE task_record_id = ? AND boss_chat_id = ?""",
        (task_record_id, boss_chat_id),
    )
    await db_conn.commit()
```

- [ ] **Step 4: Smoke test — start the bot and check DB initializes cleanly**

```bash
cd "/Users/dat_macbook/Documents/2025/ý tưởng mới/Dự án hỗ trợ thứ ký giám đốc ảo"
python -c "import asyncio; from src.db import get_db; asyncio.run(get_db())"
```

Expected: No errors. If `data/history.db` exists, migration runs silently.

- [ ] **Step 5: Commit**

```bash
git add src/db.py
git commit -m "feat: db migrations — outbound_messages, onboarding_state, notified_overdue, active_workspace_id"
```

---

### Task 2: Error Handling Wrapper in `execute_tool`

**Files:**
- Modify: `src/tools/__init__.py`

- [ ] **Step 1: Wrap the `execute_tool` dispatch in try/except**

Find the `execute_tool` function in `src/tools/__init__.py`. Replace the function body so all exceptions are caught and returned as error strings instead of raising:

```python
async def execute_tool(name: str, arguments: str | dict, ctx: ChatContext) -> str:
    try:
        args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        return await _dispatch_tool(name, args_dict, ctx)
    except Exception as e:
        err_type = type(e).__name__
        msg = str(e)
        # Classify common error types for agent guidance
        if any(kw in msg.lower() for kw in ("lark", "base_token", "table", "record")):
            return f"[TOOL_ERROR:lark] {name} — Lark không phản hồi hoặc cấu hình sai: {msg}. Thử lại hoặc báo người dùng."
        if any(kw in msg.lower() for kw in ("not found", "không tìm thấy", "no such")):
            return f"[TOOL_ERROR:not_found] {name} — {msg}. Hãy hỏi lại người dùng tên chính xác."
        return f"[TOOL_ERROR:unknown] {name} thất bại ({err_type}): {msg}"
```

The existing dispatch logic moves to a private `_dispatch_tool(name, args_dict, ctx)` function with the same if/elif chain.

- [ ] **Step 2: Add `[TOOL_ERROR]` guidance to the agent system prompt**

In `src/agent.py`, find `SECRETARY_PROMPT` and add to the **Permissions** section at the bottom:

```python
SECRETARY_PROMPT = """...existing content...

## Tool errors
If a tool returns [TOOL_ERROR:lark] — Lark is unreachable. Retry once. If it fails again, tell the user clearly: "Hệ thống Lark đang có vấn đề, vui lòng thử lại sau."
If a tool returns [TOOL_ERROR:not_found] — Ask the user to clarify (different name? different workspace?).
If a tool returns [TOOL_ERROR:unknown] — Surface the error message directly to the user. Do not claim the action succeeded.
Never ignore a [TOOL_ERROR] response.
"""
```

- [ ] **Step 3: Smoke test**

Send a message that triggers a tool call and confirm the bot still responds normally (error handling wrapper is transparent when tools succeed).

- [ ] **Step 4: Commit**

```bash
git add src/tools/__init__.py src/agent.py
git commit -m "feat: execute_tool error wrapper — returns [TOOL_ERROR] strings instead of raising"
```

---

### Task 3: `workspace_ids` + `active_workspace_id` in `_workspace.py`

**Files:**
- Modify: `src/tools/_workspace.py`

- [ ] **Step 1: Add `active_workspace_id` resolution**

In `src/tools/_workspace.py`, update `resolve_workspaces` to support `active_workspace_id`:

```python
async def resolve_workspaces(ctx: ChatContext, workspace_ids: str | list) -> list[dict]:
    """
    Returns list of workspace credential dicts.
    workspace_ids:
        "current"  — only active workspace (respects active_workspace_id if set)
        "all"      — all workspaces user belongs to
        "primary"  — boss's own workspace regardless of active setting
        [id, ...]  — specific boss_ids
    """
    if workspace_ids == "primary":
        return [_ctx_to_workspace(ctx)]

    if workspace_ids == "current":
        # Check if user has an active_workspace_id set (from switch_workspace)
        active_ws_id = await _get_active_workspace_id(ctx.sender_chat_id)
        if active_ws_id and active_ws_id != str(ctx.boss_chat_id):
            boss = await db.get_boss(int(active_ws_id))
            if boss:
                return [_boss_to_workspace(boss, ctx.sender_type)]
        return [_ctx_to_workspace(ctx)]

    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    boss_self = await db.get_boss(ctx.sender_chat_id)
    if boss_self and not any(m["boss_chat_id"] == str(ctx.sender_chat_id) for m in memberships):
        memberships = [{"boss_chat_id": str(ctx.sender_chat_id), "person_type": "boss", "status": "active"}] + list(memberships)

    active_memberships = [m for m in memberships if m.get("status") == "active"]

    if workspace_ids != "all":
        target_ids = [str(i) for i in (workspace_ids if isinstance(workspace_ids, list) else [workspace_ids])]
        active_memberships = [m for m in active_memberships if m["boss_chat_id"] in target_ids]

    result = []
    for m in active_memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            result.append(_boss_to_workspace(boss, m.get("person_type", "member")))
    return result


async def _get_active_workspace_id(sender_chat_id: int) -> str | None:
    _db = await db.get_db()
    async with _db.execute(
        "SELECT active_workspace_id FROM memberships WHERE chat_id = ? AND active_workspace_id IS NOT NULL LIMIT 1",
        (str(sender_chat_id),),
    ) as cur:
        row = await cur.fetchone()
    return row["active_workspace_id"] if row else None


async def set_active_workspace_id(sender_chat_id: int, boss_chat_id: str) -> None:
    _db = await db.get_db()
    await _db.execute(
        "UPDATE memberships SET active_workspace_id = ? WHERE chat_id = ?",
        (boss_chat_id, str(sender_chat_id)),
    )
    await _db.commit()


def _boss_to_workspace(boss: dict, user_role: str) -> dict:
    return {
        "boss_id": int(boss["chat_id"]),
        "workspace_name": boss.get("company", str(boss["chat_id"])),
        "user_role": user_role,
        "lark_base_token": boss["lark_base_token"],
        "lark_table_people": boss.get("lark_table_people", ""),
        "lark_table_tasks": boss.get("lark_table_tasks", ""),
        "lark_table_projects": boss.get("lark_table_projects", ""),
        "lark_table_ideas": boss.get("lark_table_ideas", ""),
        "lark_table_reminders": boss.get("lark_table_reminders", ""),
        "lark_table_notes": boss.get("lark_table_notes", ""),
    }
```

- [ ] **Step 2: Update `switch_workspace` tool to call `set_active_workspace_id`**

In `src/tools/workspace.py`, find `switch_workspace` and update it:

```python
async def switch_workspace(ctx: ChatContext, workspace: str) -> str:
    from src.tools._workspace import set_active_workspace_id, resolve_workspaces
    all_ws = await resolve_workspaces(ctx, "all")
    match = next((w for w in all_ws if workspace.lower() in w["workspace_name"].lower()), None)
    if not match:
        names = ", ".join(w["workspace_name"] for w in all_ws)
        return f"Không tìm thấy workspace '{workspace}'. Có: {names}"
    await set_active_workspace_id(ctx.sender_chat_id, str(match["boss_id"]))
    return f"Đã chuyển sang workspace: {match['workspace_name']}"
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/_workspace.py src/tools/workspace.py
git commit -m "feat: active_workspace_id resolution in _workspace.py + switch_workspace persists to DB"
```

---

## Phase 2: New Domains

### Task 4: Communication Domain

**Files:**
- Create: `src/tools/communication.py`

- [ ] **Step 1: Create `src/tools/communication.py`**

```python
"""
Communication tools — send DM, broadcast, get communication log.
All outbound DMs are logged to outbound_messages table.
"""
import logging
from datetime import datetime

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.communication")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _find_person_chat_id(ctx, name: str, workspace_ids: str = "current") -> tuple[int | None, str, str]:
    """
    Returns (chat_id, resolved_name, workspace_name).
    Applies disambiguation: group context → prefer group's workspace first.
    Returns (None, name, "") if person not found or has no Chat ID.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    candidates = []
    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue
        for r in records:
            full_name = r.get("Tên", "")
            nickname = r.get("Tên gọi", "")
            if name.lower() in full_name.lower() or (nickname and name.lower() in nickname.lower()):
                raw_id = r.get("Chat ID")
                candidates.append({
                    "chat_id": int(raw_id) if raw_id else None,
                    "name": full_name,
                    "workspace_name": ws["workspace_name"],
                    "workspace_boss_id": ws["boss_id"],
                    "type": r.get("Type", ""),
                })

    if not candidates:
        return None, name, ""

    # Disambiguation: if in group, prefer workspace matching group's boss
    if ctx.is_group and len(candidates) > 1:
        preferred = [c for c in candidates if c["workspace_boss_id"] == ctx.boss_chat_id]
        if preferred:
            candidates = preferred

    best = candidates[0]
    return best["chat_id"], best["name"], best["workspace_name"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def send_dm(
    ctx: ChatContext,
    to: str,
    content: str,
    context: str = "",
    workspace_ids: str = "current",
) -> str:
    """
    Send a private DM to a team member by name.
    Logs the message to outbound_messages.
    Use this when boss wants to message someone privately — even from a group context.
    Disambiguation: if in a group, searches that group's workspace first.
    """
    chat_id, resolved_name, workspace_name = await _find_person_chat_id(ctx, to, workspace_ids)

    if chat_id is None and resolved_name == to:
        return f"[TOOL_ERROR:not_found] Không tìm thấy '{to}' trong danh sách nhân sự."

    if chat_id is None:
        return (
            f"{resolved_name} có trong danh sách nhưng chưa có tài khoản liên kết — "
            f"không thể nhắn tin trực tiếp."
        )

    message_text = f"Tin nhắn từ {ctx.boss_name}:\n\n{content}"
    await telegram.send(chat_id, message_text)

    await db.log_outbound_dm(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=chat_id,
        to_name=resolved_name,
        content=content,
        trigger_type="manual",
        workspace_id=workspace_name,
    )

    return f"Đã nhắn tin riêng cho {resolved_name}" + (f" [{workspace_name}]" if workspace_name else "") + "."


async def broadcast(
    ctx: ChatContext,
    message: str,
    targets: str = "all_members",
    workspace_ids: str = "current",
) -> str:
    """
    Send a message to multiple people individually via DM.
    targets: "all_members" | "all_partners" | "all" | comma-separated names
    Works from both group and DM context.
    Use check_team_engagement first to know who has Chat IDs.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)

    type_filter = None
    specific_names: list[str] = []
    if targets in ("all_members", "all_partners", "all"):
        if targets == "all_members":
            type_filter = "Nhân viên"
        elif targets == "all_partners":
            type_filter = "Cộng tác viên"
        # "all" → no filter
    else:
        specific_names = [n.strip() for n in targets.split(",")]

    sent, failed = [], []
    seen_chat_ids: set[int] = set()

    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue

        for r in records:
            name = r.get("Tên", "")
            ptype = r.get("Type", "")

            # Filter
            if specific_names and not any(n.lower() in name.lower() for n in specific_names):
                continue
            if type_filter and ptype != type_filter:
                continue

            raw_id = r.get("Chat ID")
            if not raw_id:
                failed.append(f"{name} (không có Chat ID)")
                continue

            chat_id = int(raw_id)
            if chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(chat_id)

            try:
                await telegram.send(chat_id, f"Thông báo từ {ctx.boss_name}:\n\n{message}")
                await db.log_outbound_dm(
                    boss_chat_id=ctx.boss_chat_id,
                    to_chat_id=chat_id,
                    to_name=name,
                    content=message,
                    trigger_type="manual",
                    workspace_id=ws["workspace_name"],
                )
                sent.append(name)
            except Exception as e:
                failed.append(f"{name} (lỗi: {e})")

    parts = [f"Đã gửi cho {len(sent)} người: {', '.join(sent)}."]
    if failed:
        parts.append(f"Không gửi được cho: {', '.join(failed)}.")
    return " ".join(parts)


async def get_communication_log(
    ctx: ChatContext,
    person: str = "",
    since: str = "",
    log_type: str = "all",
    workspace_ids: str = "current",
) -> str:
    """
    Returns full timeline of all bot-initiated contact with a person or the whole team.
    log_type: "all" | "manual" | "task_assigned" | "deadline_push" | "reminder"
    Call this before asking "đã nhắn X chưa" or "đã push deadline chưa".
    Tracks from redesign deployment — no historical backfill.
    """
    # Resolve to_chat_id if person specified
    to_chat_id = None
    resolved_name = person
    if person:
        chat_id, resolved_name, _ = await _find_person_chat_id(ctx, person, workspace_ids)
        to_chat_id = chat_id

    rows = await db.get_outbound_log(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=to_chat_id,
        trigger_type=log_type if log_type != "all" else None,
        limit=30,
    )

    if not rows:
        subject = f"với {resolved_name}" if person else "với bất kỳ ai"
        return f"Chưa có lịch sử nhắn tin {subject}."

    lines = [f"Lịch sử tin nhắn{' với ' + resolved_name if person else ''} ({len(rows)} mục):"]
    for r in rows:
        dt = r.get("created_at", "")[:16]
        trigger = r.get("trigger_type", "")
        to = r.get("to_name", "")
        content_preview = r.get("content", "")[:80]
        lines.append(f"  [{dt}] → {to} ({trigger}): {content_preview}")
    return "\n".join(lines)
```

- [ ] **Step 2: Register in `src/tools/__init__.py`**

Add `from src.tools import communication` to the imports at the top of `__init__.py`, then add the three tool dispatches in `_dispatch_tool`:

```python
    elif name == "send_dm":
        return await communication.send_dm(ctx, **args_dict)
    elif name == "broadcast":
        return await communication.broadcast(ctx, **args_dict)
    elif name == "get_communication_log":
        return await communication.get_communication_log(ctx, **args_dict)
```

- [ ] **Step 3: Add tool definitions to `TOOL_DEFINITIONS` in `__init__.py`**

```python
    {
        "type": "function",
        "function": {
            "name": "send_dm",
            "description": (
                "Gửi tin nhắn riêng (DM) cho một người trong team theo tên. "
                "Dùng khi sếp muốn nhắn riêng ai đó — kể cả khi đang ở group. "
                "Tự động log vào lịch sử liên lạc. "
                "Nếu đang ở group, ưu tiên tìm người thuộc workspace của group đó trước."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Tên người nhận"},
                    "content": {"type": "string", "description": "Nội dung tin nhắn"},
                    "context": {"type": "string", "description": "Ngữ cảnh tùy chọn (vd: tên task liên quan)"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) hoặc \"all\""},
                },
                "required": ["to", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast",
            "description": (
                "Gửi thông báo hàng loạt cho nhiều người qua DM cá nhân. "
                "targets: \"all_members\" | \"all_partners\" | \"all\" | tên cụ thể cách nhau dấu phẩy. "
                "Hoạt động từ cả DM lẫn group. Dùng check_team_engagement trước để biết ai có Chat ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "targets": {"type": "string", "description": "\"all_members\" | \"all_partners\" | \"all\" | \"Tên A, Tên B\""},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_communication_log",
            "description": (
                "Tra lịch sử tất cả tin nhắn bot đã chủ động gửi cho ai đó. "
                "Gọi trước khi trả lời 'đã nhắn X chưa' hoặc 'đã push deadline chưa'. "
                "Trả về timeline đầy đủ: DM thủ công, thông báo giao task, nhắc deadline, reminder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person": {"type": "string", "description": "Tên người cần tra (bỏ trống = xem tất cả)"},
                    "since": {"type": "string", "description": "Từ ngày YYYY-MM-DD (tùy chọn)"},
                    "log_type": {"type": "string", "description": "\"all\" | \"manual\" | \"task_assigned\" | \"deadline_push\" | \"reminder\""},
                    "workspace_ids": {"type": "string"},
                },
                "required": [],
            },
        },
    },
```

- [ ] **Step 4: Update `create_task` in `tasks.py` to log outbound DM**

In `src/tools/tasks.py`, in `_notify_assignee_task`, add logging after `telegram.send`:

```python
async def _notify_assignee_task(
    assignee_chat_id: str, task_name: str, deadline: str,
    assigner_name: str, boss_chat_id: int,
):
    msg = (
        f"📋 Bạn vừa được giao task mới!\n\n"
        f"Task: {task_name}\n"
        f"Deadline: {deadline or 'Chưa xác định'}\n"
        f"Giao bởi: {assigner_name}\n\n"
        f"Reply để xác nhận, hỏi thêm thông tin, hoặc đề xuất thay đổi nhé."
    )
    await telegram.send(int(assignee_chat_id), msg)
    await db.log_outbound_dm(
        boss_chat_id=boss_chat_id,
        to_chat_id=int(assignee_chat_id),
        to_name="",
        content=msg,
        trigger_type="task_assigned",
        task_id="",
    )
```

Update all call sites of `_notify_assignee_task` to pass `boss_chat_id=ctx.boss_chat_id`.

- [ ] **Step 5: Commit**

```bash
git add src/tools/communication.py src/tools/__init__.py src/tools/tasks.py
git commit -m "feat: communication domain — send_dm, broadcast, get_communication_log with outbound logging"
```

---

### Task 5: `search_notes` Tool

**Files:**
- Create: `src/tools/search.py`

- [ ] **Step 1: Create `src/tools/search.py`**

```python
"""
Search tools — semantic search for notes/ideas and message history.
"""
from src.context import ChatContext
from src.services import qdrant, openai_client
from src import db


async def search_notes(
    ctx: ChatContext,
    query: str,
    note_type: str = "all",
    workspace_ids: str = "current",
) -> str:
    """
    Semantic search across notes and ideas.
    note_type: "personal" | "group" | "project" | "idea" | "all"
    Notes and ideas are embedded on write — Qdrant collection: notes_{boss_chat_id}
    """
    collection = f"notes_{ctx.boss_chat_id}"
    await qdrant.ensure_collection(collection)

    vector = await openai_client.embed(query)
    results = await qdrant.search(collection, query, chat_id=None, top_n=8)

    if not results:
        return f"Không tìm thấy ghi chú nào liên quan đến '{query}'."

    lines = [f"Kết quả tìm kiếm ghi chú cho '{query}' ({len(results)} kết quả):"]
    for r in results:
        snippet = r.get("content", "")[:120]
        ref = r.get("ref", "")
        ntype = r.get("type", "")
        label = f"[{ntype}]" + (f" {ref}" if ref else "")
        lines.append(f"  {label}: {snippet}...")
    return "\n".join(lines)


async def search_history(
    ctx: ChatContext,
    query: str,
    scope: str = "current_chat",
    workspace_ids: str = "current",
) -> str:
    """
    Semantic search in message history.
    scope: "current_chat" (default) | "all" (searches all chats belonging to this workspace)
    """
    collection = ctx.messages_collection
    await qdrant.ensure_collection(collection)

    chat_id_filter = ctx.chat_id if scope == "current_chat" else None
    results = await qdrant.search(collection, query, chat_id=chat_id_filter, top_n=10)

    if not results:
        return f"Không tìm thấy lịch sử liên quan đến '{query}'."

    lines = [f"Lịch sử liên quan đến '{query}' ({len(results)} kết quả):"]
    for r in results:
        role = r.get("role", "")
        content = r.get("content", "")[:120]
        lines.append(f"  [{role}]: {content}")
    return "\n".join(lines)
```

- [ ] **Step 2: Update `note.py` and `ideas.py` to embed notes/ideas on write**

In `src/tools/note.py`, in the `update_note` function, add embedding after writing:

```python
    # Embed to Qdrant for search
    import asyncio
    from src.services import qdrant, openai_client
    collection = f"notes_{ctx.boss_chat_id}"
    await qdrant.ensure_collection(collection)
    vector = await openai_client.embed(new_content)
    asyncio.create_task(qdrant.upsert(
        collection=collection,
        point_id=abs(hash(f"note_{ctx.boss_chat_id}_{note_type}_{ref_id}")),
        chat_id=ctx.boss_chat_id,
        role="note",
        text=new_content,
        vector=vector,
        extra={"type": note_type, "ref": ref_id},
    ))
```

Do the same in `src/tools/ideas.py` `create_idea` function:

```python
    import asyncio
    from src.services import qdrant, openai_client
    collection = f"notes_{ctx.boss_chat_id}"
    await qdrant.ensure_collection(collection)
    vector = await openai_client.embed(content)
    asyncio.create_task(qdrant.upsert(
        collection=collection,
        point_id=abs(hash(f"idea_{ctx.boss_chat_id}_{record_id}")),
        chat_id=ctx.boss_chat_id,
        role="idea",
        text=content,
        vector=vector,
        extra={"type": "idea", "ref": category or ""},
    ))
```

- [ ] **Step 3: Register `search_notes` and update `search_history` dispatch in `__init__.py`**

```python
from src.tools import search as search_tools

# In _dispatch_tool:
    elif name == "search_notes":
        return await search_tools.search_notes(ctx, **args_dict)
    elif name == "search_history":
        return await search_tools.search_history(ctx, **args_dict)
```

Add tool definition for `search_notes`:

```python
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "Tìm kiếm ngữ nghĩa trong ghi chú và ý tưởng. "
                "Dùng khi cần tìm lại thông tin đã lưu trong notes hoặc ideas. "
                "note_type: \"personal\" | \"group\" | \"project\" | \"idea\" | \"all\""
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "note_type": {"type": "string", "description": "\"all\" mặc định"},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
```

- [ ] **Step 4: Commit**

```bash
git add src/tools/search.py src/tools/note.py src/tools/ideas.py src/tools/__init__.py
git commit -m "feat: search_notes tool + embed notes/ideas to Qdrant on write"
```

---

## Phase 3: Tool Enhancements

### Task 6: Tasks — Multiple Assignees, Fat Returns, Reassign Notification

**Files:**
- Modify: `src/tools/tasks.py`

- [ ] **Step 1: Add enum validation helper**

At the top of `src/tools/tasks.py`:

```python
# Canonical enum values — must match Lark field options exactly
TASK_STATUS_VALUES = ("Mới", "Đang làm", "Hoàn thành", "Huỷ")
TASK_PRIORITY_VALUES = ("Cao", "Trung bình", "Thấp")


def _validate_status(status: str) -> str:
    """Normalize and validate status. Raises ValueError if invalid."""
    for v in TASK_STATUS_VALUES:
        if status.lower() == v.lower():
            return v
    raise ValueError(
        f"Status '{status}' không hợp lệ. Chỉ dùng: {', '.join(TASK_STATUS_VALUES)}"
    )


def _validate_priority(priority: str) -> str:
    for v in TASK_PRIORITY_VALUES:
        if priority.lower() == v.lower():
            return v
    raise ValueError(
        f"Priority '{priority}' không hợp lệ. Chỉ dùng: {', '.join(TASK_PRIORITY_VALUES)}"
    )
```

- [ ] **Step 2: Update `create_task` to accept multiple assignees and validate enums**

Replace the `create_task` signature and beginning:

```python
async def create_task(
    ctx: ChatContext,
    name: str,
    assignees: str | list = "",   # comma-sep string OR list
    deadline: str = "",
    priority: str = "Trung bình",
    project: str = "",
    start_time: str = "",
    location: str = "",
    original_message: str = "",
    note: str = "",
) -> str:
    # Normalize assignees to list
    if isinstance(assignees, str):
        assignee_list = [a.strip() for a in assignees.split(",") if a.strip()]
    else:
        assignee_list = list(assignees)

    # Backward compat: single 'assignee' string → list of one
    assignee_display = ", ".join(assignee_list) if assignee_list else ""

    # Validate enums
    if priority:
        priority = _validate_priority(priority)

    fields: dict = {
        "Tên task": name,
        "Priority": priority,
        "Status": "Mới",
        "Giao bởi": ctx.sender_name or ctx.boss_name,
        "Assignee": assignee_display,
    }
    # ... rest of field building same as before ...
    if note:
        fields["Ghi chú"] = note
```

- [ ] **Step 3: Send DM to each assignee and log outbound**

Replace the notify block in `create_task`:

```python
    notification_statuses = []
    for assignee_name in assignee_list:
        assignee_chat_id, found = await _find_assignee_chat_id(ctx, assignee_name)
        if not found:
            notification_statuses.append(f"⚠️ '{assignee_name}' không có trong danh sách nhân sự")
        elif not assignee_chat_id:
            notification_statuses.append(f"⚠️ '{assignee_name}' chưa có tài khoản liên kết")
        else:
            asyncio.create_task(_notify_assignee_task(
                assignee_chat_id, name, deadline,
                ctx.sender_name or ctx.boss_name, ctx.boss_chat_id,
            ))
            notification_statuses.append(f"✓ Đã thông báo {assignee_name}")

    notify_summary = "\n".join(notification_statuses) if notification_statuses else ""
    result = f"Đã tạo task '{name}' (ID: {record_id})."
    if notify_summary:
        result += f"\n{notify_summary}"
    return result
```

- [ ] **Step 4: Update `update_task` — validate enums + notify new assignee**

In `update_task`, validate status and priority before applying, and send DM when assignee changes:

```python
    # Validate enum fields before applying
    if "status" in kwargs and kwargs["status"]:
        fields["Status"] = _validate_status(kwargs["status"])
    if "priority" in kwargs and kwargs["priority"]:
        fields["Priority"] = _validate_priority(kwargs["priority"])

    # ... after applying update to Lark ...

    # Notify new assignee if assignee changed
    new_assignee = fields.get("Assignee") or fields.get("assignee")
    if new_assignee:
        assignee_chat_id, found = await _find_assignee_chat_id(ctx, new_assignee)
        if found and assignee_chat_id:
            msg = (
                f"📋 Task '{task_name}' vừa được giao lại cho bạn.\n"
                f"Giao bởi: {ctx.sender_name or ctx.boss_name}\n"
                f"Vui lòng xác nhận nhé."
            )
            asyncio.create_task(telegram.send(int(assignee_chat_id), msg))
            asyncio.create_task(db.log_outbound_dm(
                boss_chat_id=ctx.boss_chat_id,
                to_chat_id=int(assignee_chat_id),
                to_name=new_assignee,
                content=msg,
                trigger_type="task_assigned",
            ))
```

- [ ] **Step 5: Update `list_tasks` to return fat data with urgency flags**

Replace the `_format_task` helper:

```python
def _format_task(r: dict, workspace_label: str = "") -> str:
    from datetime import date, datetime
    deadline = r.get("Deadline")
    dl_str = "N/A"
    urgency = ""
    if isinstance(deadline, (int, float)):
        dl_date = datetime.fromtimestamp(deadline / 1000).date()
        dl_str = str(dl_date)
        today = date.today()
        days_left = (dl_date - today).days
        if days_left < 0:
            urgency = " 🔴QUÁHẠN"
        elif days_left == 0:
            urgency = " 🟠HÔM NAY"
        elif days_left <= 2:
            urgency = f" 🟡{days_left}ngày"

    ws = f"[{workspace_label}] " if workspace_label else ""
    return (
        f"{ws}- {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} "
        f"| {r.get('Status', '?')} | DL: {dl_str}{urgency} | {r.get('Priority', '')}"
    )
```

- [ ] **Step 6: Commit**

```bash
git add src/tools/tasks.py
git commit -m "feat: tasks — multiple assignees, enum validation, reassign DM, fat returns with urgency flags"
```

---

### Task 7: People — Fat `get_person` + `check_team_engagement`

**Files:**
- Modify: `src/tools/people.py`

- [ ] **Step 1: Rewrite `get_people` → `get_person` with fat return**

Replace `get_people` with:

```python
async def get_person(
    ctx: ChatContext,
    name: str,
    workspace_ids: str = "current",
) -> str:
    """
    Fat return: person info + active tasks + effort_score + last DM from bot + has_dmd_bot.
    Call before assigning a task: effort_score > 0.8 means near overloaded.
    If multiple people share the same name across workspaces, returns all with workspace tag.
    """
    from src.tools._workspace import resolve_workspaces
    from src import db as _db

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_matches = []

    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue
        for r in records:
            full = r.get("Tên", "")
            nick = r.get("Tên gọi", "")
            if name.lower() in full.lower() or (nick and name.lower() in nick.lower()):
                all_matches.append((r, ws))

    if not all_matches:
        return f"Không tìm thấy ai tên '{name}'."

    lines = []
    for r, ws in all_matches:
        ws_label = f" [{ws['workspace_name']}]" if workspace_ids != "current" else ""
        person_name = r.get("Tên", "")
        lines.append(f"=== {person_name}{ws_label} ===")
        lines.append(_fmt_person(r))

        # Active tasks
        try:
            tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            active = [
                t for t in tasks
                if person_name.lower() in str(t.get("Assignee", "")).lower()
                and t.get("Status") not in ("Hoàn thành", "Huỷ", "Done", "Cancelled")
            ]
            effort_score = min(len(active) / 5.0, 1.0)  # 5+ tasks = fully loaded
            lines.append(f"Tasks đang mở: {len(active)} | effort_score: {effort_score:.1f}")
            for t in active[:5]:
                lines.append(f"  - {t.get('Tên task', '?')} | {t.get('Status')} | DL: {t.get('Deadline', 'N/A')}")
        except Exception:
            lines.append("Tasks: (không tải được)")

        # Last DM from bot
        raw_id = r.get("Chat ID")
        if raw_id:
            chat_id = int(raw_id)
            outbound = await _db.get_outbound_log(ctx.boss_chat_id, to_chat_id=chat_id, limit=1)
            if outbound:
                last = outbound[0]
                lines.append(f"Lần cuối bot nhắn: {last['created_at'][:16]} — {last['content'][:60]}")
                lines.append("has_dmd_bot: true")
            else:
                lines.append("Lần cuối bot nhắn: (chưa từng)")
                lines.append("has_dmd_bot: true (có Chat ID)")
        else:
            lines.append("has_dmd_bot: false (chưa có Chat ID)")

    return "\n".join(lines)
```

- [ ] **Step 2: Add `check_team_engagement`**

```python
async def check_team_engagement(
    ctx: ChatContext,
    workspace_ids: str = "current",
) -> str:
    """
    Returns engagement status for every team member:
    has_dmd_bot, last_interaction, active task count, overload_flag.
    Use when asked 'ai chưa nhắn bot', 'ai đang bận', or before broadcast.
    """
    from src.tools._workspace import resolve_workspaces
    from src import db as _db

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    lines = ["=== Team Engagement ==="]

    for ws in workspaces:
        ws_label = f"[{ws['workspace_name']}] " if workspace_ids != "current" else ""
        if not ws.get("lark_table_people") or not ws.get("lark_table_tasks"):
            continue
        try:
            people = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
            tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
        except Exception:
            continue

        for p in people:
            name = p.get("Tên", "?")
            raw_id = p.get("Chat ID")
            active_tasks = [
                t for t in tasks
                if name.lower() in str(t.get("Assignee", "")).lower()
                and t.get("Status") not in ("Hoàn thành", "Huỷ", "Done", "Cancelled")
            ]
            task_count = len(active_tasks)
            overload = "⚠️ OVERLOAD" if task_count >= 5 else ""

            if raw_id:
                chat_id = int(raw_id)
                outbound = await _db.get_outbound_log(ctx.boss_chat_id, to_chat_id=chat_id, limit=1)
                if outbound:
                    last_dt = outbound[0]["created_at"][:16]
                    dmd = f"✓ last: {last_dt}"
                else:
                    dmd = "✓ có Chat ID, chưa nhắn"
            else:
                dmd = "✗ chưa có Chat ID"

            lines.append(f"  {ws_label}{name} | {dmd} | tasks: {task_count} {overload}")

    return "\n".join(lines)
```

- [ ] **Step 3: Update `__init__.py` dispatches**

Replace `get_people` dispatch with `get_person`, add `check_team_engagement`:

```python
    elif name == "get_person":
        return await people.get_person(ctx, **args_dict)
    elif name == "check_team_engagement":
        return await people.check_team_engagement(ctx, **args_dict)
```

- [ ] **Step 4: Commit**

```bash
git add src/tools/people.py src/tools/__init__.py
git commit -m "feat: people — get_person fat return, check_team_engagement"
```

---

### Task 8: Projects — Fat Return + Enum Fix

**Files:**
- Modify: `src/tools/projects.py`

- [ ] **Step 1: Fix enum values and add `get_project_report`**

At top of `src/tools/projects.py`, add:

```python
PROJECT_STATUS_VALUES = ("Chưa bắt đầu", "Đang thực hiện", "Hoàn thành", "Tạm dừng", "Huỷ")

def _validate_project_status(status: str) -> str:
    for v in PROJECT_STATUS_VALUES:
        if status.lower() == v.lower():
            return v
    raise ValueError(f"Status '{status}' không hợp lệ. Dùng: {', '.join(PROJECT_STATUS_VALUES)}")
```

Fix `create_project` default status from `"Planning"` → `"Chưa bắt đầu"`:

```python
    fields: dict = {
        "Tên dự án": name,
        "Trạng thái": "Chưa bắt đầu",
    }
```

In `update_project`, validate status:

```python
    if status:
        updates["Trạng thái"] = _validate_project_status(status)
```

- [ ] **Step 2: Enhance `get_project` fat return with progress %**

```python
async def get_project(ctx: ChatContext, search_name: str, workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    lines = []

    for ws in workspaces:
        if not ws.get("lark_table_projects"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_projects"])
        except Exception:
            continue
        matches = [r for r in records if search_name.lower() in str(r.get("Tên dự án", "")).lower()]
        for proj in matches:
            ws_label = f" [{ws['workspace_name']}]" if workspace_ids != "current" else ""
            lines.append(f"=== {proj.get('Tên dự án', '?')}{ws_label} ===")
            lines.append(_fmt_project(proj))

            # Tasks
            try:
                all_tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
                proj_name = proj.get("Tên dự án", "")
                related = [t for t in all_tasks if proj_name.lower() in str(t.get("Project", "")).lower()]
                total = len(related)
                done = sum(1 for t in related if t.get("Status") in ("Hoàn thành", "Done"))
                progress = f"{done}/{total} ({int(done/total*100)}%)" if total else "0/0"
                lines.append(f"Tiến độ: {progress} task hoàn thành")
                for t in related:
                    lines.append(f"  - {t.get('Tên task','?')} | {t.get('Assignee','?')} | {t.get('Status','?')}")
            except Exception:
                lines.append("Tasks: (không tải được)")

    if not lines:
        return f"Không tìm thấy dự án '{search_name}'."
    return "\n".join(lines)
```

- [ ] **Step 3: Add `workspace_ids` to `list_projects`, `update_project`, `delete_project`**

For each: add `workspace_ids: str = "current"` param, wrap Lark calls with `resolve_workspaces`, tag results with workspace name.

- [ ] **Step 4: Commit**

```bash
git add src/tools/projects.py src/tools/__init__.py
git commit -m "feat: projects — enum fix (Chưa bắt đầu), fat get_project with progress %, workspace_ids"
```

---

### Task 9: Reminders — `task_keyword` param

**Files:**
- Modify: `src/tools/reminder.py`

- [ ] **Step 1: Add `task_keyword` and `project` to `create_reminder`**

In `src/tools/reminder.py`, update `create_reminder`:

```python
async def create_reminder(
    ctx: ChatContext,
    content: str,
    remind_at: str,
    target: str = "",
    project: str = "",
    task_keyword: str = "",
    workspace_ids: str = "current",
) -> str:
    # ... existing target resolution ...

    # Store task_keyword and project in content field as structured prefix for scheduler
    stored_content = content
    if task_keyword:
        stored_content = f"[task:{task_keyword}] {content}"
    if project:
        stored_content = f"[project:{project}] {stored_content}"
    # ... rest of creation using stored_content ...
```

In `src/agent.py` `send_reminder`, when reminder content has `[task:...]` prefix, fetch task status and include in message:

```python
    # Parse task_keyword from content
    task_status_note = ""
    if content.startswith("[task:"):
        end = content.index("]")
        task_kw = content[6:end]
        content = content[end+2:]
        if ctx:
            try:
                from src.services import lark as _lark
                tasks = await _lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
                matched = [t for t in tasks if task_kw.lower() in t.get("Tên task", "").lower()]
                if matched:
                    t = matched[0]
                    task_status_note = f"\n(Task '{t.get('Tên task')}' hiện: {t.get('Status','?')})"
            except Exception:
                pass
```

- [ ] **Step 2: Update tool definition in `__init__.py`**

Add `task_keyword` and `project` params to `create_reminder` definition:

```python
                    "task_keyword": {"type": "string", "description": "Từ khoá task liên quan — scheduler sẽ fetch status task khi nhắc"},
                    "project": {"type": "string", "description": "Tên dự án liên quan"},
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/reminder.py src/agent.py src/tools/__init__.py
git commit -m "feat: reminders — task_keyword param, fetch live task status when reminder fires"
```

---

### Task 10: Summary — Cross-workspace Workload + `get_project_report`

**Files:**
- Modify: `src/tools/summary.py`

- [ ] **Step 1: Add `get_project_report` function**

In `src/tools/summary.py`:

```python
async def get_project_report(
    ctx: ChatContext,
    project: str,
    workspace_ids: str = "current",
) -> str:
    """
    LLM-generated comprehensive project status report.
    Covers: progress %, tasks by status, who's blocking, upcoming deadlines.
    """
    from src.tools._workspace import resolve_workspaces
    from src.services import openai_client as _oai

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    tasks_text = ""

    for ws in workspaces:
        try:
            all_tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            related = [t for t in all_tasks if project.lower() in str(t.get("Project", "")).lower()]
            if related:
                for t in related:
                    tasks_text += (
                        f"- {t.get('Tên task','?')} | {t.get('Assignee','?')} "
                        f"| {t.get('Status','?')} | DL: {t.get('Deadline','N/A')}\n"
                    )
        except Exception:
            continue

    if not tasks_text:
        return f"Không tìm thấy task nào cho dự án '{project}'."

    response, _ = await _oai.chat_with_tools(
        [
            {"role": "system", "content": (
                f"Tạo báo cáo tổng quan dự án '{project}' theo:\n"
                "1. Tiến độ tổng thể (% hoàn thành)\n"
                "2. Tasks theo trạng thái\n"
                "3. Ai đang chặn tiến độ (task quá hạn hoặc chưa bắt đầu)\n"
                "4. Deadline quan trọng sắp tới\n"
                "Ngắn gọn, dạng bullet."
            )},
            {"role": "user", "content": f"Danh sách tasks:\n{tasks_text}"},
        ],
        [],
    )
    return response.content or "Không thể tạo báo cáo."
```

- [ ] **Step 2: Update `get_workload` to aggregate cross-workspace**

The existing `check_effort` in `people.py` already supports `workspace_ids`. Rename `get_workload` in summary.py to wrap it and add aggregate effort_score:

```python
async def get_workload(
    ctx: ChatContext,
    person: str = "",
    workspace_ids: str = "all",
) -> str:
    """
    Effort overview. workspace_ids defaults to "all" for accurate total load.
    Returns combined task count across all workspaces.
    """
    from src.tools.people import check_effort
    return await check_effort(ctx, assignee=person or ctx.boss_name, workspace_ids=workspace_ids)
```

- [ ] **Step 3: Register in `__init__.py`**

```python
    elif name == "get_project_report":
        return await summary.get_project_report(ctx, **args_dict)
    elif name == "get_workload":
        return await summary.get_workload(ctx, **args_dict)
```

- [ ] **Step 4: Commit**

```bash
git add src/tools/summary.py src/tools/__init__.py
git commit -m "feat: summary — get_project_report LLM narrative, get_workload cross-workspace aggregate"
```

---

### Task 11: `manage_join` — Lark People Sync on Approve

**Files:**
- Modify: `src/tools/workspace.py`

- [ ] **Step 1: Update `approve_join` to add person to Lark People table**

In `src/tools/workspace.py`, find the approve logic and add Lark People insert:

```python
async def approve_join(ctx: ChatContext, requester_chat_id: int) -> str:
    # ... existing approval DB logic ...

    # Add to target workspace's Lark People table
    requester_info = await db.get_membership(str(requester_chat_id), str(ctx.boss_chat_id))
    if requester_info:
        try:
            fields = {
                "Tên": requester_info.get("name", str(requester_chat_id)),
                "Type": "Cộng tác viên",   # default for join requests
                "Chat ID": requester_chat_id,
            }
            await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)
        except Exception as e:
            logger.warning("Could not add person to Lark People on join approval: %s", e)

    # ... rest of existing approval logic (notify requester, etc.) ...
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/workspace.py
git commit -m "fix: approve_join now inserts person into Lark People table of target workspace"
```

---

## Phase 4: Onboarding Redesign

### Task 12: Personal Onboarding — Remove In-Memory State Machine

**Files:**
- Modify: `src/onboarding.py`

- [ ] **Step 1: Replace in-memory `_onboarding` dict with DB-persisted state**

The current `_onboarding: dict[int, dict]` at the top of `onboarding.py` is the state machine. Replace the public API (`is_onboarding`, `start_onboarding`, `handle_onboard_message`) to use `db.get_onboarding_state` and `db.save_onboarding_state`.

Replace `is_onboarding` and `start_onboarding`:

```python
async def is_onboarding(chat_id: int) -> bool:
    state = await db.get_onboarding_state(chat_id)
    return bool(state) and state.get("onboarding_status") != "complete"


async def start_onboarding(chat_id: int) -> None:
    state = {
        "onboarding_status": "incomplete",
        "collected": {
            "name": None,
            "company": None,
            "language": None,
            "lark_base_token": None,
            "lark_tables": {
                "people": None, "tasks": None, "projects": None,
                "ideas": None, "reminders": None, "notes": None,
            },
        },
    }
    state["missing"] = [k for k, v in state["collected"].items() if v is None]
    await db.save_onboarding_state(chat_id, state)
```

- [ ] **Step 2: Rewrite `handle_onboard_message` to be LLM-driven**

```python
async def handle_onboard_message(text: str, chat_id: int) -> None:
    state = await db.get_onboarding_state(chat_id)
    if not state:
        await start_onboarding(chat_id)
        state = await db.get_onboarding_state(chat_id)

    collected = state.get("collected", {})
    missing = [k for k, v in collected.items() if v is None]

    if not missing:
        # All collected — provision and complete
        await _complete_onboarding(chat_id, collected)
        return

    # Build context for LLM
    collected_str = "\n".join(f"  - {k}: {v}" for k, v in collected.items() if v is not None)
    missing_str = ", ".join(missing)

    system_prompt = f"""{_PERSONA}

Bạn đang thực hiện onboarding cho người dùng mới.
Đã thu thập được: {collected_str or '(chưa có gì)'}
Còn thiếu: {missing_str}

Nhiệm vụ:
1. Từ tin nhắn của người dùng, trích xuất bất kỳ thông tin nào thuộc danh sách còn thiếu.
2. Cập nhật danh sách đã thu thập.
3. Hỏi tự nhiên về MỘT thông tin còn thiếu tiếp theo — ưu tiên: name → company → language → lark_base_token → lark_tables.

Trả về JSON:
{{
  "extracted": {{"field": "value", ...}},
  "reply": "câu hỏi tiếp theo hoặc xác nhận"
}}"""

    result = await _ai_classify(system_prompt, text)
    extracted = result.get("extracted", {})
    reply = result.get("reply", "")

    # Update state
    for field, value in extracted.items():
        if field in collected and value:
            if field == "lark_tables" and isinstance(value, dict):
                collected["lark_tables"].update(value)
            else:
                collected[field] = value

    state["collected"] = collected
    state["missing"] = [k for k, v in collected.items() if v is None]
    await db.save_onboarding_state(chat_id, state)

    if reply:
        await telegram.send(chat_id, reply)
```

- [ ] **Step 3: Update `agent.py` to call async `is_onboarding`**

In `src/agent.py`, `handle_message`, the onboarding check becomes:

```python
            from src import onboarding
            if not await onboarding.is_onboarding(chat_id):
                await onboarding.start_onboarding(chat_id)
            await onboarding.handle_onboard_message(text, chat_id)
```

- [ ] **Step 4: Commit**

```bash
git add src/onboarding.py src/agent.py
git commit -m "feat: onboarding — replace in-memory state machine with DB-persisted agent-driven flow"
```

---

### Task 13: Group Onboarding — Remove In-Memory State Machine

**Files:**
- Modify: `src/group_onboarding.py`

- [ ] **Step 1: Replace in-memory dict with DB state**

Apply the same pattern as Task 12 to `src/group_onboarding.py`. The group onboarding state tracks:

```python
GROUP_ONBOARDING_TEMPLATE = {
    "onboarding_status": "incomplete",
    "collected": {
        "workspace_boss_id": None,   # which boss owns this group
        "project_id": None,           # optional linked project
        "group_name": None,
    },
}
```

Use `db.save_onboarding_state(group_chat_id, state)` — same table, keyed by group_chat_id.

- [ ] **Step 2: Rewrite `handle` to be LLM-driven (same pattern as personal onboarding)**

The LLM extracts workspace info from the message and asks one question at a time.

- [ ] **Step 3: Commit**

```bash
git add src/group_onboarding.py
git commit -m "feat: group onboarding — DB-persisted state, agent-driven flow"
```

---

## Phase 5: Scheduler Enhancements

### Task 14: `_after_deadline_check` + Extend Sync-Back + Group Context Fix

**Files:**
- Modify: `src/scheduler.py`

- [ ] **Step 1: Add `_after_deadline_check` job**

In `src/scheduler.py`, add after `_check_deadline_push`:

```python
async def _after_deadline_check():
    """Every 30min: DM assignees of overdue tasks, report to boss."""
    from datetime import datetime, timezone
    from src import agent as _agent

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    bosses = await db.get_all_bosses()

    for boss in bosses:
        try:
            tasks = await lark.search_records(boss["lark_base_token"], boss["lark_table_tasks"])
            open_status = ("Mới", "Đang làm")
            overdue = [
                t for t in tasks
                if t.get("Status") in open_status
                and isinstance(t.get("Deadline"), (int, float))
                and t["Deadline"] < now_ms
            ]
            if not overdue:
                continue

            unnotified = await db.get_unnotified_overdue_tasks(db._db, str(boss["chat_id"]))
            unnotified_ids = {n["task_record_id"] for n in unnotified}

            report_lines = []
            for task in overdue:
                record_id = task["record_id"]
                if record_id not in unnotified_ids:
                    continue

                assignee_name = task.get("Assignee", "")
                # Find assignee Chat ID
                people = await lark.search_records(boss["lark_base_token"], boss["lark_table_people"])
                person = next(
                    (p for p in people if assignee_name.lower() in p.get("Tên", "").lower()),
                    None,
                )
                assignee_chat_id = int(person["Chat ID"]) if (person and person.get("Chat ID")) else None

                task_name = task.get("Tên task", "?")
                if assignee_chat_id:
                    msg = (
                        f"Task '{task_name}' đã quá hạn rồi!\n"
                        f"Bạn có thể update tiến độ cho {boss['name']} biết không?"
                    )
                    await telegram.send(assignee_chat_id, msg)
                    await db.log_outbound_dm(
                        boss_chat_id=boss["chat_id"],
                        to_chat_id=assignee_chat_id,
                        to_name=assignee_name,
                        content=msg,
                        trigger_type="deadline_push",
                        task_id=record_id,
                    )
                    report_lines.append(f"✓ Đã nhắc {assignee_name}: '{task_name}'")
                else:
                    report_lines.append(f"⚠️ '{task_name}' — {assignee_name} chưa có Chat ID")

                await db.mark_overdue_notified(db._db, record_id, str(boss["chat_id"]))

            if report_lines:
                await telegram.send(
                    boss["chat_id"],
                    "📊 Báo cáo task quá hạn:\n" + "\n".join(report_lines),
                )
        except Exception:
            logger.exception("[scheduler] _after_deadline_check failed for %s", boss.get("name"))
```

- [ ] **Step 2: Extend `_sync_lark_to_sqlite` to Tasks, Projects, People**

Extend the existing `_sync_lark_to_sqlite` to sync Tasks and Projects back from Lark:

```python
async def _sync_lark_to_sqlite():
    """Every 30s: Lark → SQLite sync for Reminders. Every 5 min: Tasks, Projects, People."""
    from datetime import datetime

    bosses = await db.get_all_bosses()
    now = datetime.utcnow()
    do_full_sync = (now.minute % 5 == 0 and now.second < 35)  # ~every 5 min

    for boss in bosses:
        try:
            # Reminders sync (existing, always runs)
            tbl = boss.get("lark_table_reminders", "")
            if tbl:
                records = await lark.search_records(boss["lark_base_token"], tbl)
                for rec in records:
                    sqlite_id = rec.get("SQLite ID")
                    if not isinstance(sqlite_id, (int, float)):
                        continue
                    await db.sync_reminder_from_lark(
                        db._db, int(sqlite_id),
                        content=rec.get("Nội dung", ""),
                        status=rec.get("Trạng thái", "pending"),
                    )

            if not do_full_sync:
                continue

            # Task status sync — update SQLite task_notifications if status changed in Lark
            task_tbl = boss.get("lark_table_tasks", "")
            if task_tbl:
                tasks = await lark.search_records(boss["lark_base_token"], task_tbl)
                for t in tasks:
                    record_id = t.get("record_id")
                    status = t.get("Status", "")
                    # If task is done, mark notification as complete to stop future pushes
                    if status in ("Hoàn thành", "Huỷ", "Done", "Cancelled") and record_id:
                        await db._db.execute(
                            """UPDATE task_notifications SET notified_overdue=1
                               WHERE task_record_id=? AND boss_chat_id=?""",
                            (record_id, str(boss["chat_id"])),
                        )
                await db._db.commit()

        except Exception:
            logger.exception("[scheduler] sync failed for %s", boss.get("name"))
```

- [ ] **Step 3: Fix group context in `_run_dynamic_reviews`**

In `_run_dynamic_reviews`, when `target_chat_id != int(owner_id)` (sending to a group), inject group context:

```python
            # Route: group chat or boss DM
            target_chat_id = review.get("group_chat_id") or int(owner_id)
            
            # Build group context if sending to a group
            group_context_str = ""
            if review.get("group_chat_id"):
                try:
                    from src.context_builder import build_group_context as _bgc
                    grp = await _bgc(int(review["group_chat_id"]), int(owner_id))
                    if grp:
                        group_context_str = (
                            f"\nNhóm: {grp.get('group_name', '')} | "
                            f"Đang bàn: {grp.get('active_topic', '')} | "
                            f"Ghi chú: {grp.get('group_note', '')}"
                        )
                except Exception:
                    pass
            
            # Inject group context into text if present
            if group_context_str and text:
                text = group_context_str + "\n\n" + text

            await telegram.send(int(target_chat_id), text)
```

- [ ] **Step 4: Register `_after_deadline_check` in `start()`**

```python
    _scheduler.add_job(_after_deadline_check, IntervalTrigger(minutes=30))
```

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py
git commit -m "feat: scheduler — _after_deadline_check, extended Lark sync-back, group context in reviews"
```

---

## Phase 6: Final Tool Definitions Audit

### Task 15: Audit and Update All Tool Definitions in `__init__.py`

**Files:**
- Modify: `src/tools/__init__.py`

- [ ] **Step 1: Audit every tool definition against the spec**

For each of the 36 tools, verify:
1. Description includes at least one behavior hint (when to call, what to check first)
2. `workspace_ids` param present on all people/task/project/reminder/note tools
3. Enum values explicitly listed in `description` or `enum` field for status/priority/type params
4. No misleading descriptions that could cause agent to confuse group vs DM context

Tools that need description updates (key hints to add):

| Tool | Description hint to add |
|------|--------------------------|
| `create_task` | "Gọi get_person trước để check effort_score. Nếu > 0.8, hỏi sếp xác nhận." |
| `list_tasks` | "Khi gọi từ group, mặc định trả task của project gắn với group đó." |
| `get_person` | "Trả về fat return gồm tasks + effort_score + lịch sử DM. Nếu nhiều người cùng tên, trả tất cả có workspace tag." |
| `send_dm` | "Nhắn riêng ngay cả khi đang ở group. Ưu tiên Bách của workspace group hiện tại." |
| `get_communication_log` | "Gọi trước khi trả lời 'đã nhắn X chưa'." |
| `check_team_engagement` | "Gọi khi hỏi 'ai chưa nhắn bot', 'ai đang bận', trước broadcast." |
| `update_task` | "Status phải là một trong: Mới, Đang làm, Hoàn thành, Huỷ." |
| `create_project` | "Status phải là một trong: Chưa bắt đầu, Đang thực hiện, Hoàn thành, Tạm dừng, Huỷ." |
| `get_workload` | "Mặc định workspace_ids='all' để thấy tổng workload thật." |

- [ ] **Step 2: Remove deprecated tool definitions**

Remove from `TOOL_DEFINITIONS`:
- `broadcast_to_group` (replaced by `broadcast`)
- `update_group_note` (replaced by `update_note(type="group")`)
- `summarize_group_conversation` (replaced by `get_summary(scope="group")`)
- `confirm_reset_step1` (replaced by single `reset_workspace`)

Remove from `_dispatch_tool` as well.

- [ ] **Step 3: Smoke test the full tool set**

```bash
python -c "
from src.tools import TOOL_DEFINITIONS
names = [t['function']['name'] for t in TOOL_DEFINITIONS]
print(f'Total tools: {len(names)}')
print('\n'.join(sorted(names)))
"
```

Expected output: 36 tool names, no duplicates.

- [ ] **Step 4: Commit**

```bash
git add src/tools/__init__.py
git commit -m "chore: audit tool definitions — descriptions, workspace_ids, enum hints, remove deprecated tools"
```

---

## Self-Review Checklist

- [ ] All 36 tools have `workspace_ids` param where relevant
- [ ] Enum values for status/priority/type are stated literally in descriptions
- [ ] `outbound_messages` is written on every bot-initiated DM (4 logging points)
- [ ] `get_communication_log` queries outbound_messages correctly
- [ ] `_after_deadline_check` uses `notified_overdue` to prevent duplicate notifications
- [ ] `manage_join` approve → Lark People insert
- [ ] Onboarding state is persisted to DB (not in-memory)
- [ ] Group reviews use `build_group_context` before generating brief
- [ ] Deprecated tools removed from both definitions and dispatch

---

## Notes

- User preference: test in production directly — skip heavy unit test suites. Each task's smoke test is sufficient.
- Lark Base is freshly provisioned — enum values in this plan are authoritative.
- `outbound_messages` has no historical data before deployment — document this to users on upgrade.
- `search_notes` requires `notes_{boss_chat_id}` Qdrant collection — created lazily on first write.
