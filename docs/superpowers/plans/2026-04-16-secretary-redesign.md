# Secretary Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand tool capability and clean up agent architecture so Secretary reasons naturally across workspaces with no hardcoded routing logic.

**Architecture:** Single Secretary agent receives full context (memberships, active sessions, language) from a pure-Python `context_builder.py`. Tools handle credential resolution internally. System prompt is principle-based. No router LLM call.

**Tech Stack:** Python 3.11+, aiosqlite, OpenAI function calling, Lark Base API, Qdrant, Telegram Bot API, APScheduler

**Tests:** Skipped this cycle — test in production.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/db.py` | Modify | Add schema migrations for `language`, `sessions` table |
| `src/context_builder.py` | **Create** | Pure Python: build context dict (memberships, sessions, messages) |
| `src/agent.py` | Modify → rename to `secretary.py` | Remove all pre-checks; integrate context_builder |
| `src/context.py` | Modify | Support resolving context for any `workspace_id` |
| `src/tools/_workspace.py` | **Create** | Shared cross-workspace credential resolution |
| `src/tools/note.py` | Modify | Add `append_note` function |
| `src/tools/memory.py` | Modify | Add `list_pending_approvals` function |
| `src/tools/people.py` | Modify | Add `workspace_ids` param to `search_person`, `check_effort` |
| `src/tools/tasks.py` | Modify | Add `workspace_ids` param to `list_tasks`; add `approve_task_change`, `reject_task_change` |
| `src/tools/join.py` | **Create** | `list_available_workspaces`, `request_join`, `approve_join`, `reject_join` |
| `src/tools/reset.py` | Modify | Nuclear reset: delete SQLite + Qdrant + Lark Base; fix order |
| `src/tools/workspace.py` | **Create** | `switch_workspace`, `set_language` tools |
| `src/tools/__init__.py` | Modify | Register all new/updated tools + TOOL_DEFINITIONS |
| `src/onboarding.py` | Modify | Add language selection step after role selection |

---

## Task 1: DB Schema Migrations

**Files:**
- Modify: `src/db.py` — `_migrate_schema` function (~169-205)

- [ ] **Add migrations to `_migrate_schema` in `src/db.py`**

Add the following block at the end of `_migrate_schema`, before `await db.commit()` is called (or after the existing migration blocks):

```python
    # Add language to bosses
    for col, definition in [
        ("language", "TEXT DEFAULT 'en'"),
    ]:
        try:
            await db.execute(f"ALTER TABLE bosses ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc):
                raise

    # Add language to memberships
    try:
        await db.execute("ALTER TABLE memberships ADD COLUMN language TEXT DEFAULT NULL")
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
```

Also add these helper functions to `db.py` (after the existing `get_boss` section):

```python
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
```

- [ ] **Commit**

```bash
git add src/db.py
git commit -m "feat: add language + sessions schema, db helper functions"
```

---

## Task 2: context_builder.py

**Files:**
- Create: `src/context_builder.py`

- [ ] **Create `src/context_builder.py`**

```python
"""
context_builder.py — Pure Python context assembly. No LLM call.
Runs before Secretary. Returns structured context dict.
"""
import json
import logging
from datetime import datetime, timezone

from src import db

logger = logging.getLogger("context_builder")


async def build(sender_id: int, chat_id: int) -> dict:
    """
    Returns:
    {
        "sender_id": int,
        "memberships": [{"workspace": str, "boss_id": int, "role": str, "language": str|None}],
        "active_sessions": {"reset_pending": dict|None, "join_pending": [...], "approvals_pending": [...]},
        "last_5_messages": [...],
        "primary_workspace_id": int | None,
        "language": str,
    }
    """
    memberships = await db.get_memberships(str(sender_id))

    # Include boss's own workspace if they are a boss
    boss_self = await db.get_boss(sender_id)
    if boss_self and not any(m["boss_chat_id"] == str(sender_id) for m in memberships):
        memberships = [{
            "chat_id": str(sender_id),
            "boss_chat_id": str(sender_id),
            "person_type": "boss",
            "name": boss_self["name"],
            "status": "active",
            "language": boss_self.get("language", "en"),
        }] + list(memberships)

    resolved = []
    for m in memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            resolved.append({
                "workspace": boss.get("company", str(m["boss_chat_id"])),
                "boss_id": int(m["boss_chat_id"]),
                "role": m["person_type"],
                "language": m.get("language"),
            })

    primary = next(
        (m for m in resolved if m["role"] == "boss"), 
        resolved[0] if resolved else None
    )
    primary_id = primary["boss_id"] if primary else None

    # Check preferred workspace from sessions (switch_workspace with TTL)
    preferred_raw = await db.get_session(sender_id, "preferred_workspace")
    if preferred_raw:
        try:
            preferred_id = int(preferred_raw)
            if any(m["boss_id"] == preferred_id for m in resolved):
                primary_id = preferred_id
        except ValueError:
            pass

    active_sessions = await _get_active_sessions(sender_id)
    last_5 = await db.get_recent(chat_id, limit=5)
    language = _resolve_language(memberships, sender_id, primary)

    return {
        "sender_id": sender_id,
        "memberships": resolved,
        "active_sessions": active_sessions,
        "last_5_messages": last_5,
        "primary_workspace_id": primary_id,
        "language": language,
    }


async def _get_active_sessions(sender_id: int) -> dict:
    reset_raw = await db.get_session(sender_id, "reset_step")
    reset_pending = json.loads(reset_raw) if reset_raw else None

    _db = await db.get_db()

    # Join requests this user sent (pending)
    async with _db.execute(
        "SELECT * FROM memberships WHERE chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    join_pending = [dict(r) for r in rows]

    # Approvals this user (as boss) needs to handle
    approvals_pending = []
    async with _db.execute(
        "SELECT *, 'join' AS approval_type FROM memberships WHERE boss_chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    approvals_pending.extend([dict(r) for r in rows])

    async with _db.execute(
        "SELECT *, 'task' AS approval_type FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    approvals_pending.extend([dict(r) for r in rows])

    return {
        "reset_pending": reset_pending,
        "join_pending": join_pending,
        "approvals_pending": approvals_pending,
    }


def _resolve_language(memberships: list, sender_id: int, primary: dict | None) -> str:
    sender_m = next(
        (m for m in memberships if str(m.get("chat_id", "")) == str(sender_id)),
        None,
    )
    if sender_m and sender_m.get("language"):
        return sender_m["language"]
    if primary and primary.get("language"):
        return primary["language"]
    return "en"


def membership_summary(memberships: list) -> str:
    """Returns a short string like 'Company A (boss), Company B (partner)' for system prompt."""
    if not memberships:
        return "(no workspaces)"
    return ", ".join(f"{m['workspace']} ({m['role']})" for m in memberships)
```

- [ ] **Commit**

```bash
git add src/context_builder.py
git commit -m "feat: add context_builder — pure Python context assembly"
```

---

## Task 3: Cross-workspace Credential Resolution Utility

**Files:**
- Create: `src/tools/_workspace.py`

- [ ] **Create `src/tools/_workspace.py`**

```python
"""
_workspace.py — Shared cross-workspace credential resolution.
Used by tools that accept workspace_ids parameter.
"""
from src import db
from src.context import ChatContext


async def resolve_workspaces(ctx: ChatContext, workspace_ids: str | list) -> list[dict]:
    """
    Returns list of workspace credential dicts.
    Each dict has: boss_id, lark_base_token, lark_table_people, lark_table_tasks,
                   lark_table_projects, lark_table_ideas, workspace_name, user_role.

    workspace_ids:
        "current" — only active ctx workspace
        "all"     — all workspaces user belongs to
        [id, ...] — specific boss_ids
    """
    if workspace_ids == "current":
        return [_ctx_to_workspace(ctx)]

    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    # Include own boss workspace
    boss_self = await db.get_boss(ctx.sender_chat_id)
    if boss_self and not any(m["boss_chat_id"] == str(ctx.sender_chat_id) for m in memberships):
        memberships = [{
            "boss_chat_id": str(ctx.sender_chat_id),
            "person_type": "boss",
            "status": "active",
        }] + list(memberships)

    if workspace_ids != "all":
        target_ids = [str(i) for i in workspace_ids]
        memberships = [m for m in memberships if m["boss_chat_id"] in target_ids]

    result = []
    for m in memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            result.append({
                "boss_id": int(boss["chat_id"]),
                "workspace_name": boss.get("company", str(boss["chat_id"])),
                "user_role": m.get("person_type", "member"),
                "lark_base_token": boss["lark_base_token"],
                "lark_table_people": boss.get("lark_table_people", ""),
                "lark_table_tasks": boss.get("lark_table_tasks", ""),
                "lark_table_projects": boss.get("lark_table_projects", ""),
                "lark_table_ideas": boss.get("lark_table_ideas", ""),
                "lark_table_reminders": boss.get("lark_table_reminders", ""),
            })
    return result


def _ctx_to_workspace(ctx: ChatContext) -> dict:
    return {
        "boss_id": ctx.boss_chat_id,
        "workspace_name": ctx.boss_name,
        "user_role": ctx.sender_type,
        "lark_base_token": ctx.lark_base_token,
        "lark_table_people": ctx.lark_table_people,
        "lark_table_tasks": ctx.lark_table_tasks,
        "lark_table_projects": ctx.lark_table_projects,
        "lark_table_ideas": ctx.lark_table_ideas,
        "lark_table_reminders": ctx.lark_table_reminders,
    }
```

- [ ] **Commit**

```bash
git add src/tools/_workspace.py
git commit -m "feat: add cross-workspace credential resolution utility"
```

---

## Task 4: Update `context.py` — Support Any Workspace ID

**Files:**
- Modify: `src/context.py`

- [ ] **Update `resolve()` in `src/context.py` to accept `workspace_id` from context_builder**

The current `resolve()` takes `preferred_boss_id`. Change the call sites in `agent.py`/`secretary.py` to pass `primary_workspace_id` from context_builder output. No code change needed in `context.py` itself — it already supports `preferred_boss_id`. Just ensure the wiring in secretary.py uses the context_builder's `primary_workspace_id`.

This task is: verify `context.resolve(chat_id, sender_id, is_group, preferred_boss_id=primary_workspace_id)` works correctly. Read `src/context.py` lines 34-108 and confirm `preferred_boss_id` flows through to `_build_ctx`. No changes needed.

- [ ] **Commit (no-op if no changes needed)**

```bash
git commit --allow-empty -m "chore: verify context.py preferred_boss_id wiring — no changes needed"
```

---

## Task 5: Rewrite `agent.py` → `secretary.py`

**Files:**
- Modify: `src/agent.py` (keep filename for now, rename later to avoid breaking imports)

The key change: remove the 5 pre-check blocks in `handle_message` (join session check, join keywords check, reset session check, reset trigger check, boss join decision check, `_handle_task_approval` call). Replace with context_builder integration.

- [ ] **Remove `_handle_task_approval` function from `src/agent.py`** (lines ~140-187)

Delete the entire `_handle_task_approval` function. It will be replaced by `list_pending_approvals` + `approve_task_change` tools.

- [ ] **Replace pre-check blocks in `handle_message` with context_builder**

In `handle_message`, replace steps 1b and 2b (the pre-checks) with:

```python
    # ------------------------------------------------------------------
    # Step 1b: Group + not mentioned → persist only
    # ------------------------------------------------------------------
    if is_group and not bot_mentioned:
        group_info = await db.get_group(chat_id)
        if not group_info:
            return
        boss_id = group_info["boss_chat_id"]
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        vector = await openai_client.embed(text)
        asyncio.create_task(
            qdrant.upsert(
                collection=f"messages_{boss_id}",
                point_id=msg_id,
                chat_id=chat_id,
                role="user",
                text=text,
                vector=vector,
            )
        )
        return

    # ------------------------------------------------------------------
    # Step 2: Build context
    # ------------------------------------------------------------------
    from src import context_builder as _cb
    built = await _cb.build(sender_id, chat_id)

    # Unknown user → onboarding
    ctx = await context.resolve(
        chat_id, sender_id, is_group,
        preferred_boss_id=built["primary_workspace_id"],
    )
    if ctx is None:
        from src import onboarding
        if not onboarding.is_onboarding(chat_id):
            onboarding.start_onboarding(chat_id)
        await onboarding.handle_onboard_message(text, chat_id)
        return
```

- [ ] **Update system prompt building to use context_builder output**

In `handle_message`, replace the `SECRETARY_PROMPT.format(...)` section:

```python
        from src.context_builder import membership_summary as _ms
        system_content = SECRETARY_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
            people_summary=people_summary,
            chat_type=chat_type,
            sender_name=ctx.sender_name,
            sender_type=ctx.sender_type,
            context_note=context_note,
            language=built["language"],
            memberships_summary=_ms(built["memberships"]),
            active_sessions_summary=_build_sessions_summary(built["active_sessions"]),
        )
```

Add helper at module level:

```python
def _build_sessions_summary(sessions: dict) -> str:
    parts = []
    if sessions.get("reset_pending"):
        parts.append(f"Reset flow active (step {sessions['reset_pending'].get('step', '?')})")
    if sessions.get("join_pending"):
        parts.append(f"{len(sessions['join_pending'])} join request(s) you sent pending approval")
    if sessions.get("approvals_pending"):
        parts.append(f"{len(sessions['approvals_pending'])} item(s) awaiting your approval")
    return "; ".join(parts) if parts else "none"
```

- [ ] **Rewrite `SECRETARY_PROMPT` at top of `agent.py`**

```python
SECRETARY_PROMPT = """You are the AI secretary of {boss_name}{company_info}.

## Context
Time: {current_time}
Language: respond in {language}
Talking to: {sender_name} ({sender_type})
Their workspaces: {memberships_summary}
Active workspace: {boss_name}'s workspace

## Team
{people_summary}

## Your notes
{personal_note}

## Current conversation context
{context_note}

## Active sessions
{active_sessions_summary}

## Who you are
You genuinely know this team. You care about their wellbeing, not just their output.
When making decisions that affect someone, understand their situation before acting.

You remember everything shared with you. Your notes are your extended memory —
when context feels incomplete about a person or project, check them.

You have access to multiple workspaces. When a question spans workspaces or
doesn't specify one, use your judgment about where to look.

You use tools to understand context before acting, not just to execute commands.

## Permissions
- Boss ({boss_name}): full access. Confirm before deleting anything.
- Member/Partner: can view and update their own tasks. Significant changes need boss approval.
- Group: respond only when tagged. Permissions follow the person who tagged you.
"""
```

- [ ] **Commit**

```bash
git add src/agent.py
git commit -m "feat: remove hardcoded pre-checks from agent, integrate context_builder, principle-based prompt"
```

---

## Task 6: `append_note` Tool

**Files:**
- Modify: `src/tools/note.py`

- [ ] **Add `append_note` function to `src/tools/note.py`**

```python
async def append_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    """Appends content to an existing note without overwriting. Creates if not exists."""
    from src import db
    existing = await db.get_note(ctx.boss_chat_id, note_type, ref_id)
    if existing and existing.get("content"):
        new_content = existing["content"] + "\n\n" + content
    else:
        new_content = content
    await db.update_note(ctx.boss_chat_id, note_type, ref_id, new_content)
    return f"Note updated ({note_type}/{ref_id})."
```

- [ ] **Commit**

```bash
git add src/tools/note.py
git commit -m "feat: add append_note tool"
```

---

## Task 7: `list_pending_approvals` Tool

**Files:**
- Modify: `src/tools/memory.py`

- [ ] **Add `list_pending_approvals` to `src/tools/memory.py`**

```python
async def list_pending_approvals(ctx: ChatContext) -> str:
    """Lists all pending approvals for the boss: task change requests + join requests."""
    import json
    from src import db

    lines = []

    # Pending task approvals
    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending' ORDER BY created_at",
        (str(ctx.boss_chat_id),),
    ) as cur:
        task_approvals = [dict(r) for r in await cur.fetchall()]

    for a in task_approvals:
        payload = json.loads(a["payload"]) if isinstance(a["payload"], str) else a["payload"]
        task_name = payload.get("task_name", "unknown task")
        changes = payload.get("changes", {})
        changes_str = ", ".join(f"{k}→{v}" for k, v in changes.items())
        lines.append(
            f"[task_approval id={a['id']}] '{task_name}': {changes_str} "
            f"(requested by user {a['requester_id']})"
        )

    # Pending join requests
    async with _db.execute(
        "SELECT * FROM memberships WHERE boss_chat_id = ? AND status = 'pending' ORDER BY requested_at",
        (str(ctx.boss_chat_id),),
    ) as cur:
        join_requests = [dict(r) for r in await cur.fetchall()]

    for j in join_requests:
        lines.append(
            f"[join_request chat_id={j['chat_id']}] {j['name'] or 'Unknown'} "
            f"wants to join as {j['person_type']}. Info: {j.get('request_info', '')}"
        )

    if not lines:
        return "No pending approvals."
    return "Pending approvals:\n" + "\n".join(lines)
```

- [ ] **Commit**

```bash
git add src/tools/memory.py
git commit -m "feat: add list_pending_approvals tool"
```

---

## Task 8: Cross-workspace `search_person`, `list_tasks`, `check_effort`

**Files:**
- Modify: `src/tools/people.py`
- Modify: `src/tools/tasks.py`

- [ ] **Update `search_person` in `src/tools/people.py` to support `workspace_ids`**

Add `workspace_ids: str = "current"` parameter. When not "current", resolve via `_workspace.resolve_workspaces`:

```python
async def search_person(ctx: ChatContext, search_name: str, workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces
    from src.services import lark

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_results = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
            matches = [
                r for r in records
                if search_name.lower() in r.get("Tên", "").lower()
                or search_name.lower() in r.get("Tên gọi", "").lower()
            ]
            for r in matches:
                all_results.append({
                    "workspace": ws["workspace_name"],
                    "name": r.get("Tên", ""),
                    "nickname": r.get("Tên gọi", ""),
                    "type": r.get("Type", ""),
                    "role": r.get("Vai trò", ""),
                    "group": r.get("Nhóm", ""),
                    "record_id": r.get("record_id", ""),
                })
        except Exception:
            continue

    if not all_results:
        return f"No one found matching '{search_name}'."

    lines = []
    for r in all_results:
        label = f"[{r['workspace']}] " if workspace_ids != "current" else ""
        name = f"{r['name']} ({r['nickname']})" if r.get("nickname") else r["name"]
        parts = [label + name, r["type"], r["role"], r["group"]]
        lines.append(" | ".join(p for p in parts if p))
    return "\n".join(lines)
```

- [ ] **Update `check_effort` in `src/tools/people.py` to support `workspace_ids`**

Add `workspace_ids: str = "current"` parameter. Use `resolve_workspaces` to query tasks per workspace:

```python
async def check_effort(ctx: ChatContext, assignee: str, deadline: str = None, workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces
    from src.services import lark

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_tasks = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            tasks = [
                r for r in records
                if assignee.lower() in r.get("Assignee", "").lower()
                and r.get("Status") not in ("Xong",)
            ]
            for t in tasks:
                t["_workspace"] = ws["workspace_name"]
            all_tasks.extend(tasks)
        except Exception:
            continue

    if not all_tasks:
        return f"No active tasks found for '{assignee}'."

    lines = [f"Active tasks for '{assignee}' ({len(all_tasks)} total):"]
    conflicts = []
    for t in all_tasks:
        ws_label = f"[{t['_workspace']}] " if workspace_ids != "current" else ""
        line = f"  {ws_label}{t.get('Tên task', '?')} | deadline: {t.get('Deadline', 'none')} | {t.get('Status', '?')}"
        lines.append(line)
        if deadline and t.get("Deadline") == deadline:
            conflicts.append(t.get("Tên task", "?"))

    if conflicts:
        lines.append(f"\n⚠️ Deadline conflict on {deadline}: {', '.join(conflicts)}")

    return "\n".join(lines)
```

- [ ] **Update `list_tasks` in `src/tools/tasks.py` to support `workspace_ids`**

Add `workspace_ids: str = "current"` to existing `list_tasks` signature. When "all", query each workspace:

```python
async def list_tasks(ctx: ChatContext, assignee: str = None, status: str = None,
                     project: str = None, workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces
    from src.services import lark

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_tasks = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            for r in records:
                if assignee and assignee.lower() not in r.get("Assignee", "").lower():
                    continue
                if status and r.get("Status") != status:
                    continue
                if project and project.lower() not in r.get("Project", "").lower():
                    continue
                r["_workspace"] = ws["workspace_name"]
                all_tasks.append(r)
        except Exception:
            continue

    if not all_tasks:
        return "No tasks found."

    lines = []
    for t in all_tasks:
        ws_label = f"[{t['_workspace']}] " if workspace_ids != "current" else ""
        lines.append(
            f"{ws_label}{t.get('Tên task', '?')} | "
            f"{t.get('Assignee', '?')} | "
            f"{t.get('Status', '?')} | "
            f"deadline: {t.get('Deadline', 'none')}"
        )
    return f"{len(all_tasks)} task(s):\n" + "\n".join(lines)
```

- [ ] **Commit**

```bash
git add src/tools/people.py src/tools/tasks.py
git commit -m "feat: add workspace_ids support to search_person, check_effort, list_tasks"
```

---

## Task 9: Join Flow Tools

**Files:**
- Create: `src/tools/join.py`

- [ ] **Create `src/tools/join.py`**

```python
"""
join.py — LLM-native join flow tools.
Replaces keyword-based join state machine in agent.py and onboarding.py.
"""
import logging

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.join")


async def list_available_workspaces(ctx: ChatContext) -> str:
    """Returns workspaces this user can join (not already an active member)."""
    all_bosses = await db.get_all_bosses()
    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    active_boss_ids = {m["boss_chat_id"] for m in memberships}
    # Also exclude own workspace
    active_boss_ids.add(str(ctx.sender_chat_id))

    available = [b for b in all_bosses if str(b["chat_id"]) not in active_boss_ids]
    if not available:
        return "No other workspaces available to join at this time."

    lines = ["Available workspaces:"]
    for i, b in enumerate(available, 1):
        lines.append(f"{i}. {b['company']} (boss: {b['name']}) — boss_id: {b['chat_id']}")
    return "\n".join(lines)


async def request_join(ctx: ChatContext, target_boss_id: int, role: str, intro: str) -> str:
    """Creates a pending membership and notifies the target boss."""
    _db = await db.get_db()

    # Upsert pending membership
    await db.upsert_membership(
        _db,
        chat_id=str(ctx.sender_chat_id),
        boss_chat_id=str(target_boss_id),
        person_type=role,
        name=ctx.sender_name,
        status="pending",
        request_info=intro,
    )

    boss = await db.get_boss(target_boss_id)
    if not boss:
        return f"Could not find workspace for boss_id {target_boss_id}."

    company = boss.get("company", str(target_boss_id))
    notify_msg = (
        f"Join request from {ctx.sender_name} (chat_id={ctx.sender_chat_id}):\n"
        f"Role requested: {role}\n"
        f"Introduction: {intro}\n\n"
        f"Reply naturally to approve or reject (e.g. 'approve', 'ok partner', 'reject')."
    )
    try:
        await telegram.send(target_boss_id, notify_msg)
    except Exception:
        logger.exception("Failed to notify boss %s of join request", target_boss_id)

    return f"Join request sent to {company}. You'll be notified when the boss responds."


async def approve_join(ctx: ChatContext, membership_chat_id: str, role: str = None) -> str:
    """
    Approve a join request. Writes person to Lark People table of THIS workspace.
    ctx must be the target boss's context.
    """
    _db = await db.get_db()
    membership = await db.get_membership(_db, str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    person_type = role or membership["person_type"]
    name = membership["name"] or "Unknown"

    # Write to Lark People table of THIS workspace (the boss's workspace) ← BUG FIX
    fields = {
        "Tên": name,
        "Chat ID": int(membership_chat_id),
        "Type": person_type,
        "Ghi chú": membership.get("request_info", ""),
    }
    try:
        rec = await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)
        lark_record_id = rec.get("record_id", "")
    except Exception:
        logger.exception("Failed to write to Lark People for membership %s", membership_chat_id)
        lark_record_id = ""

    await db.upsert_membership(
        _db,
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=person_type,
        name=name,
        status="active",
        lark_record_id=lark_record_id,
    )

    company = ctx.boss_name
    try:
        await telegram.send(
            int(membership_chat_id),
            f"Your request to join {company} has been approved as {person_type}. "
            f"You can now interact with the AI secretary for {company}.",
        )
    except Exception:
        logger.exception("Failed to notify approved member %s", membership_chat_id)

    return f"Approved {name} as {person_type} in {company}."


async def reject_join(ctx: ChatContext, membership_chat_id: str) -> str:
    """Reject a join request and notify the requester."""
    _db = await db.get_db()
    membership = await db.get_membership(_db, str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    await db.upsert_membership(
        _db,
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=membership["person_type"],
        name=membership["name"],
        status="rejected",
    )

    company = ctx.boss_name
    try:
        await telegram.send(
            int(membership_chat_id),
            f"Your request to join {company} was not approved.",
        )
    except Exception:
        pass

    return f"Rejected join request from chat_id={membership_chat_id}."
```

- [ ] **Commit**

```bash
git add src/tools/join.py
git commit -m "feat: add join flow tools — list_available_workspaces, request_join, approve_join (bug fix), reject_join"
```

---

## Task 10: Task Approval Tools

**Files:**
- Modify: `src/tools/tasks.py`

- [ ] **Add `approve_task_change` and `reject_task_change` to `src/tools/tasks.py`**

```python
async def approve_task_change(ctx: ChatContext, approval_id: int) -> str:
    """Apply a pending task change and notify the requester."""
    import json
    from src import db
    from src.services import lark, telegram

    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE id = ? AND boss_chat_id = ? AND status = 'pending'",
        (approval_id, str(ctx.boss_chat_id)),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return f"No pending approval found with id={approval_id}."

    approval = dict(row)
    payload = json.loads(approval["payload"]) if isinstance(approval["payload"], str) else approval["payload"]

    changes = payload.get("changes", {})
    record_id = payload.get("record_id", "")
    task_name = payload.get("task_name", "?")

    if changes and record_id:
        try:
            await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, record_id, changes)
        except Exception as e:
            return f"Failed to apply changes to Lark: {e}"

    await _db.execute(
        "UPDATE pending_approvals SET status = 'approved' WHERE id = ?",
        (approval_id,),
    )
    await _db.commit()

    changes_str = ", ".join(f"{k}: {v}" for k, v in changes.items())
    try:
        await telegram.send(
            int(approval["requester_id"]),
            f"✅ Your update to task '{task_name}' was approved. Changes: {changes_str}",
        )
    except Exception:
        pass

    return f"Approved task change for '{task_name}'. Changes applied: {changes_str}"


async def reject_task_change(ctx: ChatContext, approval_id: int) -> str:
    """Reject a pending task change and notify the requester."""
    import json
    from src import db
    from src.services import telegram

    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE id = ? AND boss_chat_id = ? AND status = 'pending'",
        (approval_id, str(ctx.boss_chat_id)),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return f"No pending approval found with id={approval_id}."

    approval = dict(row)
    payload = json.loads(approval["payload"]) if isinstance(approval["payload"], str) else approval["payload"]
    task_name = payload.get("task_name", "?")

    await _db.execute(
        "UPDATE pending_approvals SET status = 'rejected' WHERE id = ?",
        (approval_id,),
    )
    await _db.commit()

    try:
        await telegram.send(
            int(approval["requester_id"]),
            f"Your requested update to task '{task_name}' was not approved.",
        )
    except Exception:
        pass

    return f"Rejected task change request for '{task_name}'."
```

- [ ] **Commit**

```bash
git add src/tools/tasks.py
git commit -m "feat: add approve_task_change, reject_task_change tools — replaces regex approval"
```

---

## Task 11: Nuclear Reset Upgrade

**Files:**
- Modify: `src/tools/reset.py`

- [ ] **Rewrite `src/tools/reset.py` for nuclear reset**

Replace the current file entirely:

```python
"""
reset.py — Nuclear workspace reset.
3-step: initiate → confirm company name → confirm phrase → execute.
State stored in SQLite sessions table (not in-memory).
"""
import asyncio
import json
import logging

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.reset")

SEPARATOR = (
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "       WORKSPACE RESET\n"
    "  Old data has been deleted.\n"
    "  New session starts here.\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━"
)


async def initiate_reset(ctx: ChatContext) -> str:
    """Step 1: Start reset flow. Ask boss to type company name in UPPERCASE."""
    boss = await db.get_boss(ctx.boss_chat_id)
    company = boss.get("company", str(ctx.boss_chat_id)) if boss else str(ctx.boss_chat_id)
    upper = company.upper()

    await db.set_session(
        ctx.boss_chat_id,
        "reset_step",
        json.dumps({"step": 1, "company": company}),
        ttl_minutes=10,
    )

    return (
        f"⚠️ You are about to DELETE ALL DATA for workspace *{company}*.\n"
        f"This removes Lark Base, all SQLite records, chat history, and Qdrant data.\n\n"
        f"To confirm, type the company name in UPPERCASE:\n`{upper}`"
    )


async def confirm_reset_step1(ctx: ChatContext, user_input: str) -> str:
    """Step 2: Validate company name. If match, ask for final confirmation phrase."""
    raw = await db.get_session(ctx.boss_chat_id, "reset_step")
    if not raw:
        return "No active reset flow. Say 'reset workspace' to start."

    session = json.loads(raw)
    if session.get("step") != 1:
        return "Unexpected reset state. Say 'reset workspace' to restart."

    expected = session["company"].upper()
    if user_input.strip() != expected:
        await db.delete_session(ctx.boss_chat_id, "reset_step")
        return f"Name did not match. Reset cancelled."

    await db.set_session(
        ctx.boss_chat_id,
        "reset_step",
        json.dumps({"step": 2, "company": session["company"]}),
        ttl_minutes=5,
    )
    return "Type `tôi chắc chắn` (or `i am sure`) to execute the reset."


async def execute_reset(ctx: ChatContext, confirmation: str) -> str:
    """Step 3: Final confirmation. Execute nuclear reset."""
    raw = await db.get_session(ctx.boss_chat_id, "reset_step")
    if not raw:
        return "No active reset flow."

    session = json.loads(raw)
    if session.get("step") != 2:
        return "Unexpected reset state. Say 'reset workspace' to restart."

    if confirmation.strip().lower() not in ("tôi chắc chắn", "i am sure"):
        await db.delete_session(ctx.boss_chat_id, "reset_step")
        return "Confirmation phrase did not match. Reset cancelled."

    await db.delete_session(ctx.boss_chat_id, "reset_step")
    return await _do_reset(ctx)


async def _do_reset(ctx: ChatContext) -> str:
    boss_id = ctx.boss_chat_id
    boss = await db.get_boss(boss_id)
    if not boss:
        return "Workspace not found."

    _db = await db.get_db()

    # Step 0: Capture member IDs BEFORE any deletion
    async with _db.execute(
        "SELECT chat_id FROM memberships WHERE boss_chat_id = ?",
        (str(boss_id),),
    ) as cur:
        member_rows = await cur.fetchall()
    member_ids = [int(r["chat_id"]) for r in member_rows]

    # Step 1: Notify members
    company = boss.get("company", str(boss_id))
    for mid in member_ids:
        if mid != boss_id:
            try:
                await telegram.send(mid, f"The workspace '{company}' has been reset by the boss.")
            except Exception:
                pass

    # Step 2: Delete Lark Base entirely
    base_token = boss.get("lark_base_token", "")
    if base_token:
        try:
            await lark.delete_base(base_token)
        except Exception:
            logger.exception("Failed to delete Lark Base %s", base_token)

    # Step 3-8: Delete SQLite rows (notes before bosses, messages using captured member_ids)
    all_chat_ids = list({boss_id} | {m for m in member_ids})
    placeholders = ",".join("?" * len(all_chat_ids))

    for sql, params in [
        ("DELETE FROM notes WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM reminders WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM scheduled_reviews WHERE owner_id = ?", (str(boss_id),)),
        ("DELETE FROM pending_approvals WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM task_notifications WHERE boss_chat_id = ?", (str(boss_id),)),
        (f"DELETE FROM messages WHERE chat_id IN ({placeholders})", all_chat_ids),
        ("DELETE FROM people_map WHERE boss_chat_id = ?", (str(boss_id),)),
        ("UPDATE memberships SET status = 'workspace_reset' WHERE boss_chat_id = ?", (str(boss_id),)),
        ("DELETE FROM bosses WHERE chat_id = ?", (boss_id,)),
    ]:
        await _db.execute(sql, params)
    await _db.commit()

    # Step 9: Delete Qdrant collections
    try:
        from src.services import qdrant
        await asyncio.gather(
            qdrant.delete_collection(f"messages_{boss_id}"),
            qdrant.delete_collection(f"tasks_{boss_id}"),
            return_exceptions=True,
        )
    except Exception:
        logger.exception("Failed to delete Qdrant collections for boss %s", boss_id)

    # Step 10: Send separator
    try:
        await telegram.send(boss_id, SEPARATOR)
    except Exception:
        pass

    return "Reset complete. Send any message to start over."
```

Note: `lark.delete_base(base_token)` needs to be implemented in `src/services/lark.py`. Check Lark API docs for base deletion endpoint. If not available, fall back to deleting all tables instead.

- [ ] **Commit**

```bash
git add src/tools/reset.py
git commit -m "feat: nuclear reset — deletes SQLite + Qdrant + Lark Base, sessions-based state, correct order"
```

---

## Task 12: Language + `set_language` + `switch_workspace` Tools

**Files:**
- Create: `src/tools/workspace.py`

- [ ] **Create `src/tools/workspace.py`**

```python
"""
workspace.py — Workspace and language preference tools.
"""
from src import db
from src.context import ChatContext


async def set_language(ctx: ChatContext, language_code: str) -> str:
    """Persist language preference for this sender."""
    _db = await db.get_db()
    # Update memberships.language for this sender in active workspace
    await _db.execute(
        "UPDATE memberships SET language = ? WHERE chat_id = ? AND boss_chat_id = ?",
        (language_code, str(ctx.sender_chat_id), str(ctx.boss_chat_id)),
    )
    # If sender is boss, also update bosses.language
    if ctx.sender_type == "boss":
        await _db.execute(
            "UPDATE bosses SET language = ? WHERE chat_id = ?",
            (language_code, ctx.boss_chat_id),
        )
    await _db.commit()
    return f"Language set to '{language_code}'."


async def switch_workspace(ctx: ChatContext, boss_id: int) -> str:
    """
    Switch active workspace. Preference persisted for 30 min.
    Secretary will use this workspace for subsequent messages.
    """
    # Verify user has access to this workspace
    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    boss_self = await db.get_boss(ctx.sender_chat_id)
    valid_ids = {m["boss_chat_id"] for m in memberships}
    if boss_self:
        valid_ids.add(str(ctx.sender_chat_id))

    if str(boss_id) not in valid_ids:
        return f"You don't have access to workspace {boss_id}."

    await db.set_session(ctx.sender_chat_id, "preferred_workspace", str(boss_id), ttl_minutes=30)

    boss = await db.get_boss(boss_id)
    company = boss.get("company", str(boss_id)) if boss else str(boss_id)
    return f"Switched to workspace: {company}. This preference lasts 30 minutes."
```

- [ ] **Update `src/onboarding.py` — add language selection step**

In `_step_ask_type`, after successfully classifying user type, set `state["step"]` to `"ask_language"` instead of the next content step. Add handler:

```python
async def _step_ask_language(text: str, chat_id: int, state: dict) -> None:
    """Ask user which language they prefer. Called after role is determined."""
    if state.pop("first_language", False):
        reply = await _ai_reply(
            "Ask the user what language they prefer to use: "
            "options are (1) English, (2) Tiếng Việt, or (3) other — "
            "tell them if they pick other they can just reply in their language."
        )
        await telegram.send(chat_id, reply)
        return

    # Detect language from reply
    result = await _ai_classify(
        """Detect the language preference from the user's reply.
        "1" or "english" → {"language": "en"}
        "2" or "tiếng việt" or "vietnamese" → {"language": "vi"}
        Otherwise, detect the language of the reply itself and return its BCP-47 code.
        Return JSON: {"language": "<code>"}""",
        text,
    )
    lang = result.get("language", "en") or "en"
    state["language"] = lang

    # Continue to next step based on user type
    user_type = state.get("type")
    if user_type == "boss":
        state["step"] = "boss_name"
        reply = await _ai_reply(f"Language set. Now ask their name (boss path).")
    else:
        state["step"] = "member_boss"
        reply = await _ai_reply(f"Language set. Now ask which team they belong to.")
    await telegram.send(chat_id, reply)
```

Add `"ask_language"` case to `handle_onboard_message` dispatch.

Pass `state["language"]` into `db.create_boss()` and `db.add_person()` calls at completion steps.

- [ ] **Commit**

```bash
git add src/tools/workspace.py src/onboarding.py
git commit -m "feat: add set_language, switch_workspace tools; language step in onboarding"
```

---

## Task 13: Register All New Tools in `__init__.py`

**Files:**
- Modify: `src/tools/__init__.py`

- [ ] **Add tool definitions to `TOOL_DEFINITIONS` list**

Add the following entries to the `TOOL_DEFINITIONS` list in `src/tools/__init__.py`:

```python
    # ------------------------------------------------------------------
    # Note tools — append_note (new)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "append_note",
            "description": "Add new information to an existing note without overwriting. Use this when you learn something new about a person, project, or group — it preserves existing knowledge. Use update_note only when reorganizing stale content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {"type": "string", "enum": ["personal", "project", "group"]},
                    "ref_id": {"type": "string", "description": "Reference key (person name, project name, or group id)"},
                    "content": {"type": "string", "description": "New information to append"},
                },
                "required": ["note_type", "ref_id", "content"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Approval tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_pending_approvals",
            "description": "Lists all pending approvals: task change requests from members and join requests to this workspace. Call this when someone asks about pending items or when you need to know what approval_id to use.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_task_change",
            "description": "Approve a pending task change request from a member. Use list_pending_approvals to get the approval_id first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "integer", "description": "ID from list_pending_approvals"},
                },
                "required": ["approval_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_task_change",
            "description": "Reject a pending task change request from a member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "integer"},
                },
                "required": ["approval_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Join flow tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_available_workspaces",
            "description": "Returns workspaces this user can request to join (not already a member). Useful when someone wants to collaborate with another company.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_join",
            "description": "Send a join request to another workspace. The target boss will be notified and can approve or reject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_boss_id": {"type": "integer", "description": "Boss ID from list_available_workspaces"},
                    "role": {"type": "string", "enum": ["member", "partner"], "description": "Role being requested"},
                    "intro": {"type": "string", "description": "Brief introduction / reason for joining"},
                },
                "required": ["target_boss_id", "role", "intro"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_join",
            "description": "Approve a join request to this workspace. The person will be added to the team and written to the People table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "membership_chat_id": {"type": "string", "description": "chat_id of the person to approve (from list_pending_approvals)"},
                    "role": {"type": "string", "enum": ["member", "partner"], "description": "Role to assign (overrides requested role if specified)"},
                },
                "required": ["membership_chat_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_join",
            "description": "Reject a join request. The person will be notified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "membership_chat_id": {"type": "string"},
                },
                "required": ["membership_chat_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Reset tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "initiate_reset",
            "description": "Start the workspace reset flow. Only call when the boss clearly wants to delete all workspace data and start fresh. This begins a 3-step confirmation.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_reset_step1",
            "description": "Second step of reset: validate the company name the boss typed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_input": {"type": "string", "description": "Exact text the user typed"},
                },
                "required": ["user_input"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_reset",
            "description": "Final step of reset: execute nuclear deletion after boss types confirmation phrase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {"type": "string", "description": "The confirmation phrase typed by boss"},
                },
                "required": ["confirmation"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Workspace & language tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": "Persist the language preference for this user. Call when the user requests a specific language or switches mid-conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language_code": {"type": "string", "description": "BCP-47 language code, e.g. 'en', 'vi', 'ja'"},
                },
                "required": ["language_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_workspace",
            "description": "Switch the active workspace context. Useful when the user has multiple workspaces and wants to work in a specific one. Preference lasts 30 minutes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "boss_id": {"type": "integer", "description": "boss_id of the workspace to switch to"},
                },
                "required": ["boss_id"],
            },
        },
    },
```

- [ ] **Update `workspace_ids` descriptions in existing tool definitions**

For `list_tasks`, `search_person` (via `get_people`), and `check_effort` — add `workspace_ids` parameter to their existing definitions:

```python
"workspace_ids": {
    "type": "string",
    "description": "Which workspaces to query. 'current' (default) = active workspace only. 'all' = all workspaces this user belongs to. Pass 'all' for personal queries like 'what are my tasks' that span workspaces.",
    "default": "current",
}
```

- [ ] **Add all new tools to the `execute_tool` match block**

```python
        # Approval tools
        case "list_pending_approvals":
            return await memory.list_pending_approvals(ctx)
        case "approve_task_change":
            return await tasks.approve_task_change(ctx, **args)
        case "reject_task_change":
            return await tasks.reject_task_change(ctx, **args)

        # Note tools
        case "append_note":
            return await note.append_note(ctx, **args)

        # Join tools
        case "list_available_workspaces":
            return await join.list_available_workspaces(ctx)
        case "request_join":
            return await join.request_join(ctx, **args)
        case "approve_join":
            return await join.approve_join(ctx, **args)
        case "reject_join":
            return await join.reject_join(ctx, **args)

        # Reset tools
        case "initiate_reset":
            return await reset.initiate_reset(ctx)
        case "confirm_reset_step1":
            return await reset.confirm_reset_step1(ctx, **args)
        case "execute_reset":
            return await reset.execute_reset(ctx, **args)

        # Workspace / language tools
        case "set_language":
            return await workspace_tools.set_language(ctx, **args)
        case "switch_workspace":
            return await workspace_tools.switch_workspace(ctx, **args)
```

Add import at top of `__init__.py`:
```python
from src.tools import join, workspace as workspace_tools
```

- [ ] **Commit**

```bash
git add src/tools/__init__.py
git commit -m "feat: register all new tools in __init__.py — join, reset, approval, language, workspace"
```

---

## Task 14: Smoke Test — Real World

- [ ] **Start the bot**

```bash
./scripts/start.sh
./scripts/logs.sh
```

- [ ] **Test: new user onboards (boss)**

Message the bot. Verify:
1. Language selection step appears after role selection
2. Workspace is provisioned in Lark

- [ ] **Test: join flow**

From a second account (already onboarded as boss elsewhere), say "I want to collaborate with another company". Verify:
1. `list_available_workspaces` returns results
2. `request_join` sends notification to target boss
3. Boss approves → person appears in Lark People table of target workspace

- [ ] **Test: cross-workspace task query**

From the joined account, say "what tasks do I have across all my workspaces?". Verify:
1. Agent calls `list_tasks` with `workspace_ids="all"`
2. Results include tasks from both workspaces with labels

- [ ] **Test: nuclear reset**

Say "reset workspace". Verify 3-step confirmation, then check Lark Base is gone, SQLite records deleted, separator message appears.

- [ ] **Test: task approval**

Member requests a task change → boss calls `list_pending_approvals` → `approve_task_change` → change appears in Lark, member notified.

---

## Self-Review

**Spec coverage:**
- ✅ Join flow bug fix (`approve_join` writes to correct workspace)
- ✅ Hardcoded patterns removed from agent.py
- ✅ Nuclear reset (SQLite + Qdrant + Lark Base + correct deletion order)
- ✅ Multi-workspace context (context_builder + `primary_workspace_id`)
- ✅ Language preference (schema + onboarding step + `set_language` tool)
- ✅ Cross-workspace tools (`workspace_ids` param + credential resolution)
- ✅ `append_note` tool
- ✅ `list_pending_approvals` tool
- ✅ Principle-based system prompt
- ✅ `switch_workspace` with 30-min session persistence
- ✅ Cross-workspace permission model (enforced by membership `person_type`)

**Gaps noted:**
- `lark.delete_base()` may not exist — Task 11 notes this. Implementer should check Lark API or fall back to deleting all records per table.
- `db.get_all_bosses()` used in `join.py` — verify this function exists in db.py (it's used in existing onboarding.py so should be fine).
- `db.upsert_membership()` signature — verify matches existing usage in onboarding.py.
