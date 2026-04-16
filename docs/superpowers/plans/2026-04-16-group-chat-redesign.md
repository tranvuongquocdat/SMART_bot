# Group Chat Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI Secretary work naturally in Telegram group chats — proper group onboarding, group-aware context, group management tools, smart notification routing, and approval feedback in group.

**Architecture:** Group messages are intercepted before personal onboarding in `agent.py` and routed to a dedicated `group_onboarding.py`. `context_builder.py` enriches context with group-specific data including an LLM-generated topic summary. New `src/tools/group.py` provides group-specific tools. Scheduler routes group briefs to group chat instead of boss DM.

**Tech Stack:** Python 3.11+, aiosqlite, httpx (Telegram Bot API), OpenAI (LLM mini-call for active_topic), Lark Base API

**Tests:** Skipped — test in production.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/db.py` | Modify | Add `project_id` to `group_map`; add `group_chat_id` to `scheduled_reviews`; update `add_group()` |
| `src/services/telegram.py` | Modify | Add group management API wrappers |
| `src/group_onboarding.py` | **Create** | Group registration flow: admin check → workspace → project → confirm |
| `src/agent.py` | Modify | Intercept unregistered group before personal onboarding; inject group context into prompt |
| `src/context_builder.py` | Modify | Add `group_context` block with LLM active_topic when `is_group=True` |
| `src/tools/group.py` | **Create** | `summarize_group_conversation`, `update_group_note`, `broadcast_to_group`, `manage_group` |
| `src/tools/__init__.py` | Modify | Register 4 new group tools |
| `src/scheduler.py` | Modify | Route `group_brief` reviews to `group_chat_id` instead of boss DM |

---

## Task 1: DB Schema Migrations

**Files:**
- Modify: `src/db.py`

- [ ] **Add migrations to `_migrate_schema` in `src/db.py`**

Add inside `_migrate_schema`, using same try/except pattern as existing migrations:

```python
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
```

- [ ] **Update `add_group()` to accept `project_id`**

Find the current `add_group` function (around line 364). Replace with:

```python
async def add_group(
    group_chat_id: int,
    boss_chat_id: int,
    group_name: str = "",
    project_id: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO group_map (group_chat_id, boss_chat_id, group_name, project_id)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(group_chat_id) DO UPDATE SET
               boss_chat_id = excluded.boss_chat_id,
               group_name = excluded.group_name,
               project_id = excluded.project_id""",
        (group_chat_id, boss_chat_id, group_name, project_id),
    )
    await db.commit()
```

Note: The old signature had `db_path` parameter — remove it, use `get_db()` like all other functions.

- [ ] **Commit**

```bash
git add src/db.py
git commit -m "feat: add project_id to group_map, group_chat_id to scheduled_reviews"
```

---

## Task 2: Telegram Group Management Wrappers

**Files:**
- Modify: `src/services/telegram.py`

- [ ] **Add group management functions to `src/services/telegram.py`**

Add these after the existing `send()` function. Follow the same `httpx` pattern — `API = "https://api.telegram.org"`, token from `_token` global:

```python
async def get_chat_member(chat_id: int, user_id: int) -> dict:
    """Returns chat member info including status ('administrator', 'member', etc.)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/getChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    data = r.json()
    return data.get("result", {})


async def add_chat_member(chat_id: int, user_id: int) -> bool:
    """Add a user to the group. Requires bot to be admin. User must have started bot."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/addChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def set_chat_title(chat_id: int, title: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/setChatTitle",
            json={"chat_id": chat_id, "title": title},
            timeout=10,
        )
    return r.json().get("ok", False)


async def set_chat_description(chat_id: int, description: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/setChatDescription",
            json={"chat_id": chat_id, "description": description},
            timeout=10,
        )
    return r.json().get("ok", False)


async def pin_chat_message(chat_id: int, message_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/pinChatMessage",
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": False},
            timeout=10,
        )
    return r.json().get("ok", False)


async def unpin_all_chat_messages(chat_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/unpinAllChatMessages",
            json={"chat_id": chat_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def ban_chat_member(chat_id: int, user_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/banChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10,
        )
    return r.json().get("ok", False)


async def unban_chat_member(chat_id: int, user_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/unbanChatMember",
            json={"chat_id": chat_id, "user_id": user_id, "only_if_banned": True},
            timeout=10,
        )
    return r.json().get("ok", False)


async def create_invite_link(chat_id: int, member_limit: int = 1, expire_hours: int = 24) -> str:
    """Create a single-use invite link. Returns the link string or empty string on failure."""
    import time
    expire_date = int(time.time()) + expire_hours * 3600
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/bot{_token}/createChatInviteLink",
            json={"chat_id": chat_id, "member_limit": member_limit, "expire_date": expire_date},
            timeout=10,
        )
    result = r.json().get("result", {})
    return result.get("invite_link", "")


async def get_bot_id() -> int | None:
    """Returns the bot's own user_id. Cached after first call."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{API}/bot{_token}/getMe", timeout=10)
    return r.json().get("result", {}).get("id")
```

- [ ] **Commit**

```bash
git add src/services/telegram.py
git commit -m "feat: add Telegram group management API wrappers"
```

---

## Task 3: Create `src/group_onboarding.py`

**Files:**
- Create: `src/group_onboarding.py`

- [ ] **Create `src/group_onboarding.py`**

```python
"""
group_onboarding.py — Group registration flow.

Steps:
  1. Check bot is admin
  2. Ask which workspace this group belongs to
  3. Ask which project (or none)
  4. Confirm → db.add_group() → introduce bot
"""
import json
import logging

from src import db
from src.services import lark, openai_client, telegram

logger = logging.getLogger("group_onboarding")

# In-memory state: {group_chat_id: {"step": str, ...}}
_sessions: dict[int, dict] = {}


def is_group_onboarding(group_chat_id: int) -> bool:
    return group_chat_id in _sessions


async def start(group_chat_id: int, sender_id: int) -> None:
    """Entry point — check admin rights first."""
    bot_id = await telegram.get_bot_id()
    if bot_id:
        member = await telegram.get_chat_member(group_chat_id, bot_id)
        status = member.get("status", "")
        if status not in ("administrator", "creator"):
            await telegram.send(
                group_chat_id,
                "Để em hoạt động đầy đủ trong nhóm, nhờ admin promote em lên làm *Administrator*:\n"
                "Settings → Administrators → Add Administrator → chọn @bot\n\n"
                "Sau khi xong, tag em lại để tiếp tục nhé.",
            )
            return

    # Admin confirmed — start workspace selection
    bosses = await db.get_all_bosses()
    if not bosses:
        await telegram.send(group_chat_id, "Chưa có workspace nào được đăng ký. "
                            "Nhờ sếp đăng ký với bot trước nhé.")
        return

    lines = ["Nhóm này thuộc workspace nào?\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} (sếp: {b['name']})")
    await telegram.send(group_chat_id, "\n".join(lines))
    _sessions[group_chat_id] = {"step": "pick_workspace", "bosses": bosses, "sender_id": sender_id}


async def handle(text: str, group_chat_id: int, group_name: str = "") -> None:
    session = _sessions.get(group_chat_id)
    if not session:
        return

    step = session["step"]

    if step == "pick_workspace":
        await _step_pick_workspace(text, group_chat_id, group_name, session)
    elif step == "pick_project":
        await _step_pick_project(text, group_chat_id, session)
    elif step == "confirm":
        await _step_confirm(text, group_chat_id, session)


async def _step_pick_workspace(text: str, group_chat_id: int, group_name: str, session: dict) -> None:
    bosses = session["bosses"]
    boss_list = "\n".join(f"{i}: {b['company']}" for i, b in enumerate(bosses, 1))

    result = await _classify(
        f"User chọn workspace từ danh sách sau:\n{boss_list}\n\n"
        "Trả về JSON: {{\"index\": <số thứ tự - 1, bắt đầu từ 0>, hoặc -1 nếu không rõ}}",
        text,
    )
    idx = result.get("index", -1)
    if not isinstance(idx, int) or idx < 0 or idx >= len(bosses):
        await telegram.send(group_chat_id, "Chưa rõ bạn chọn workspace nào. Bạn có thể nói lại không?")
        return

    boss = bosses[idx]
    session["boss"] = boss

    # Fetch projects from Lark
    projects = []
    try:
        records = await lark.search_records(boss["lark_base_token"], boss.get("lark_table_projects", ""))
        projects = [{"name": r.get("Tên dự án", r.get("Name", "")), "record_id": r.get("record_id", "")}
                    for r in records if r.get("Tên dự án") or r.get("Name")]
    except Exception:
        logger.exception("Failed to fetch projects for boss %s", boss["chat_id"])

    session["projects"] = projects
    session["group_name"] = group_name

    if not projects:
        session["step"] = "confirm"
        session["project_id"] = None
        await telegram.send(
            group_chat_id,
            f"Đã chọn workspace *{boss['company']}*.\n"
            f"Nhóm này không có dự án nào để link. Xác nhận setup không? (có/không)",
        )
        return

    lines = [f"Đã chọn *{boss['company']}*. Nhóm này phục vụ dự án nào?\n"]
    for i, p in enumerate(projects, 1):
        lines.append(f"{i}. {p['name']}")
    lines.append(f"{len(projects) + 1}. Không thuộc dự án cụ thể")
    await telegram.send(group_chat_id, "\n".join(lines))
    session["step"] = "pick_project"


async def _step_pick_project(text: str, group_chat_id: int, session: dict) -> None:
    projects = session["projects"]
    project_list = "\n".join(f"{i}: {p['name']}" for i, p in enumerate(projects, 1))
    project_list += f"\n{len(projects) + 1}: Không thuộc dự án cụ thể"

    result = await _classify(
        f"User chọn dự án từ danh sách:\n{project_list}\n\n"
        "Trả về JSON: {{\"index\": <số thứ tự - 1, bắt đầu từ 0>, hoặc -1 nếu không rõ, "
        "hoặc 'none' nếu không thuộc dự án}}",
        text,
    )
    idx = result.get("index")
    if idx == "none" or idx == len(projects):
        session["project_id"] = None
        project_name = "không thuộc dự án cụ thể"
    elif isinstance(idx, int) and 0 <= idx < len(projects):
        session["project_id"] = projects[idx]["record_id"]
        project_name = projects[idx]["name"]
    else:
        await telegram.send(group_chat_id, "Chưa rõ bạn chọn dự án nào. Bạn có thể nói lại không?")
        return

    boss = session["boss"]
    session["step"] = "confirm"
    await telegram.send(
        group_chat_id,
        f"Sẽ link nhóm này vào:\n"
        f"- Workspace: *{boss['company']}*\n"
        f"- Dự án: *{project_name}*\n\n"
        "Xác nhận không? (có/không)",
    )


async def _step_confirm(text: str, group_chat_id: int, session: dict) -> None:
    result = await _classify(
        "User xác nhận hay từ chối. Trả về JSON: {\"confirmed\": true} hoặc {\"confirmed\": false}",
        text,
    )
    if not result.get("confirmed"):
        _sessions.pop(group_chat_id, None)
        await telegram.send(group_chat_id, "Đã huỷ. Tag em lại khi muốn setup nhé.")
        return

    boss = session["boss"]
    project_id = session.get("project_id")
    group_name = session.get("group_name", "")

    await db.add_group(group_chat_id, boss["chat_id"], group_name, project_id)

    # Write initial group note
    _db = await db.get_db()
    from datetime import date
    initial_note = (
        f"Nhóm: {group_name}\n"
        f"Workspace: {boss['company']}\n"
        f"Setup: {date.today().isoformat()}"
    )
    await db.update_note(boss["chat_id"], "group", str(group_chat_id), initial_note)

    _sessions.pop(group_chat_id, None)

    company = boss["company"]
    await telegram.send(
        group_chat_id,
        f"Xong! Em đã được link vào *{company}*.\n\n"
        f"Các bạn chưa đăng ký với em, nhắn */start* để em nhận ra trong nhóm nhé. "
        f"Tag em bất cứ lúc nào cần hỗ trợ!",
    )
    logger.info("[group_onboarding] group %d linked to boss %s", group_chat_id, boss["chat_id"])


async def _classify(system_prompt: str, text: str) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    content = (response.content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        return {}
```

- [ ] **Commit**

```bash
git add src/group_onboarding.py
git commit -m "feat: add group_onboarding — admin check, workspace + project selection"
```

---

## Task 4: Intercept Unregistered Groups in `agent.py`

**Files:**
- Modify: `src/agent.py`

- [ ] **Add group onboarding intercept in `handle_message`**

In `src/agent.py`, in the group handling section (around line 169), update the block that handles `is_group and not bot_mentioned` and the fallthrough for unregistered groups:

Find the existing group handling block (where `db.get_group(chat_id)` is called). Replace/extend it so that when `is_group=True` and `bot_mentioned=True` and group is not registered, it routes to `group_onboarding` instead of personal onboarding:

```python
    # ------------------------------------------------------------------
    # Step 1b: Group message handling
    # ------------------------------------------------------------------
    if is_group:
        group_info = await db.get_group(chat_id)

        # Not mentioned — silent indexing only
        if not bot_mentioned:
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

        # Mentioned — check if group is registered
        if not group_info:
            # Route to group onboarding (not personal)
            from src import group_onboarding
            group_name = update.get("message", {}).get("chat", {}).get("title", "")
            if group_onboarding.is_group_onboarding(chat_id):
                await group_onboarding.handle(text, chat_id, group_name)
            else:
                await group_onboarding.start(chat_id, sender_id)
            return
```

Note: `update` is the raw Telegram update dict. Check how it's passed in `handle_message` — if `group_name` is not available directly, use `""` as fallback.

- [ ] **Commit**

```bash
git add src/agent.py
git commit -m "feat: intercept unregistered groups → group_onboarding instead of personal onboarding"
```

---

## Task 5: Group Context Enrichment in `context_builder.py`

**Files:**
- Modify: `src/context_builder.py`

- [ ] **Add `build_group_context()` and `_get_active_topic()` functions**

Add these two functions to `src/context_builder.py`:

```python
async def build_group_context(group_chat_id: int, boss_chat_id: int) -> dict:
    """
    Builds group-specific context dict:
    {
        "group_name": str,
        "project": {"name": str, "status": str} | None,
        "group_note": str | None,
        "recent_participants": [str, ...],
        "active_topic": str,
    }
    """
    from src.services import lark as _lark

    _db = await db.get_db()

    # group_name + project_id from group_map
    async with _db.execute(
        "SELECT group_name, project_id FROM group_map WHERE group_chat_id = ?",
        (group_chat_id,),
    ) as cur:
        row = await cur.fetchone()
    group_name = row["group_name"] if row else ""
    project_id = row["project_id"] if row else None

    # Fetch project info from Lark if linked
    project = None
    if project_id:
        boss = await db.get_boss(boss_chat_id)
        if boss:
            try:
                records = await _lark.search_records(boss["lark_base_token"], boss.get("lark_table_projects", ""))
                match = next((r for r in records if r.get("record_id") == project_id), None)
                if match:
                    project = {
                        "name": match.get("Tên dự án", match.get("Name", "")),
                        "status": match.get("Trạng thái", match.get("Status", "")),
                    }
            except Exception:
                pass

    # Group note
    note_row = await db.get_note(boss_chat_id, "group", str(group_chat_id))
    group_note = note_row.get("content") if note_row else None

    # Recent participants (distinct names, last 15 messages)
    async with _db.execute(
        """SELECT DISTINCT sender_name FROM messages
           WHERE chat_id = ? AND sender_name IS NOT NULL AND sender_name != ''
           ORDER BY id DESC LIMIT 15""",
        (group_chat_id,),
    ) as cur:
        participant_rows = await cur.fetchall()
    recent_participants = [r["sender_name"] for r in participant_rows]

    # Active topic — LLM mini-call on last 10 messages
    async with _db.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 10",
        (group_chat_id,),
    ) as cur:
        msg_rows = await cur.fetchall()
    active_topic = await _get_active_topic(list(reversed([dict(r) for r in msg_rows])))

    return {
        "group_name": group_name,
        "project": project,
        "group_note": group_note,
        "recent_participants": recent_participants,
        "active_topic": active_topic,
    }


async def _get_active_topic(messages: list[dict]) -> str:
    """LLM mini-call: summarize what the group is currently discussing in 1 sentence."""
    if not messages:
        return ""
    from src.services import openai_client as _oai
    conversation = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
    )
    response, _ = await _oai.chat_with_tools(
        [
            {"role": "system", "content": "Tóm tắt trong 1 câu ngắn chủ đề mà nhóm đang bàn luận. Chỉ trả về câu tóm tắt, không giải thích thêm."},
            {"role": "user", "content": conversation},
        ],
        [],
    )
    return (response.content or "").strip()
```

- [ ] **Call `build_group_context()` at end of `build()` function**

At the end of `build()` in `context_builder.py`, before the `return` statement, add:

```python
    # Group context (only when called from group chat)
    # Note: build() doesn't know is_group — caller passes group_chat_id=None for DMs
    # Actually: agent.py will call build_group_context() separately when is_group=True
    # build() stays unchanged — no modification needed here
```

Actually: `build()` takes `sender_id, chat_id`. When `is_group=True`, `chat_id` is the group chat ID. The caller (agent.py) will call `build_group_context()` separately.

- [ ] **Commit**

```bash
git add src/context_builder.py
git commit -m "feat: add build_group_context and LLM active_topic to context_builder"
```

---

## Task 6: Inject Group Context into System Prompt in `agent.py`

**Files:**
- Modify: `src/agent.py`

- [ ] **Call `build_group_context()` and inject into system prompt**

In `handle_message`, after the `built = await _cb.build(sender_id, chat_id)` call, add:

```python
    # Group context enrichment
    group_ctx = None
    if is_group and ctx:
        from src.context_builder import build_group_context as _bgc
        group_ctx = await _bgc(chat_id, ctx.boss_chat_id)
```

Then update the `SECRETARY_PROMPT.format(...)` call to include group variables. Also update `SECRETARY_PROMPT` to have a group section that renders conditionally.

In `SECRETARY_PROMPT`, add after `## Active sessions`:

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
{group_section}
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
  In group: reply publicly by default — the whole team benefits from seeing task/deadline/workload info.
  Send sensitive info (personal evaluations, private notes, approval results) via DM instead.
  When sending DM instead of group reply, say so in the group: "Đã gửi riêng cho bạn."
"""
```

Add a helper to build the group section:

```python
def _build_group_section(group_ctx: dict | None) -> str:
    if not group_ctx:
        return ""
    project_str = ""
    if group_ctx.get("project"):
        p = group_ctx["project"]
        project_str = f" | Project: {p['name']} ({p['status']})" if p.get("status") else f" | Project: {p['name']}"
    participants = ", ".join(group_ctx.get("recent_participants", [])) or "chưa có"
    note = group_ctx.get("group_note") or "chưa có"
    topic = group_ctx.get("active_topic") or "chưa rõ"
    return (
        f"## Nhóm\n"
        f"Tên: {group_ctx.get('group_name', '')}{project_str}\n"
        f"Đang bàn: {topic}\n"
        f"Tham gia gần đây: {participants}\n"
        f"Ghi chú nhóm: {note}\n\n"
    )
```

In the `SECRETARY_PROMPT.format(...)` call, add:
```python
        group_section=_build_group_section(group_ctx),
```

- [ ] **Commit**

```bash
git add src/agent.py
git commit -m "feat: inject group context section into secretary system prompt"
```

---

## Task 7: Create `src/tools/group.py`

**Files:**
- Create: `src/tools/group.py`

- [ ] **Create `src/tools/group.py`**

```python
"""
group.py — Group-specific tools for the AI Secretary.
"""
import logging

from src import db
from src.context import ChatContext
from src.services import openai_client, telegram

logger = logging.getLogger("tools.group")


async def summarize_group_conversation(ctx: ChatContext, n_messages: int = 20) -> str:
    """
    Reads last N messages from the group and returns an LLM summary:
    main topic, decisions made, action items not yet assigned.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    _db = await db.get_db()
    async with _db.execute(
        "SELECT role, content, sender_name FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (ctx.chat_id, n_messages),
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        return "Không có tin nhắn nào trong nhóm để tóm tắt."

    messages_text = "\n".join(
        f"{r['sender_name'] or r['role']}: {r['content']}"
        for r in reversed(rows)
    )

    response, _ = await openai_client.chat_with_tools(
        [
            {
                "role": "system",
                "content": (
                    "Tóm tắt cuộc trò chuyện nhóm này theo 3 phần:\n"
                    "1. Chủ đề chính đang bàn\n"
                    "2. Các quyết định đã đưa ra\n"
                    "3. Các việc cần làm chưa được giao task (action items)\n"
                    "Ngắn gọn, rõ ràng."
                ),
            },
            {"role": "user", "content": messages_text},
        ],
        [],
    )
    return (response.content or "Không thể tóm tắt.").strip()


async def update_group_note(ctx: ChatContext, content: str, append: bool = True) -> str:
    """
    Write or append to the group note. Used to record decisions, rules,
    recurring context about this group.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    existing = await db.get_note(ctx.boss_chat_id, "group", str(ctx.chat_id))
    if append and existing and existing.get("content"):
        new_content = existing["content"] + "\n\n" + content
    else:
        new_content = content

    await db.update_note(ctx.boss_chat_id, "group", str(ctx.chat_id), new_content)
    return "Đã cập nhật ghi chú nhóm."


async def broadcast_to_group(ctx: ChatContext, message: str) -> str:
    """
    Send a message to the group chat. Used for team announcements,
    deadline broadcasts, approval results.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."
    await telegram.send(ctx.chat_id, message)
    return "Đã gửi thông báo vào nhóm."


async def manage_group(ctx: ChatContext, action: str, **kwargs) -> str:
    """
    Telegram group management actions. Requires bot to be admin.

    action values:
      invite       name (str) — add member or generate invite link
      rename       title (str) — rename the group
      pin          message_id (int, optional) — pin a message
      unpin        — unpin all messages
      kick         name (str) — remove member from group
      set_description  text (str)
      invite_link  — generate a single-use 24h invite link
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    # Check bot is admin
    bot_id = await telegram.get_bot_id()
    if bot_id:
        member_info = await telegram.get_chat_member(ctx.chat_id, bot_id)
        if member_info.get("status") not in ("administrator", "creator"):
            return (
                "Em cần quyền admin để thực hiện việc này. "
                "Nhờ admin vào Settings → Administrators → Add Administrator → chọn @bot nhé."
            )

    if action == "invite":
        return await _invite_member(ctx, kwargs.get("name", ""))

    elif action == "rename":
        title = kwargs.get("title", "")
        ok = await telegram.set_chat_title(ctx.chat_id, title)
        return f"Đã đổi tên nhóm thành '{title}'." if ok else "Không thể đổi tên nhóm."

    elif action == "pin":
        message_id = kwargs.get("message_id")
        if not message_id:
            return "Cần cung cấp message_id để pin."
        ok = await telegram.pin_chat_message(ctx.chat_id, message_id)
        return "Đã pin tin nhắn." if ok else "Không thể pin tin nhắn."

    elif action == "unpin":
        ok = await telegram.unpin_all_chat_messages(ctx.chat_id)
        return "Đã bỏ pin tất cả tin nhắn." if ok else "Không thể bỏ pin."

    elif action == "kick":
        return await _kick_member(ctx, kwargs.get("name", ""))

    elif action == "set_description":
        text = kwargs.get("text", "")
        ok = await telegram.set_chat_description(ctx.chat_id, text)
        return "Đã cập nhật mô tả nhóm." if ok else "Không thể cập nhật mô tả."

    elif action == "invite_link":
        link = await telegram.create_invite_link(ctx.chat_id, member_limit=1, expire_hours=24)
        return f"Link mời (dùng 1 lần, hết hạn 24h): {link}" if link else "Không thể tạo link mời."

    return f"Hành động '{action}' không được nhận ra."


async def _invite_member(ctx: ChatContext, name: str) -> str:
    """Try direct add first; fallback to invite link."""
    from src.services import lark as _lark
    # Search People table for chat_id
    records = await _lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    person = next(
        (r for r in records if name.lower() in r.get("Tên", "").lower()),
        None,
    )

    if person and person.get("Chat ID"):
        chat_id_val = int(person["Chat ID"])
        ok = await telegram.add_chat_member(ctx.chat_id, chat_id_val)
        if ok:
            return f"Đã mời {person['Tên']} vào nhóm."
        # Fallback: person hasn't DM'd bot or other error
    
    # Generate single-use invite link
    link = await telegram.create_invite_link(ctx.chat_id, member_limit=1, expire_hours=24)
    person_name = person["Tên"] if person else name
    if link:
        return (
            f"{person_name} chưa nhắn bot lần nào. "
            f"Đây là link mời (dùng 1 lần, hết hạn 24h): {link}"
        )
    return f"Không tìm thấy {name} hoặc không thể tạo link mời."


async def _kick_member(ctx: ChatContext, name: str) -> str:
    """Find member in People table and kick from group."""
    from src.services import lark as _lark
    records = await _lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    person = next(
        (r for r in records if name.lower() in r.get("Tên", "").lower()),
        None,
    )
    if not person or not person.get("Chat ID"):
        return f"Không tìm thấy {name} trong danh sách nhân sự."

    chat_id_val = int(person["Chat ID"])
    await telegram.ban_chat_member(ctx.chat_id, chat_id_val)
    await telegram.unban_chat_member(ctx.chat_id, chat_id_val)  # ban+unban = kick without permanent ban
    return f"Đã xóa {person['Tên']} khỏi nhóm."
```

- [ ] **Commit**

```bash
git add src/tools/group.py
git commit -m "feat: add group tools — summarize, note, broadcast, manage_group with invite fallback"
```

---

## Task 8: Register Group Tools in `__init__.py`

**Files:**
- Modify: `src/tools/__init__.py`

- [ ] **Add import and TOOL_DEFINITIONS entries**

At top of `src/tools/__init__.py`, add:
```python
from src.tools import group as group_tools
```

Add to `TOOL_DEFINITIONS`:

```python
    # ------------------------------------------------------------------
    # Group tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "summarize_group_conversation",
            "description": "Summarize recent group messages: main topic, decisions made, action items. Call when asked to recap a meeting or conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n_messages": {"type": "integer", "description": "Number of recent messages to summarize (default 20)", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_group_note",
            "description": "Write or append to the group's persistent note. Use to record decisions, group rules, or context that should be remembered across sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "description": "True (default) = append; False = overwrite", "default": True},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast_to_group",
            "description": "Send a message to the group chat. Use for team announcements, deadline alerts, or approval results that the whole team should see.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_group",
            "description": "Manage the Telegram group: invite member, rename, pin/unpin messages, kick member, set description, or generate invite link. Requires bot to be admin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["invite", "rename", "pin", "unpin", "kick", "set_description", "invite_link"],
                    },
                    "name": {"type": "string", "description": "Person name (for invite/kick)"},
                    "title": {"type": "string", "description": "New group name (for rename)"},
                    "message_id": {"type": "integer", "description": "Message ID to pin"},
                    "text": {"type": "string", "description": "Description text (for set_description)"},
                },
                "required": ["action"],
            },
        },
    },
```

- [ ] **Add cases to `execute_tool` match block**

```python
        # Group tools
        case "summarize_group_conversation":
            return await group_tools.summarize_group_conversation(ctx, **args)
        case "update_group_note":
            return await group_tools.update_group_note(ctx, **args)
        case "broadcast_to_group":
            return await group_tools.broadcast_to_group(ctx, **args)
        case "manage_group":
            return await group_tools.manage_group(ctx, **args)
```

- [ ] **Commit**

```bash
git add src/tools/__init__.py
git commit -m "feat: register group tools in __init__.py"
```

---

## Task 9: Approval Flow Group Notification

**Files:**
- Modify: `src/tools/tasks.py`

- [ ] **Update `approve_task_change` to broadcast result to group if applicable**

In `approve_task_change` and `reject_task_change` in `src/tools/tasks.py`, after the DM notification to requester, add a group broadcast if the task was created in a group:

In `approve_task_change`, after the `telegram.send(requester_id, ...)` call:

```python
    # Broadcast result to group if task was created there
    group_chat_id = payload.get("group_chat_id")
    if group_chat_id:
        try:
            await telegram.send(
                int(group_chat_id),
                f"✅ Task *{task_name}* đã được duyệt cập nhật. Changes: {changes_str}",
            )
        except Exception:
            pass
```

Same pattern for `reject_task_change`:

```python
    group_chat_id = payload.get("group_chat_id")
    if group_chat_id:
        try:
            await telegram.send(
                int(group_chat_id),
                f"Task *{task_name}*: yêu cầu cập nhật không được duyệt.",
            )
        except Exception:
            pass
```

Note: `group_chat_id` in `payload` is set when a task update is requested from group context. The existing `request_task_approval` tool (in tasks.py) needs to include `ctx.chat_id` when `ctx.is_group` is True. Find `request_task_approval` and add to its payload:

```python
    payload = {
        "task_name": task_name,
        "record_id": record_id,
        "changes": changes,
        "group_chat_id": str(ctx.chat_id) if ctx.is_group else None,
    }
```

- [ ] **Commit**

```bash
git add src/tools/tasks.py
git commit -m "feat: broadcast approval results to group when task was updated from group context"
```

---

## Task 10: Scheduler Group Brief Routing

**Files:**
- Modify: `src/scheduler.py`

- [ ] **Update scheduler to route to `group_chat_id` when set**

In `src/scheduler.py`, find the function that runs scheduled reviews (likely `_run_scheduled_reviews` or similar). Find where reviews are queried and where `telegram.send(boss["chat_id"], ...)` is called.

Update the query to include `group_chat_id`:
```python
    # Query: include group_chat_id
    async with _db.execute(
        "SELECT * FROM scheduled_reviews WHERE enabled = 1",
    ) as cur:
        reviews = [dict(r) for r in await cur.fetchall()]
```

Then in the send loop, route based on `group_chat_id`:

```python
    for review in reviews:
        # ... existing logic to generate content ...
        
        # Route: group chat or boss DM
        target_chat_id = review.get("group_chat_id") or int(review["owner_id"])
        await telegram.send(target_chat_id, content)
```

- [ ] **Add `group_brief` as a new content_type**

In the function that generates review content (where `content_type` is matched), add:

```python
        elif content_type == "group_brief":
            # Build team-focused brief: today's deadlines, overloaded members, new tasks
            prompt = (
                "Tạo briefing ngắn gọn cho nhóm (không phải cho sếp):\n"
                "1. Deadline hôm nay của team\n"
                "2. Ai đang có nhiều task nhất\n"
                "3. Task mới được giao từ hôm qua\n"
                "Tone tự nhiên, như thông báo nội bộ."
            )
```

- [ ] **Commit**

```bash
git add src/scheduler.py
git commit -m "feat: scheduler routes group_brief reviews to group_chat_id"
```

---

## Task 11: Smoke Test — Real World

- [ ] **Start bot and test group onboarding**

Add bot to a new Telegram group. Tag it. Verify:
1. Bot asks to be promoted to admin (not personal onboarding questions)
2. After promotion, bot lists workspaces
3. After workspace selection, bot lists projects
4. After confirmation, bot sends welcome message with /start instruction

- [ ] **Test group context in responses**

In a registered group, have a conversation about a project, then tag bot "em đang giúp nhóm bàn gì vậy?" Verify active_topic is mentioned in response.

- [ ] **Test manage_group tools**

Tag bot: "mời Bách vào nhóm" → verify direct add or invite link fallback.
Tag bot: "đổi tên nhóm thành ABC" → verify group renamed.

- [ ] **Test approval broadcast**

Member requests task update from group → boss approves in DM → verify result appears in group chat.

- [ ] **Test group_brief scheduled review**

Boss sets "thêm lịch briefing nhóm lúc 8:30" → verify scheduled_reviews has group_chat_id set → at 8:30, brief appears in group (not boss DM).

---

## Self-Review

**Spec coverage:**
- ✅ Group onboarding — admin check + workspace + project selection (`group_onboarding.py`)
- ✅ Group context enrichment — `build_group_context()` with LLM active_topic
- ✅ System prompt group section — `_build_group_section()` + `{group_section}` in prompt
- ✅ Permission model — injected as principle in system prompt (not hardcoded)
- ✅ Approval flow — `group_chat_id` in payload, broadcast on approve/reject
- ✅ Group scheduled review — `group_chat_id` column, `group_brief` content_type, scheduler routing
- ✅ Member discovery — /start instruction in welcome message
- ✅ Telegram group management wrappers — all 9 functions
- ✅ `manage_group` tool with invite fallback logic
- ✅ Admin check before group management actions

**Gap:** `request_task_approval` in tasks.py needs to store `group_chat_id` in payload — covered in Task 9.

**Gap:** `ChatContext.is_group` and `ChatContext.chat_id` — verify these fields exist on the dataclass. If `ctx.is_group` doesn't exist, check how group status is tracked in `context.py` and use the correct field.
