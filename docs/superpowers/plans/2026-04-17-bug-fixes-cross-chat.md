# Bug Fixes + Cross-Chat Flows + Agent Intelligence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs, add multi-workspace summary, improve agent prompts, and wire cross-chat task completion notifications.

**Architecture:** All changes are to existing files — no new tables, no new services. Completion notifications use `asyncio.create_task` for the Telegram+log side-effects so they don't block the tool response. Multi-workspace summary follows the existing `get_workload` pattern via `resolve_workspaces`.

**Tech Stack:** Python 3.12, aiosqlite, Lark Base API, python-telegram-bot, APScheduler, pytest + AsyncMock

---

## File Map

| File | What changes |
|------|-------------|
| `src/tools/__init__.py` | Add `confirm_reset_step1` definition + dispatch; fix `request_join` description; add `workspace_ids` to `get_summary` definition |
| `src/agent.py` | Add 20 THINKING_MAP entries; add cross-chat rules to SECRETARY_PROMPT; fix REMINDER_PROMPT language field |
| `src/tools/summary.py` | Add `workspace_ids` param to `get_summary` |
| `src/tools/tasks.py` | Allow non-boss direct completion; add `_notify_completion` helper; wire notifications in `update_task` |

---

### Task 1: Restore `confirm_reset_step1` in TOOL_DEFINITIONS and dispatch

**Files:**
- Modify: `src/tools/__init__.py:860-883` (reset tools section)
- Modify: `src/tools/__init__.py:1157-1160` (dispatch)

The 3-step reset flow in `src/tools/reset.py` still has `confirm_reset_step1` at line 45, but the LLM cannot call it because it was removed from the definitions. This restores it.

- [ ] **Step 1: Add the tool definition between `initiate_reset` and `execute_reset`**

In `src/tools/__init__.py`, find this block (around line 862):
```python
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
            "name": "execute_reset",
```

Replace with:
```python
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
    {
        "type": "function",
        "function": {
            "name": "execute_reset",
```

- [ ] **Step 2: Add dispatch case**

In `src/tools/__init__.py`, find (around line 1157):
```python
        # Reset tools
        case "initiate_reset":
            return await reset.initiate_reset(ctx)
        case "execute_reset":
            return await reset.execute_reset(ctx, **args)
```

Replace with:
```python
        # Reset tools
        case "initiate_reset":
            return await reset.initiate_reset(ctx)
        case "confirm_reset_step1":
            return await reset.confirm_reset_step1(ctx, **args)
        case "execute_reset":
            return await reset.execute_reset(ctx, **args)
```

- [ ] **Step 3: Verify reset.py has the function**

Run:
```bash
grep -n "confirm_reset_step1" "src/tools/reset.py"
```
Expected output: line 45 with `async def confirm_reset_step1(ctx: ChatContext, user_input: str) -> str:`

- [ ] **Step 4: Commit**

```bash
git add src/tools/__init__.py
git commit -m "fix: restore confirm_reset_step1 to TOOL_DEFINITIONS and dispatch"
```

---

### Task 2: Fix `request_join` description + add `workspace_ids` to `get_summary` definition

**Files:**
- Modify: `src/tools/__init__.py:818` (request_join description)
- Modify: `src/tools/__init__.py:440-458` (get_summary definition)

- [ ] **Step 1: Fix request_join description**

In `src/tools/__init__.py`, find (around line 818):
```python
            "description": "Send a join request to another workspace. The target boss will be notified and can approve or reject.",
```

Replace with:
```python
            "description": "Send a join request to another workspace. Always call list_available_workspaces first to get the target_boss_id. The target boss will be notified and can approve or reject.",
```

- [ ] **Step 2: Add workspace_ids param to get_summary definition**

In `src/tools/__init__.py`, find the `get_summary` definition (around line 440):
```python
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Tổng hợp báo cáo task theo ngày hoặc tuần. Dùng khi sếp muốn brief tình hình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_type": {
                        "type": "string",
                        "enum": ["today", "week"],
                        "description": "Loại tóm tắt",
                    },
                    "assignee": {"type": "string", "description": "Lọc theo người (để trống = tất cả)"},
                },
                "required": ["summary_type"],
            },
        },
    },
```

Replace with:
```python
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Tổng hợp báo cáo task theo ngày hoặc tuần. Dùng khi sếp muốn brief tình hình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_type": {
                        "type": "string",
                        "enum": ["today", "week"],
                        "description": "Loại tóm tắt",
                    },
                    "assignee": {"type": "string", "description": "Lọc theo người (để trống = tất cả)"},
                    "workspace_ids": {
                        "type": "string",
                        "description": "\"current\" (default) | \"all\" = aggregate across all workspaces this user belongs to.",
                        "default": "current",
                    },
                },
                "required": ["summary_type"],
            },
        },
    },
```

- [ ] **Step 3: Commit**

```bash
git add src/tools/__init__.py
git commit -m "fix: update request_join description; add workspace_ids to get_summary tool definition"
```

---

### Task 3: Add THINKING_MAP entries + SECRETARY_PROMPT cross-chat rules

**Files:**
- Modify: `src/agent.py:76-96` (THINKING_MAP)
- Modify: `src/agent.py:27-70` (SECRETARY_PROMPT)

- [ ] **Step 1: Add THINKING_MAP entries**

In `src/agent.py`, find the closing `}` of THINKING_MAP (line 96, after `"delete_reminder": "Đang xóa nhắc nhở...",`):
```python
    "delete_reminder": "Đang xóa nhắc nhở...",
}
```

Replace with:
```python
    "delete_reminder": "Đang xóa nhắc nhở...",
    # Tools added after initial release
    "send_dm": "Đang gửi tin nhắn...",
    "broadcast": "Đang gửi thông báo hàng loạt...",
    "get_communication_log": "Đang tra lịch sử liên lạc...",
    "check_team_engagement": "Đang kiểm tra tương tác team...",
    "search_notes": "Đang tìm ghi chú...",
    "get_project_report": "Đang tạo báo cáo dự án...",
    "get_project": "Đang xem dự án...",
    "list_projects": "Đang xem danh sách dự án...",
    "create_project": "Đang tạo dự án...",
    "update_project": "Đang cập nhật dự án...",
    "delete_project": "Đang xóa dự án...",
    "append_note": "Đang thêm ghi chú...",
    "update_note": "Đang cập nhật ghi chú...",
    "create_idea": "Đang lưu ý tưởng...",
    "switch_workspace": "Đang chuyển workspace...",
    "approve_join": "Đang duyệt tham gia...",
    "reject_join": "Đang từ chối...",
    "list_pending_approvals": "Đang xem yêu cầu chờ...",
    "approve_task_change": "Đang duyệt thay đổi...",
    "reject_task_change": "Đang từ chối thay đổi...",
}
```

- [ ] **Step 2: Add cross-chat rules to SECRETARY_PROMPT**

In `src/agent.py`, find the end of SECRETARY_PROMPT (the last line before the closing `"""`):
```python
Never ignore a [TOOL_ERROR] response.
"""
```

Replace with:
```python
Never ignore a [TOOL_ERROR] response.

## Cross-chat rules
- Before answering "have you messaged X" or "did you remind X about Y": always call get_communication_log first.
- When the user asks about tasks/projects/workload across all their workspaces: pass workspace_ids="all".
- After a non-boss member marks a task complete (status → Hoàn thành or Huỷ): the update_task tool will auto-notify the boss and group. You do not need to do this manually.
"""
```

- [ ] **Step 3: Commit**

```bash
git add src/agent.py
git commit -m "feat: add 20 THINKING_MAP entries and cross-chat rules to SECRETARY_PROMPT"
```

---

### Task 4: Fix REMINDER_PROMPT hardcoded Vietnamese

**Files:**
- Modify: `src/agent.py:496-508` (REMINDER_PROMPT)
- Modify: `src/agent.py:554-566` (send_reminder — format call)

- [ ] **Step 1: Update REMINDER_PROMPT to accept language**

In `src/agent.py`, find REMINDER_PROMPT (line 496):
```python
REMINDER_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}. Giao tiếp tiếng Việt, thân thiện, ngắn gọn.
```

Replace that first line only:
```python
REMINDER_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}.
Language: {language}. Respond entirely in that language. Thân thiện, ngắn gọn.
```

- [ ] **Step 2: Extract language from boss in send_reminder**

In `src/agent.py`, find in `send_reminder()` (around line 554):
```python
        boss = await db.get_boss(boss_chat_id)
        company = boss.get("company", "") if boss else ""
        company_info = f" — {company}" if company else ""
```

Replace with:
```python
        boss = await db.get_boss(boss_chat_id)
        company = boss.get("company", "") if boss else ""
        company_info = f" — {company}" if company else ""
        language = boss.get("language", "vi") if boss else "vi"
```

- [ ] **Step 3: Pass language to REMINDER_PROMPT.format()**

In `src/agent.py`, find (around line 561):
```python
        system_content = REMINDER_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
        )
```

Replace with:
```python
        system_content = REMINDER_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
            language=language,
        )
```

- [ ] **Step 4: Commit**

```bash
git add src/agent.py
git commit -m "fix: use boss language preference in REMINDER_PROMPT instead of hardcoded Vietnamese"
```

---

### Task 5: Add `workspace_ids` to `get_summary` implementation

**Files:**
- Modify: `src/tools/summary.py:21-69`
- Test: `tests/unit/test_summary.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_summary.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_ctx(boss_chat_id=1):
    ctx = MagicMock()
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"
    ctx.sender_chat_id = boss_chat_id
    ctx.boss_chat_id = boss_chat_id
    ctx.boss_name = "Boss"
    ctx.sender_type = "boss"
    return ctx


_TASK_A = {"Tên task": "Task A", "Status": "Đang làm", "Assignee": "Alice", "Deadline": 9999999999999}
_TASK_B = {"Tên task": "Task B", "Status": "Hoàn thành", "Assignee": "Bob", "Deadline": 9999999999999}


@pytest.mark.asyncio
async def test_get_summary_current_workspace():
    from src.tools.summary import get_summary
    ctx = _make_ctx()
    with patch("src.tools.summary.lark.search_records", new_callable=AsyncMock,
               return_value=[_TASK_A, _TASK_B]):
        result = await get_summary(ctx, summary_type="today", workspace_ids="current")
    assert "Task A" in result


@pytest.mark.asyncio
async def test_get_summary_all_workspaces_tags_workspace_name():
    from src.tools.summary import get_summary
    from src.tools._workspace import resolve_workspaces
    ctx = _make_ctx()
    ws = {
        "workspace_name": "Công ty X",
        "lark_base_token": "tok2",
        "lark_table_tasks": "tbl2",
    }
    with patch("src.tools.summary.resolve_workspaces", new_callable=AsyncMock, return_value=[ws]), \
         patch("src.tools.summary.lark.search_records", new_callable=AsyncMock,
               return_value=[_TASK_A]):
        result = await get_summary(ctx, summary_type="today", workspace_ids="all")
    assert "[Công ty X]" in result
    assert "Task A" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/dat_macbook/Documents/2025/ý tưởng mới/Dự án hỗ trợ thứ ký giám đốc ảo"
python -m pytest tests/unit/test_summary.py -v
```
Expected: FAIL (signature mismatch or import error)

- [ ] **Step 3: Implement multi-workspace `get_summary`**

Replace the entire `get_summary` function in `src/tools/summary.py` (lines 21-69):
```python
async def get_summary(
    ctx: ChatContext,
    summary_type: str = "today",
    assignee: str = "",
    workspace_ids: str = "current",
) -> str:
    # Multi-workspace path
    if workspace_ids != "current":
        from src.tools._workspace import resolve_workspaces
        workspaces = await resolve_workspaces(ctx, workspace_ids)
        all_records = []
        for ws in workspaces:
            if not ws.get("lark_table_tasks"):
                continue
            try:
                recs = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
                for r in recs:
                    r["_workspace"] = ws["workspace_name"]
                all_records.extend(recs)
            except Exception:
                continue
        records = all_records
    else:
        records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if not records:
        return "Hiện chưa có task nào."

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]

    today_str = date.today().isoformat()
    today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)

    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]
    done = [r for r in records if r.get("Status") in ("Hoàn thành", "Huỷ")]
    overdue = [
        r for r in active
        if _deadline_ts(r) is not None and _deadline_ts(r) < today_ms
    ]

    def _task_line(r: dict) -> str:
        ws = r.get("_workspace", "")
        tag = f"[{ws}] " if ws and workspace_ids != "current" else ""
        return f"  {tag}- {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | DL: {_deadline_str(r)}"

    lines = []
    if summary_type == "week":
        lines.append("Báo cáo tuần:")
        lines.append(f"  Tổng task: {len(records)}")
        lines.append(f"  Hoàn thành/Huỷ: {len(done)}")
        lines.append(f"  Đang làm: {len(active)}")
        lines.append(f"  Quá hạn: {len(overdue)}")
        if overdue:
            lines.append(f"\nTask quá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(_task_line(r))
    else:
        header = f"Tóm tắt hôm nay ({today_str})"
        if assignee:
            header += f" - {assignee}"
        lines.append(header + ":")
        lines.append(f"  Tổng: {len(records)} | Đang làm: {len(active)} | Xong: {len(done)} | Quá hạn: {len(overdue)}")
        if active:
            lines.append(f"\nTask cần xử lý ({len(active)}):")
            for r in active[:10]:
                lines.append(_task_line(r))
        if overdue:
            lines.append(f"\nQuá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(_task_line(r))
        if not active and not overdue:
            lines.append("Không có task nào cần xử lý.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/test_summary.py -v
```
Expected: PASS both tests

- [ ] **Step 5: Commit**

```bash
git add src/tools/summary.py tests/unit/test_summary.py
git commit -m "feat: add workspace_ids param to get_summary for cross-workspace aggregation"
```

---

### Task 6: Cross-chat task completion notifications

**Files:**
- Modify: `src/tools/tasks.py:241-333` (`update_task` function)
- Test: `tests/unit/test_task_completion.py` (create)

The logic: when a non-boss user marks a task "Hoàn thành" or "Huỷ", allow the change directly (no approval needed), then DM the boss and post to the linked group (if any).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_task_completion.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


def _make_ctx(sender_type="member"):
    ctx = MagicMock()
    ctx.lark_base_token = "tok"
    ctx.lark_table_tasks = "tbl"
    ctx.lark_table_people = "ppl"
    ctx.lark_table_projects = "proj"
    ctx.sender_type = sender_type
    ctx.sender_name = "Alice"
    ctx.sender_chat_id = 200
    ctx.boss_chat_id = 100
    ctx.boss_name = "Boss"
    ctx.is_group = False
    ctx.chat_id = 200
    return ctx


_TASK = {
    "record_id": "rec123",
    "Tên task": "Viết báo cáo",
    "Assignee": "Alice",
    "Status": "Đang làm",
    "Project": "Dự án X",
}


@pytest.mark.asyncio
async def test_non_boss_completion_notifies_boss():
    from src.tools import tasks
    ctx = _make_ctx(sender_type="member")

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[_TASK]), \
         patch("src.tools.tasks.lark.update_record", new_callable=AsyncMock), \
         patch("src.tools.tasks.telegram.send", new_callable=AsyncMock) as mock_send, \
         patch("src.tools.tasks.db_mod.log_outbound_dm", new_callable=AsyncMock), \
         patch("src.tools.tasks.db_mod.get_db", new_callable=AsyncMock), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("src.tools.tasks._notify_group_completion", new_callable=AsyncMock) as mock_group, \
         patch("asyncio.create_task", side_effect=lambda coro: asyncio.ensure_future(coro)):
        result = await tasks.update_task(ctx, search_keyword="báo cáo", status="Hoàn thành")

    # Should NOT go through approval path
    assert "Yêu cầu" not in result
    assert "Đã cập nhật" in result
    # Boss should be notified
    mock_send.assert_awaited()
    calls = [str(c) for c in mock_send.call_args_list]
    assert any("100" in c for c in calls)  # boss_chat_id


@pytest.mark.asyncio
async def test_boss_completion_no_notification():
    from src.tools import tasks
    ctx = _make_ctx(sender_type="boss")

    with patch("src.tools.tasks.lark.search_records", new_callable=AsyncMock, return_value=[_TASK]), \
         patch("src.tools.tasks.lark.update_record", new_callable=AsyncMock), \
         patch("src.tools.tasks.telegram.send", new_callable=AsyncMock) as mock_send, \
         patch("src.tools.tasks.db_mod.log_outbound_dm", new_callable=AsyncMock), \
         patch("src.tools.tasks._embed_and_upsert", new_callable=AsyncMock), \
         patch("asyncio.create_task", side_effect=lambda coro: asyncio.ensure_future(coro)):
        result = await tasks.update_task(ctx, search_keyword="báo cáo", status="Hoàn thành")

    # telegram.send should NOT be called with boss_chat_id for completion notification
    for call in mock_send.call_args_list:
        args = call[0]
        # No completion notification message
        assert "vừa hoàn thành" not in str(args)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_task_completion.py -v
```
Expected: FAIL (completion notification not yet implemented)

- [ ] **Step 3: Add `_notify_group_completion` helper to `tasks.py`**

Add this function after `_notify_assignee_task` (around line 119 in `src/tools/tasks.py`):
```python
async def _notify_group_completion(
    ctx: ChatContext,
    task_name: str,
    verb: str,
    task_record: dict,
) -> None:
    """Find the group linked to the task's project and post a completion update."""
    project_name = task_record.get("Project", "")
    if not project_name:
        return
    try:
        all_projects = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
        proj = next(
            (p for p in all_projects if project_name.lower() in p.get("Tên dự án", "").lower()),
            None,
        )
        if not proj:
            return
        _db = await db_mod.get_db()
        async with _db.execute(
            "SELECT group_chat_id FROM group_map WHERE project_id = ?",
            (proj["record_id"],),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        group_chat_id = row["group_chat_id"]
        group_msg = f"Update: task '{task_name}' đã {verb} bởi {ctx.sender_name} ✓"
        await telegram.send(group_chat_id, group_msg)
        await db_mod.log_outbound_dm(
            boss_chat_id=ctx.boss_chat_id,
            to_chat_id=int(group_chat_id),
            to_name="(group)",
            content=group_msg,
            trigger_type="task_completed",
            task_id=proj["record_id"],
        )
    except Exception:
        import logging
        logging.getLogger("tasks").warning(
            "Failed to notify group for task '%s': %s", task_name, "see traceback", exc_info=True
        )
```

- [ ] **Step 4: Wire completion bypass + notifications into `update_task`**

In `src/tools/tasks.py`, find the non-boss check (around line 271):
```python
    # Non-boss: create pending approval request
    if ctx.sender_type in ("member", "partner"):
        record = matched[0]
```

Replace the entire non-boss block through its `return` statement:
```python
    # Non-boss: completion/cancellation bypasses approval — direct update + notify boss
    new_status = fields.get("Status", "")
    if ctx.sender_type in ("member", "partner"):
        if new_status in ("Hoàn thành", "Huỷ") and len(fields) == 1:
            pass  # fall through to direct update path below
        else:
            # Other changes still require approval
            record = matched[0]
            payload = json.dumps({
                "record_id": record["record_id"],
                "task_name": record.get("Tên task", ""),
                "changes": fields,
                "group_chat_id": str(ctx.chat_id) if ctx.is_group else None,
            })
            await db_mod.create_approval(
                db_mod._db,
                str(ctx.boss_chat_id),
                str(ctx.sender_chat_id),
                record["record_id"],
                payload,
            )
            changes_str = ", ".join(
                f"{k}: {_ms_to_date(v) if k == 'Deadline' else v}"
                for k, v in fields.items()
            )
            boss = await db_mod.get_boss(str(ctx.boss_chat_id))
            if boss:
                await telegram.send(
                    ctx.boss_chat_id,
                    f"📝 Yêu cầu cập nhật task từ {ctx.sender_name}:\n\n"
                    f"Task: {record.get('Tên task')}\n"
                    f"Thay đổi: {changes_str}\n\n"
                    f"Reply 'ok task {record.get('Tên task', '')}' để approve.",
                )
            return (f"Yêu cầu cập nhật '{record.get('Tên task')}' đã gửi đến sếp. "
                    f"Bạn sẽ được thông báo khi được xử lý.")
```

Then in the direct-update loop (currently `# Boss: apply directly`, around line 305), add the completion notification after the existing Lark update. Find:
```python
    # Boss: apply directly
    updated = []
    for r in matched:
        rid = r["record_id"]
        task_name = r.get("Tên task", "?")
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, rid, fields)
        merged = {**r, **fields}
        asyncio.create_task(_embed_and_upsert(ctx, rid, merged))
        updated.append(task_name)

        # Notify new assignee if assignee changed
```

Replace with:
```python
    # Direct update (boss, or non-boss completing their task)
    updated = []
    is_completion = new_status in ("Hoàn thành", "Huỷ")
    actor_is_boss = ctx.sender_type == "boss"

    for r in matched:
        rid = r["record_id"]
        task_name = r.get("Tên task", "?")
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, rid, fields)
        merged = {**r, **fields}
        asyncio.create_task(_embed_and_upsert(ctx, rid, merged))
        updated.append(task_name)

        # Cross-chat completion notifications (non-boss only)
        if is_completion and not actor_is_boss:
            verb = "hoàn thành" if new_status == "Hoàn thành" else "huỷ"
            boss_msg = f"{ctx.sender_name} vừa {verb} task '{task_name}'."
            await telegram.send(ctx.boss_chat_id, boss_msg)
            asyncio.create_task(db_mod.log_outbound_dm(
                boss_chat_id=ctx.boss_chat_id,
                to_chat_id=ctx.boss_chat_id,
                to_name=ctx.boss_name,
                content=boss_msg,
                trigger_type="task_completed",
                task_id=rid,
            ))
            asyncio.create_task(_notify_group_completion(ctx, task_name, verb, r))

        # Notify new assignee if assignee changed
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/test_task_completion.py -v
```
Expected: PASS both tests

- [ ] **Step 6: Run all unit tests to check for regressions**

```bash
python -m pytest tests/unit/ -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/tools/tasks.py tests/unit/test_task_completion.py
git commit -m "feat: auto-notify boss and group on non-boss task completion"
```
