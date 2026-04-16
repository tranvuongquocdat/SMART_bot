# AI Secretary — Redesign Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Scope:** Tool capability expansion, join flow fix, nuclear reset, multi-workspace, language preference

---

## Design Philosophy

**The agent is smart. Trust it.**

The primary lever for quality is **tool capability**, not flow architecture. Give the Secretary powerful tools that return rich, structured data — then get out of the way. A few lines of principle in the system prompt handle any custom flow better than hardcoded routing logic.

**What this means in practice:**
- No router LLM call. No mode classification. No pre-filtering.
- Secretary receives full context and reasons about what to do.
- Tools do the heavy lifting — credential resolution, cross-workspace queries, compound lookups.
- System prompt gives principles, not procedures.

---

## Problems Being Fixed

1. **Join flow bug** — user joining workspace B is not written to Lark People table of B
2. **Hardcoded patterns** in `agent.py` — keyword lists, regex approval, reset trigger phrases
3. **Reset is partial** — only clears Lark records, not SQLite or Qdrant
4. **No multi-workspace routing** — context always defaults to user's own workspace
5. **No language preference** — Vietnamese hardcoded in prompts
6. **Tools too weak** — only query active workspace, can't reason across workspaces
7. **`update_note` overwrites** — agent loses previous knowledge when updating notes
8. **Approval flow** — boss has no tool to see pending approvals; regex matching is fragile

**Demo scenario:** User is a member of Company A and a partner of Company B. "Tôi đang có task gì?" should aggregate tasks from both workspaces.

---

## Architecture

### Overview

```
Telegram message
        │
        ▼
  context_builder.py  ← pure Python, no LLM call
  Queries: memberships, active sessions, last 5 messages
  Output: structured context dict
        │
        ▼
  secretary.py  ← single LLM agent, full tool set
  Receives: all memberships, active sessions, workspace options, language
  Reasons: which workspace, what to do, which tools to call
        │
        └── escalates to advisor.py when needed (via tool)
```

No router. No mode pre-classification. Secretary gets enough context to reason everything itself.

### context_builder.py (new, pure Python)

Runs before Secretary. No LLM. Queries DB and returns:

```python
{
    "sender_id": 123,
    "memberships": [
        {"workspace": "Company A", "boss_id": 111, "role": "member", "language": "vi"},
        {"workspace": "Company B", "boss_id": 222, "role": "partner", "language": "en"},
    ],
    "active_sessions": {
        "reset_pending": None,            # or {"boss_id": X, "step": 1}
        "join_pending": [...],            # pending join requests this user sent
        "approvals_pending": [...],       # pending approvals this user (as boss) needs to handle
    },
    "last_5_messages": [...],
    "primary_workspace_id": 111,          # boss workspace if exists, else first active membership
}
```

Secretary receives this, builds its own reasoning about which workspace is active.

### Files changed

| File | Change |
|---|---|
| `context_builder.py` | **New** — pure Python context assembly, ~80 lines |
| `agent.py` → `secretary.py` | Remove ALL pre-checks. Pure tool loop + context_builder integration. |
| `onboarding.py` | Add language selection step |
| `src/tools/join.py` | **New** — join flow as tools |
| `src/tools/reset.py` | Upgrade to nuclear reset |
| `src/tools/__init__.py` | Register new tools, update tool descriptions |
| `src/db.py` | Add `language` to `bosses` + `memberships`; add `sessions` table |
| `src/context.py` | Support resolving context for any workspace_id |

---

## Secretary System Prompt — Principle-Based

Short. No procedures. Gives the agent values and situational awareness.

**Injected context (structured, not prose):**
```
You are the AI secretary of {boss_name} — {company}.
Current time: {time}
Language: {language}
Talking to: {sender_name} ({role})
This user is active in: Company A (member), Company B (partner)  ← membership summary
Active workspace: Company A  ← primary, but agent can reason otherwise

People in active workspace:
- Bách | Designer | Team Media
- Linh | Content | Team Media

Your notes about this workspace: {personal_note}
```

**Principles (not rules):**
```
You genuinely know this team. You care about their wellbeing, not just their output.
When making decisions that affect someone, understand their situation first.

You remember everything shared with you. Draw on your notes naturally.
Your notes are your extended memory — when context feels incomplete, check them.

You have access to multiple workspaces. When a question spans workspaces or
doesn't specify one, use your judgment about where to look. You can always check.

You use tools to understand context before acting, not just to execute commands.
```

No step-by-step instructions. No "always call X before Y". The model reasons.

---

## Tool Capability Spec

### Core principle for tool design

Every tool must:
1. Return **rich, labeled data** — enough for the agent to reason without needing another call
2. Handle **credential resolution internally** — agent passes `workspace_ids`, tool figures out the rest
3. Have a description that says **when it's useful**, not when it's mandatory

### Cross-workspace credential resolution pattern

All tools that accept `workspace_ids` follow this pattern internally:

```python
async def resolve_workspaces(user_id: int, workspace_ids: str | list) -> list[dict]:
    """Returns list of {boss_id, lark_base_token, lark_table_X, workspace_name}"""
    if workspace_ids == "current":
        return [current_workspace_from_ctx]
    memberships = await db.get_memberships(user_id)
    if workspace_ids == "all":
        targets = memberships
    else:
        targets = [m for m in memberships if m["boss_chat_id"] in workspace_ids]
    result = []
    for m in targets:
        boss = await db.get_boss(m["boss_chat_id"])
        result.append({**boss, "workspace_name": boss["company"], "user_role": m["person_type"]})
    return result
```

This is the single shared implementation. No per-tool credential logic.

### Tools updated: add `workspace_ids`

| Tool | `workspace_ids` default | Returns |
|---|---|---|
| `search_person(name)` | `"current"` | List with workspace label per result |
| `list_tasks(...)` | `"current"` | List with workspace label per result |
| `check_effort(assignee)` | `"current"` | Workload per workspace |

Tool descriptions hint: *"Pass workspace_ids='all' when the question is about this user across all their workspaces."*

Agent decides when to pass `"all"`. No rule.

### New tools

| Tool | What it does | Why it matters |
|---|---|---|
| `list_available_workspaces()` | Workspaces sender can join (not already a member) | Enables natural join flow |
| `request_join(target_boss_id, role, intro)` | Creates pending membership, notifies boss | LLM-native join — no keyword matching |
| `approve_join(membership_id, role)` | Approves join; writes to Lark People of TARGET workspace | **Fixes the bug** |
| `reject_join(membership_id)` | Rejects join, notifies requester | |
| `list_pending_approvals()` | Shows all pending task changes + join requests awaiting boss action | Agent can now reason about what needs approval |
| `approve_task_change(approval_id)` | Applies change, notifies member | Replaces regex pattern |
| `reject_task_change(approval_id)` | Rejects change, notifies member | |
| `append_note(note_type, ref_id, content)` | Adds to existing note without overwriting | Preserves accumulated knowledge |
| `set_language(language_code)` | Persists language for current sender | |
| `switch_workspace(boss_id)` | Switches active workspace; saves to sessions table (30 min TTL) | For explicit switching |
| `initiate_reset()` | Step 1 of nuclear reset | |
| `confirm_reset_step1(input)` | Validates company name input | |
| `execute_reset()` | Executes full nuclear reset | |

### `append_note` vs `update_note`

Both exist. Agent reasons:
- `append_note` — adding new info, preserving old (default when learning something new)
- `update_note` — reorganizing or cleaning up stale content

No instruction about which to use. Agent decides from context.

### `list_pending_approvals` — why it's critical

Without this tool, when boss says "ok duyệt đi", Secretary has no way to know:
- Which approval they mean
- How many are pending
- What each one involves

With this tool, Secretary can naturally: list pending items → understand context → call `approve_task_change` or `approve_join` on the right one.

---

## Core Flows

### Join flow (LLM-native, no keywords)

```
User says "tôi muốn làm cộng tác ở công ty khác" (or any variation)
  Secretary sees active_sessions.join_pending = [] in context
  Secretary calls: list_available_workspaces()
  Secretary presents options naturally, asks which one + role
  User picks
  Secretary calls: request_join(target_boss_id, role, intro)
    → pending membership in SQLite
    → notification to target boss

Target boss sees notification. Says "cho vào" / "ok partner" / "từ chối"
  Secretary (boss context) sees active_sessions.approvals_pending in context
  Secretary calls: list_pending_approvals() if needed to clarify
  Secretary calls: approve_join(membership_id, role)
    → membership status → "active"
    → create_record in Lark People of TARGET workspace  ← bug fix
    → notify requester
```

### Task approval (LLM-native, no regex)

```
Member requests change → request_task_approval() → pending record in DB

Boss says "ok" / "duyệt" / "thôi giữ nguyên"
  Secretary sees approvals_pending in injected context
  If ambiguous → calls list_pending_approvals() to clarify
  Calls: approve_task_change(approval_id) or reject_task_change(approval_id)
```

### Nuclear reset (correct order)

```
execute_reset():
  0. Capture member_ids = SELECT chat_id FROM memberships WHERE boss_chat_id = X
  1. Notify all members workspace is being reset
  2. DELETE Lark Base entirely (delete the base, not just records)
  3. DELETE FROM notes WHERE boss_chat_id = X
  4. DELETE FROM reminders WHERE boss_chat_id = X
  5. DELETE FROM scheduled_reviews WHERE boss_chat_id = X
  6. DELETE FROM pending_approvals WHERE boss_chat_id = X
  7. DELETE FROM task_notifications WHERE boss_chat_id = X
  8. DELETE FROM messages WHERE chat_id IN (boss_id + member_ids)
  9. DELETE FROM people_map WHERE boss_chat_id = X
  10. UPDATE memberships SET status='workspace_reset' WHERE boss_chat_id = X
  11. DELETE FROM bosses WHERE chat_id = X
  12. Qdrant: delete_collection("messages_X"), delete_collection("tasks_X")
  13. Send visual separator to Telegram:
      "━━━━━━━━━━━━━━━━━━━━━━
             WORKSPACE RESET
        Dữ liệu cũ đã được xóa.
        Phiên mới bắt đầu từ đây.
      ━━━━━━━━━━━━━━━━━━━━━━"
```

Note: member_ids captured in step 0 BEFORE any deletion. Step 11 (delete bosses) is LAST.

### Cross-workspace task query

```
User: "tôi đang có task gì tới đây?"
Secretary sees: user has 2 workspaces in membership context
Secretary reasons: generic personal task query → should check all workspaces
Secretary calls: list_tasks(assignee="self", workspace_ids="all")
Tool returns: [{workspace: "Company A", tasks: [...]}, {workspace: "Company B", tasks: [...]}]
Secretary aggregates and responds naturally
```

---

## Data Model Changes

```sql
-- bosses
ALTER TABLE bosses ADD COLUMN language TEXT DEFAULT 'en';

-- memberships  
ALTER TABLE memberships ADD COLUMN language TEXT DEFAULT NULL;
-- NULL = inherit boss workspace language

-- sessions (new table)
CREATE TABLE IF NOT EXISTS sessions (
    user_id     INTEGER NOT NULL,
    key         TEXT NOT NULL,           -- e.g. "preferred_workspace"
    value       TEXT NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, key)
);
```

---

## Language Preference

**Resolution order for Secretary:** `memberships.language` → `bosses.language` → `'en'`

Each sender gets their own language. Boss and member can have different languages in the same workspace.

**Injection:** Single line in system prompt: `"Respond in: English"` (resolved from DB). No hardcoded language logic anywhere.

**Onboarding:** Language is asked explicitly after role selection. Saved to onboarding state dict → passed into `db.create_boss()` or `db.upsert_membership()` at completion.

---

## What Is NOT Changing

- Advisor Agent — no changes
- Scheduler — minor cleanup (last_notified_at timestamp)
- Qdrant setup — no changes
- Lark Base provisioning — no changes  
- Group chat handling — no changes
- Reminder flow — no changes
- Review schedule config — no changes
- Tests — skipped this cycle (real-world testing)

---

## Known Limitations

- Telegram chat history not deletable via API. Separator message is the workaround.
- `workspace_ids="all"` queries run N parallel Lark API calls — acceptable at demo scale.
- If Secretary picks wrong workspace, it detects via tool results and calls `switch_workspace()`. Costs 1 extra round, no data loss.
