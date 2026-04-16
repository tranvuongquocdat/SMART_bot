# Bug Fixes + Cross-Chat Flows + Agent Intelligence — Design Spec

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Fix 4 known bugs, improve agent intelligence via better prompts and tool descriptions, add multi-workspace summary, and implement cross-chat completion notifications so the agent behaves like a real secretary across group and personal chats.

**Date:** 2026-04-16

---

## Scope

Five independent improvement areas, all changes to existing files — no new tables, no new services.

1. Bug fixes (4 items)
2. `get_summary` multi-workspace support
3. SECRETARY_PROMPT guidance improvements
4. Cross-chat task completion notifications
5. THINKING_MAP completeness

---

## 1. Bug Fixes

### 1a. Reset flow — `confirm_reset_step1` missing from TOOL_DEFINITIONS

**Root cause:** Task 15 audit removed `confirm_reset_step1` from `TOOL_DEFINITIONS` and `_dispatch_tool`, but the 3-step reset flow in `reset.py` still depends on it. LLM cannot call step 2 → reset is broken.

**Fix:** Add `confirm_reset_step1` back to `TOOL_DEFINITIONS` and `_dispatch_tool` in `src/tools/__init__.py`.

Tool definition to restore:
```python
{
    "type": "function",
    "function": {
        "name": "confirm_reset_step1",
        "description": "Step 2 of workspace reset: validate the company name the boss typed. Call after initiate_reset once the boss has typed the company name.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_input": {"type": "string", "description": "Exact text the user typed"},
            },
            "required": ["user_input"],
        },
    },
},
```

Dispatch case to restore:
```python
case "confirm_reset_step1":
    return await reset.confirm_reset_step1(ctx, **args)
```

---

### 1b. Reminder language — hardcoded Vietnamese

**Root cause:** `REMINDER_PROMPT` in `src/agent.py` has `"Giao tiếp tiếng Việt"` hardcoded, ignoring the boss's `language` field.

**Fix:** In `send_reminder()`, query boss language and pass it to the prompt:

```python
# In send_reminder(), after `boss = await db.get_boss(boss_chat_id)`:
language = boss.get("language", "vi") if boss else "vi"
# Add to REMINDER_PROMPT template: Language: {language}
```

`REMINDER_PROMPT` becomes:
```python
REMINDER_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}.
Language: {language}. Respond entirely in that language.
...
"""
```

---

### 1c. `request_join` tool description — agent doesn't know to call list first

**Root cause:** `request_join` requires `target_boss_id` (integer) but description doesn't tell the LLM to get it via `list_available_workspaces` first.

**Fix:** Update description in `TOOL_DEFINITIONS`:
```python
"description": "Send a join request to another workspace. Always call list_available_workspaces first to get the target_boss_id. The target boss will be notified and can approve or reject.",
```

---

### 1d. THINKING_MAP — missing entries for new tools

**Root cause:** 15+ tools added since THINKING_MAP was last updated.

**Fix:** Add entries in `src/agent.py`:
```python
"send_dm": "Đang gửi tin nhắn...",
"broadcast": "Đang gửi thông báo hàng loạt...",
"get_communication_log": "Đang tra lịch sử liên lạc...",
"check_team_engagement": "Đang kiểm tra tương tác team...",
"search_notes": "Đang tìm ghi chú...",
"get_project_report": "Đang tạo báo cáo dự án...",
"get_workload": "Đang xem workload...",
"get_project": "Đang xem dự án...",
"list_projects": "Đang xem danh sách dự án...",
"create_project": "Đang tạo dự án...",
"update_project": "Đang cập nhật dự án...",
"delete_project": "Đang xóa dự án...",
"check_effort": "Đang kiểm tra workload...",
"append_note": "Đang thêm ghi chú...",
"update_note": "Đang cập nhật ghi chú...",
"create_idea": "Đang lưu ý tưởng...",
"switch_workspace": "Đang chuyển workspace...",
"approve_join": "Đang duyệt tham gia...",
"reject_join": "Đang từ chối...",
"list_pending_approvals": "Đang xem yêu cầu chờ...",
"approve_task_change": "Đang duyệt thay đổi...",
"reject_task_change": "Đang từ chối thay đổi...",
```

---

## 2. `get_summary` Multi-Workspace Support

**Current:** `get_summary` in `src/tools/summary.py` queries only `ctx.lark_base_token` — the current workspace.

**Fix:** Add `workspace_ids` param, same pattern as `get_workload`:

```python
async def get_summary(
    ctx: ChatContext,
    summary_type: str = "today",
    assignee: str = "",
    workspace_ids: str = "current",
) -> str:
```

When `workspace_ids != "current"`: use `resolve_workspaces(ctx, workspace_ids)` to loop across workspaces, aggregate records, then build combined report with `[WorkspaceName]` tags on each task line.

Update `TOOL_DEFINITIONS` for `get_summary`:
```python
"workspace_ids": {
    "type": "string",
    "description": "\"current\" (default) | \"all\" = aggregate across all workspaces this user belongs to.",
    "default": "current",
},
```

---

## 3. SECRETARY_PROMPT Intelligence Improvements

Three guidance additions to `SECRETARY_PROMPT` in `src/agent.py`:

```
## Cross-chat rules
- Before answering "have you messaged X" or "did you remind X about Y": always call get_communication_log first.
- When the user asks about tasks/projects/workload across all their workspaces: pass workspace_ids="all".
- After a non-boss member marks a task complete (status → Hoàn thành or Huỷ): the update_task tool will auto-notify. You do not need to do this manually.
```

---

## 4. Cross-Chat Task Completion Notifications

**Trigger:** `update_task` called with `status="Hoàn thành"` or `status="Huỷ"` by a non-boss user.

**Implementation in `src/tools/tasks.py` — `update_task()`:**

### Step 1: Detect completion and actor
```python
# After successful Lark update, if status in ("Hoàn thành", "Huỷ"):
is_completion = new_status in ("Hoàn thành", "Huỷ")
actor_is_boss = ctx.sender_type == "boss"
```

### Step 2: DM the boss
```python
if is_completion and not actor_is_boss:
    verb = "hoàn thành" if new_status == "Hoàn thành" else "huỷ"
    boss_msg = f"{ctx.sender_name} vừa {verb} task '{task_name}'."
    await telegram.send(ctx.boss_chat_id, boss_msg)
    await db.log_outbound_dm(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=ctx.boss_chat_id,
        to_name=ctx.boss_name,
        content=boss_msg,
        trigger_type="task_completed",
        task_id=record["record_id"],
    )
```

### Step 3: Find linked group via project
```python
# task record has "Project" field (project name string)
project_name = record.get("Project", "")
group_chat_id = None
if project_name:
    # Find project record_id
    all_projects = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    proj = next(
        (p for p in all_projects if project_name.lower() in p.get("Tên dự án", "").lower()),
        None,
    )
    if proj:
        _db = await db.get_db()
        async with _db.execute(
            "SELECT group_chat_id FROM group_map WHERE project_id = ?",
            (proj["record_id"],),
        ) as cur:
            row = await cur.fetchone()
        if row:
            group_chat_id = row["group_chat_id"]
```

### Step 4: Post to group
```python
if group_chat_id:
    group_msg = f"Update: task '{task_name}' đã {verb} bởi {ctx.sender_name} ✓"
    await telegram.send(group_chat_id, group_msg)
    await db.log_outbound_dm(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=group_chat_id,
        to_name="(group)",
        content=group_msg,
        trigger_type="task_completed",
        task_id=record["record_id"],
    )
```

**Edge cases:**
- Boss marks own task done → skip (actor_is_boss check)
- Task has no Project field → skip group lookup
- Project found but no linked group → skip group post
- Lark/Telegram errors → log warning, don't fail the update

---

## 5. File Map

| File | Change |
|------|--------|
| `src/tools/__init__.py` | Restore `confirm_reset_step1` in definitions + dispatch; add `workspace_ids` to `get_summary` definition |
| `src/agent.py` | Fix `REMINDER_PROMPT` language; add THINKING_MAP entries; add cross-chat rules to SECRETARY_PROMPT |
| `src/tools/summary.py` | Add `workspace_ids` param to `get_summary` |
| `src/tools/tasks.py` | Add completion notification logic in `update_task` |

---

## Non-goals

- No new DB tables or migrations
- No changes to Lark service layer
- No changes to scheduler
- No changes to onboarding (separate spec)
