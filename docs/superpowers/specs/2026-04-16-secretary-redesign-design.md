# AI Secretary — Redesign Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Scope:** Architecture cleanup, join flow fix, nuclear reset, multi-workspace routing, language preference

---

## Context & Goals

The current system is a Telegram-based AI secretary bot with 2 agents (Secretary + Advisor), SQLite for internal state, Lark Base for visual data, and Qdrant for semantic search.

**Problems to fix:**
1. Join flow bug — when a boss of workspace A joins workspace B as partner, they are not written into Lark People table of workspace B
2. Hardcoded if/else patterns in `agent.py` (keyword lists, regex approval matching, reset trigger phrases) make the flow feel unnatural
3. Reset only clears Lark records, not SQLite or Qdrant
4. No multi-workspace context routing — context always defaults to the user's own workspace
5. No language preference — always responds in Vietnamese (hardcoded in prompts)
6. No cross-workspace person lookup — tools only query the active workspace

**Demo scenario:** A user who is a member of Company A and a partner of Company B. They interact with both workspaces via a single bot. "Bách" may exist in both workspaces as different people.

---

## Architecture

### Overview

```
Telegram message
        │
        ▼
  [router.py]  ← lightweight LLM call
  Context: sender memberships + active sessions + last 5 messages
  Output:
    - workspace_id: which workspace to activate
    - mode: "onboarding" | "admin" | "work" | "strategic"
    - admin_type: "join" | "join_approval" | "task_approval" | "reset" | null
        │
        ├─ mode=onboarding → onboarding.py (state machine, new users only)
        ├─ mode=admin → secretary.py (correct workspace context pre-loaded)
        ├─ mode=work → secretary.py (correct workspace context pre-loaded)
        └─ mode=strategic → secretary.py → escalates to advisor.py
```

### Router design

Router is a focused LLM call with a small system prompt (~200 tokens). It receives:
- Sender's workspace memberships (name + role per workspace)
- Any active sessions (join pending, reset pending, task approval pending)
- Last 5 messages for follow-up context
- Current message

Router returns structured JSON:
```json
{
  "workspace_id": "<boss_chat_id or null>",
  "mode": "work",
  "admin_type": null,
  "ambiguous_person": false
}
```

If `workspace_id` is null (cannot determine from context), Secretary defaults to the user's primary workspace — defined as: their own boss workspace if they have one, otherwise the first active membership. Secretary can call `switch_workspace()` mid-conversation if it detects a mismatch.

### Files changed

| File | Change |
|---|---|
| `router.py` | **New** — lightweight classifier, ~100 lines |
| `agent.py` → `secretary.py` | Remove all pre-checks (keyword lists, regex, reset triggers). Pure tool loop only. |
| `onboarding.py` | Add language selection step. Minor changes only. |
| `src/tools/join.py` | **New** — join flow as stateful tools |
| `src/tools/reset.py` | Upgrade to nuclear reset |
| `src/tools/__init__.py` | Register new tools, add `workspace_ids` param to relevant tools |
| `src/db.py` | Add `language` field to `bosses` and `memberships` tables |
| `src/context.py` | Support multi-workspace context resolution |

---

## Core Flows

### Flow 1: Multi-workspace context routing

```
User = member of Company A + partner of Company B
Message: "deadline của dự án web bên công ty B còn bao lâu?"

Router:
  - Sees memberships: [A-member, B-partner]
  - Detects "công ty B" reference → workspace_id = B's boss_id
  → Secretary runs with Company B's Lark Base context

Follow-up message: "còn task nào của tôi chưa xong?"
Router:
  - Last 5 messages context is about Company B
  - No explicit workspace mentioned → keep workspace B
  → Secretary continues in Company B context
```

### Flow 2: Cross-workspace person lookup

Tools that deal with people or tasks accept an optional `workspace_ids` parameter:

```python
search_person(name="Bách", workspace_ids="all")
# Returns:
[
  {"workspace": "Company A", "name": "Bách", "role": "Designer", "tasks": 3},
  {"workspace": "Company B", "name": "Bách", "role": "Developer", "tasks": 1}
]
```

The Secretary agent reasons about the result:
- 1 result → answer directly
- Multiple results, context is clear → pick the right one
- Multiple results, ambiguous → ask user naturally
- 0 results → say so

No hardcoded case handling in Python. The LLM reasons from the structured data.

Tools updated to support `workspace_ids`:
- `search_person(name, workspace_ids="current")`
- `list_tasks(assignee, workspace_ids="current")`
- `check_effort(assignee, workspace_ids="current")`

Default is `"current"` — backward compatible. Pass `"all"` or a list of boss_ids for cross-workspace.

### Flow 3: Join flow (cross-workspace, LLM-native)

Replaces the current state machine in `onboarding.py` join path and the keyword-check in `agent.py`.

```
User (already onboarded as boss of A) says "tôi muốn làm cộng tác ở công ty khác"
  → Router: mode=admin, type=join
  → Secretary calls: list_available_workspaces()
    → returns list of workspaces the user is NOT yet a member of
  → Secretary presents list naturally, asks which one
  → User picks
  → Secretary calls: request_join(target_boss_id, role, intro_text)
    → creates pending membership in SQLite (status="pending")
    → sends notification to target boss

Target boss sees: "Đạt (boss of Company A) wants to join as partner. [intro]. Reply to approve or reject."
  → Boss replies naturally: "cho vào đi" / "ok partner" / "từ chối"
  → Router: sees pending join request in active sessions → mode=admin, type=join_approval
  → Secretary calls: approve_join(membership_id, role) OR reject_join(membership_id)
    → approve_join:
        1. Update membership status → "active" in SQLite
        2. create_record in Lark People table of TARGET workspace ← [BUG FIX]
        3. Notify the requester
    → reject_join:
        1. Update membership status → "rejected"
        2. Notify the requester
```

### Flow 4: Task approval (LLM-native)

Replaces regex pattern `(approve|reject)\s+(\d+)` in `agent.py`.

```
Member: "em done task thiết kế logo rồi anh"
  → Secretary (member context): minor update → apply directly, notify boss

Member: "anh ơi em muốn chuyển task logo sang tuần sau được không"
  → Secretary: significant change → calls request_task_approval(task_id, changes, reason)
  → Notifies boss: "Bách wants to push task X deadline to next week. Reason: [reason]."

Boss: "ừ được" / "ok chuyển đi" / "thôi giữ nguyên đi"
  → Router: sees pending task approval → mode=admin, type=task_approval
  → Secretary: calls approve_task_change(approval_id) OR reject_task_change(approval_id)
  → Applies change or reverts, notifies member
```

### Flow 5: Nuclear reset

```
User: "reset workspace" / "xóa hết đi" / any reset intent
  → Router: mode=admin, type=reset
  → Secretary: calls initiate_reset()
    → Returns: "Type your company name in UPPERCASE to confirm"

User types: "COMPANY NAME"
  → Secretary: calls confirm_reset_step1(input)
    → Matches? → Returns: "Type 'tôi chắc chắn' to proceed"
    → No match? → Cancels

User types: "tôi chắc chắn"
  → Secretary: calls execute_reset()
    1. Send visual separator message to Telegram chat:
       "━━━━━━━━━━━━━━━━━━━━━━\n       WORKSPACE RESET\n  Dữ liệu cũ đã được xóa.\n  Phiên mới bắt đầu từ đây.\n━━━━━━━━━━━━━━━━━━━━━━"
    2. Notify all active members/partners that workspace is being reset
    3. DELETE Lark Base entirely (not just records — delete the base)
    4. DELETE FROM bosses WHERE chat_id = X
    5. DELETE FROM memberships WHERE boss_chat_id = X
    6. DELETE FROM people_map WHERE boss_chat_id = X  
    7. DELETE FROM messages WHERE chat_id IN (boss + all members' chat_ids)
    8. DELETE FROM reminders WHERE boss_chat_id = X
    9. DELETE FROM notes WHERE boss_chat_id = X
    10. DELETE FROM scheduled_reviews WHERE boss_chat_id = X
    11. DELETE FROM pending_approvals WHERE boss_chat_id = X
    12. DELETE FROM task_notifications WHERE boss_chat_id = X
    13. Qdrant: delete_collection("messages_X"), delete_collection("tasks_X")
    14. Update memberships of members/partners: set status="workspace_reset" for their link to this workspace

After reset: user messages → context.resolve() returns None → onboarding runs again from scratch.

Note: Telegram chat history is NOT deletable via API (48h limit, bot messages only).
The separator message serves as the visual boundary between old and new sessions.
```

### Flow 6: Deadline push (unchanged, cleanup only)

Scheduler remains. Cleanup:
- Replace complex `task_notifications` logic with simple `last_notified_at` timestamp on notification record
- Assignee name → people_map lookup → Telegram chat_id → send message

---

## Data Model Changes

### `bosses` table
```sql
ALTER TABLE bosses ADD COLUMN language TEXT DEFAULT 'en';
```

### `memberships` table
```sql
ALTER TABLE memberships ADD COLUMN language TEXT DEFAULT NULL;
-- NULL means: use boss workspace language as default
```

### No other schema changes required.

---

## New Tools

| Tool | Description |
|---|---|
| `list_available_workspaces()` | Returns workspaces the sender can join (not already a member) |
| `request_join(target_boss_id, role, intro)` | Creates pending membership, notifies target boss |
| `approve_join(membership_id, role)` | Approves join, writes to Lark People of target workspace |
| `reject_join(membership_id)` | Rejects join, notifies requester |
| `approve_task_change(approval_id)` | Applies pending task change, notifies member |
| `reject_task_change(approval_id)` | Rejects pending task change, notifies member |
| `initiate_reset()` | Starts reset flow, returns step-1 confirmation prompt |
| `confirm_reset_step1(input)` | Validates company name; if match → returns step-2 prompt; else cancels |
| `execute_reset()` | Executes nuclear reset after 2-step confirmation |
| `set_language(language_code)` | Persists language preference for current user |
| `switch_workspace(boss_id)` | Switches active workspace context; persisted for 30 min in session table |
| `append_note(note_type, ref_id, content)` | Appends new information to an existing note without overwriting. Prefer over update_note to preserve knowledge. |

### `append_note` vs `update_note`

Both tools exist. Agent chooses:
- `append_note` — when adding new information to what's already known (default choice)
- `update_note` — when reorganizing or cleaning up a note that's grown stale

No instruction in the prompt about which to use when — the agent reasons based on context.

### `switch_workspace` session persistence

When called, `switch_workspace(boss_id)` writes `preferred_workspace_id` to a SQLite `sessions` table with a 30-minute TTL. Router reads this before classifying — if a preference is active, it uses it directly without routing logic. Preference expires after 30 min of inactivity or when user explicitly references a different workspace.

### Cross-workspace permission model

When a user operates in workspace B (as partner/member), their permissions are governed by their `person_type` in workspace B's membership — not their role in their home workspace. Boss-of-A operating as partner-of-B has partner-level permissions in B. This is enforced in code, not prompt.

### Tools updated (add `workspace_ids` param)

| Tool | New param | Default |
|---|---|---|
| `search_person(name)` | `workspace_ids` | `"current"` |
| `list_tasks(...)` | `workspace_ids` | `"current"` |
| `check_effort(assignee)` | `workspace_ids` | `"current"` |

Pass `"all"` to query across all workspaces the user belongs to. Returns results with workspace labels — agent reasons about disambiguation naturally.

---

## Language Preference

### Storage
- `bosses.language` — workspace default language (set during boss onboarding)
- `memberships.language` — per-member override (set during their onboarding or via `set_language`)

### Injection into Secretary system prompt
```
Respond in: English (user preference).
If the user writes in a different language or explicitly requests a language change,
match them immediately and call set_language() to persist the preference.
```
No hardcoded language rules. LLM detects and adapts.

### Onboarding language step (after role selection)
```
Bot: "What language do you prefer?"
     1. English
     2. Tiếng Việt
     3. Other — just reply in your language and I'll match you

User picks → language saved → rest of onboarding in that language
```
Option 3 fallback: LLM detects language from the reply and saves it.

---

## Secretary Agent — Cleaned Up Structure

`secretary.py` (renamed from `agent.py`) contains only:
1. Resolve workspace context (from router output)
2. Build system prompt (inject: language, personal note, people summary, time, sender info)
3. Gather context: last 15 messages + 8 RAG results
4. Tool loop (max 10 rounds)
5. Send reply
6. Persist to SQLite + Qdrant

No if/else blocks for join keywords, reset triggers, or approval regex. Zero business logic outside the tool loop.

### System prompt philosophy — principle-based, not procedure-based

The system prompt does NOT list step-by-step procedures. It gives the agent values and context, then trusts the model to reason.

**What to avoid:**
> ❌ "Before responding about any person, always call get_note() first, then list_tasks(), then check_effort()"

**What to write instead:**
> ✅ "You genuinely know this team. You care about their wellbeing, not just their output. When making decisions that affect someone — assigning tasks, setting deadlines, sending messages — take a moment to understand their current situation before acting."

> ✅ "You remember everything the boss has told you. If they've shared preferences, habits, or standing instructions in the past, those live in the personal note. Draw on them naturally — don't ask the boss to repeat themselves."

> ✅ "You use your tools to understand context before acting, not just to execute commands."

The agent is smart enough to decide: does understanding this situation require checking notes? Checking workload? Both? Neither? It makes that call based on the principle, not a rigid checklist.

**Tool descriptions follow the same philosophy.** Each tool description says *when it's useful*, not *when it's mandatory*:
- `get_note`: "Use when you want to recall what you know about a person, project, or group — their history, preferences, context."
- `append_note`: "Use when you learn something worth remembering — a preference, a concern, a piece of context. Prefer this over update_note to preserve existing knowledge."
- `check_effort`: "Useful before assigning tasks — helps you understand if someone is already stretched."

This approach maximizes agent reasoning freedom. The model decides the right tool sequence for each situation rather than following a script.

---

## What Is NOT Changing

- Advisor Agent — no changes
- Scheduler — minor cleanup only  
- Qdrant setup — no changes
- Lark Base provisioning — no changes
- Group chat handling — no changes
- Reminder flow — no changes
- Review schedule config — no changes
- Tests — skipped this build cycle (real-world testing instead)

---

## Open Questions / Known Limitations

- Telegram chat history cannot be deleted (API limitation). The visual separator message is the workaround.
- Cross-workspace `workspace_ids="all"` queries will be slower (N parallel Lark API calls). Acceptable for demo scale.
- If router misclassifies workspace, Secretary will detect via tool results and can call `switch_workspace()` — costs 1 extra round but no data loss.
- Session table for workspace preference needs to be added to SQLite schema (minimal: `user_id`, `preferred_workspace_id`, `expires_at`).
