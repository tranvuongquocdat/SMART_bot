# Tool Layer Redesign — AI Secretary

**Date:** 2026-04-16  
**Status:** Draft  
**Scope:** Full redesign of tool set, onboarding flow, Lark sync strategy, outbound DM logging, and scheduler proactive behavior.

---

## 1. Problem Statement

The current system (~42 tools) has three root issues that compound each other:

1. **Tool philosophy is wrong** — tools are narrow, single-purpose, and return minimal data. The agent must chain 3–5 tool calls to understand a situation before acting. This wastes tokens and creates rigid flows.
2. **Hardcoded flows** — `onboarding.py` and several tools contain state machines and `if/else` logic that force rigid sequences. Breaks easily in production, hard to extend.
3. **Missing capabilities** — simple but critical use cases (outbound DM log, cross-workspace queries, group↔personal context switching) are absent entirely.

**Goal:** Redesign the tool layer so the agent can reason flexibly from rich data, sequence actions naturally, and handle all real use cases without being constrained by tool design.

---

## 2. Design Principles

### 2.1 Descriptions drive behavior, not hardcode

Tool descriptions guide the agent on when and how to use each tool. No `if/else` flows, no state machines in orchestration logic. Example:

> `get_person` — *"Call before assigning a task. Return includes effort_score and active_task_count. If effort_score > 0.8, consider asking the boss to confirm before proceeding."*

The agent reads this and self-sequences. No code enforces the sequence.

### 2.2 Fat returns — read less, understand more

Every read tool returns all context the agent needs to reason, not just the requested field:

```
get_person("Bách") →
  name, role, type, workspace
  active_tasks: [{name, deadline, status, urgency_flag}]
  effort_score: 0.8
  last_dm_from_bot: "2026-04-15 14:30 — nhắc deadline logo"
  has_dmd_bot: true
```

The agent reads one tool result and already knows: Bách is near overloaded, was already reminded yesterday, likely doesn't need another push today.

### 2.3 Context-agnostic tools

Most tools work from both group chat and DM. `ctx` carries enough information to route correctly. Hard `is_group` guards are removed except for tools that are genuinely group-only (e.g., `manage_group` actions like kick/rename).

### 2.4 Workspace-aware by default

All tools that query people, tasks, or projects accept a `workspace_ids` param:
- `"current"` — default, active workspace
- `"all"` — all workspaces the user belongs to
- specific name — target a single workspace

When querying cross-workspace, every returned record is tagged with its `workspace` field. The agent reads context to disambiguate (e.g., "cộng tác" → prefer `type=partner` workspaces).

### 2.5 Lark is source of truth

All write operations follow this order:
1. Write to Lark (source of truth) — get `record_id`
2. Write to SQLite (local cache)
3. Embed to Qdrant async (search index)

If Lark fails → do not write SQLite → surface clear error: *"Không thể kết nối Lark, vui lòng thử lại."* Never claim success when Lark write failed.

---

## 3. Tool Set (~36 tools, 11 domains)

### 3.1 Tasks (5 tools)

| Tool | Key Params | Fat Return Additions |
|------|-----------|----------------------|
| `create_task` | name, assignees (list), deadline, priority, project, note, workspace_ids | assignee workload snapshot per assignee + DM notification status |
| `list_tasks` | assignee?, status?, project?, scope?, due_within_days?, workspace_ids | urgency_flag, days_until_deadline, overdue_flag, workspace tag per task |
| `update_task` | keyword, \*fields, workspace_ids | updated task + who was notified |
| `delete_task` | keyword, workspace_ids | — |
| `search_tasks` | query, workspace_ids | semantic ranked results with relevance reason + workspace tag |

**`list_tasks` default scope from group:** when called from a group context, defaults to tasks linked to that group's project — not all boss tasks.

**Literal enums — must match Lark field values exactly:**
- `status`: `"Mới"` | `"Đang làm"` | `"Hoàn thành"` | `"Huỷ"`
- `priority`: `"Cao"` | `"Trung bình"` | `"Thấp"`

Any value outside these enums will cause Lark sync to silently fail or create an invalid record. Tool descriptions must state these explicitly. Agent must never invent status strings.

**`update_task` reassign:** when `assignee` field changes, the new assignee automatically receives a DM notification (same as `create_task` flow). Old assignee is not notified unless boss explicitly requests it.

**`update_task` by member/partner:** internally creates an approval request instead of applying directly. This is tool-internal behavior, not orchestration logic. Description states: *"If sender_type is member/partner, change is queued for boss approval automatically."*

**`create_task` with multiple assignees:** sends DM notification to each assignee individually, logs each DM in `outbound_messages`.

**Description hint:** *"Before create_task, call get_person to check effort_score. If > 0.8, surface a warning and ask boss to confirm."*

---

### 3.2 People (6 tools)

| Tool | Key Params | Fat Return Additions |
|------|-----------|----------------------|
| `add_person` | name, role, type, contact?, workspace_ids | person record + Lark sync confirmation |
| `get_person` | name, workspace_ids | info + active_tasks + effort_score + last_dm_from_bot + has_dmd_bot + workspace tag |
| `list_people` | type?, workspace_ids | lightweight: name, role, type, task_count, workspace |
| `update_person` | name, \*fields, workspace_ids | updated + Lark synced |
| `delete_person` | name, workspace_ids | confirmation (risky — description warns to confirm with boss first) |
| `check_team_engagement` | workspace_ids | per member: has_dmd_bot, last_interaction, task_count, overload_flag, workspace |

**`get_person` cross-workspace disambiguation:** if multiple people share the same name across workspaces, return all matches tagged by workspace. Agent reasons from context which Bách is relevant (e.g., currently in workspace A's group → prioritize workspace A's Bách).

**`add_person` and `update_person`** sync to Lark People table — currently missing, added in redesign.

**Literal enums — defined at provisioning, must be used exactly:**
- `type`: `"Nhân viên"` | `"Cộng tác viên"` | `"Đối tác"`

**`check_team_engagement` description:** *"Use when asked 'ai chưa nhắn bot', 'ai đang bận', or before broadcast to know who may not receive messages."*

**`get_workload` (moved to Summary domain):** aggregates tasks across all workspaces the person belongs to for accurate total effort.

---

### 3.3 Projects (5 tools)

| Tool | Key Params | Fat Return Additions |
|------|-----------|----------------------|
| `create_project` | name, description, deadline, members?, workspace_ids | project + Lark record_id |
| `get_project` | name, workspace_ids | **fat**: project info + all tasks + progress % + team + recent activity + notes |
| `list_projects` | status?, workspace_ids | list + task_count + deadline + workspace tag |
| `update_project` | name, \*fields, workspace_ids | updated + Lark synced |
| `delete_project` | name, workspace_ids | confirmation + Lark deleted |

All 5 tools sync Lark on every write. Currently `create/update/delete_project` only write SQLite — this is fixed.

**Literal enums — must match Lark field values exactly:**
- `status`: `"Chưa bắt đầu"` | `"Đang thực hiện"` | `"Hoàn thành"` | `"Tạm dừng"` | `"Huỷ"`

---

### 3.4 Communication (3 tools) — NEW

| Tool | Key Params | Return |
|------|-----------|--------|
| `send_dm` | to, content, context?, workspace_ids | confirmation + logged to `outbound_messages` |
| `broadcast` | message, targets?, workspace_ids | sent_count + who received / who missing Chat ID |
| `get_communication_log` | person?, since?, type?, workspace_ids | full timeline: DMs sent, task notifications, reminders — tagged by workspace |

**`send_dm` disambiguation from group:** when called from group context, first searches within the group's workspace before searching other workspaces.

**`broadcast` targets:** valid values — `"all_members"`, `"all_partners"`, `"all"`, or list of specific names. When called from DM (no group context), sends individual DMs to workspace members, does not require a group.

**`send_dm` no Chat ID:** returns clear error: *"[name] chưa DM bot, chưa có Chat ID — không thể nhắn tin trực tiếp."*

**`get_communication_log` description:** *"Call before asking 'đã nhắn X chưa' or 'đã push deadline chưa'. Returns full timeline of all bot-initiated contact with that person."*

**`get_communication_log` note:** tracks from redesign deployment date — no historical backfill from previous version.

**`outbound_messages` table:**
```sql
CREATE TABLE outbound_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_chat_id  INTEGER NOT NULL,
    workspace_id  TEXT,
    to_chat_id    INTEGER NOT NULL,
    to_name       TEXT,
    content       TEXT NOT NULL,
    trigger_type  TEXT,  -- "manual" | "task_assigned" | "deadline_push" | "reminder" | "scheduler"
    task_id       TEXT,
    project       TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Every bot-initiated DM inserts a row: `send_dm` tool, `create_task` notification, scheduler deadline push, `send_reminder`.

---

### 3.5 Reminders (4 tools)

| Tool | Key Params |
|------|-----------|
| `create_reminder` | content, time, target?, project?, task_keyword?, workspace_ids |
| `list_reminders` | target?, status?, workspace_ids |
| `update_reminder` | id, \*fields |
| `delete_reminder` | id |

**`create_reminder` target disambiguation:** if `target` is a person name and multiple people match across workspaces, apply same disambiguation logic as `get_person` — use workspace context, return ambiguity error if still unclear.

**`create_reminder` with `project`:** reminder is contextually associated with that project. When triggered by scheduler, agent includes project context in the reminder message.

**`create_reminder` with `task_keyword`:** optional — links reminder to a specific task by keyword search. When scheduler triggers this reminder, the agent fetches the latest task status and includes it in the reminder message (e.g., "Nhắc: task logo hiện đang ở trạng thái Đang làm, deadline còn 2h"). `task_keyword` and `project` are independent — both, either, or neither can be set.

---

### 3.6 Notes (2 tools)

| Tool | Key Params |
|------|-----------|
| `get_note` | type, ref?, workspace_ids |
| `update_note` | type, content, ref?, mode, workspace_ids |

**`type` values:** `"personal"` \| `"group"` \| `"project"` — `"project"` is new.

**`mode` values:** `"overwrite"` \| `"append"`.

**`get_note(type="group")` from DM:** requires explicit `ref=group_chat_id`. If `ref` not provided and not in group context, agent must ask which group.

**`update_note(type="group")` from DM:** same requirement as above.

---

### 3.7 Summary & Workload (3 tools)

| Tool | Key Params | Return |
|------|-----------|--------|
| `get_summary` | period, scope?, workspace_ids | tasks done/pending/overdue, aggregated across requested workspaces |
| `get_workload` | person?, workspace_ids | effort score aggregated cross-workspace + task list by priority + deadline pressure |
| `get_project_report` | project, workspace_ids | progress %, tasks by status, who's blocking, upcoming deadlines — LLM-generated narrative |

**`get_workload` cross-workspace aggregation:** when `workspace_ids="all"`, fetches tasks from all workspaces the person belongs to and computes a combined effort score. This prevents the situation where each workspace sees 5/8 tasks but total is 8.

**`get_summary` from group:** defaults to summarizing the group's linked project and team, not boss's full personal summary.

**`get_summary(scope="group")` from DM:** requires explicit `workspace_ids` + a group reference, same constraint as `get_note(type="group")` from DM. Agent must ask which group if not specified.

---

### 3.8 Workspace & Access (4 tools)

| Tool | Key Params |
|------|-----------|
| `list_workspaces` | — |
| `request_join` | workspace |
| `manage_join` | requester, action | 
| `switch_workspace` | workspace |

**`manage_join` approve → Lark sync:** when approving a join request, the new member is inserted into the target workspace's Lark People table. This fixes the current bug where joining a workspace does not add the person to that workspace's People table in Lark.

---

### 3.9 Approvals (2 tools)

| Tool | Key Params |
|------|-----------|
| `list_approvals` | — |
| `manage_approval` | id, action |

**`manage_approval` notify-back to group:** when an approval was created from a group context (payload has `group_chat_id`), approval result is broadcast back to that group. This behavior is preserved from current implementation.

---

### 3.10 Utilities (4 tools)

| Tool | Key Params |
|------|-----------|
| `search_history` | query, scope?, workspace_ids |
| `search_notes` | query, type?, workspace_ids |
| `save_idea` | content, category?, workspace_ids |
| `web_search` | query |
| `escalate_to_advisor` | reason |

**`search_history` cross-context:** currently searches only current `chat_id` context. In redesign, `scope="all"` searches across all chat_ids (DM + groups) belonging to the boss's workspace. Qdrant queries are filtered by `boss_chat_id` rather than specific `chat_id` when scope is all.

**`search_notes` — new tool:** semantic search across notes and ideas. `type` filters by `"personal"` | `"group"` | `"project"` | `"idea"` | `"all"` (default). Uses Qdrant — notes and ideas are embedded and upserted on write. Returns ranked matches with `type`, `ref` (group/project name if applicable), and `snippet`.

---

### 3.11 Admin (2 tools)

| Tool | Key Params |
|------|-----------|
| `manage_group` | action, \*params |
| `reset_workspace` | confirmed |

**`manage_group`** is the only tool that remains group-context-required for actions like kick/rename. `broadcast` is separated out (moved to Communication domain) so it works from DM too.

**`reset_workspace(confirmed=True)`** — no state machine. Agent asks user to confirm conversationally, then calls tool once with `confirmed=True`. Single tool call, no multi-step session tracking.

---

## 4. Onboarding Redesign

### 4.1 Current problem

`onboarding.py` is a hardcoded state machine (dict of steps). Forces yes/no answers, breaks on unexpected input, cannot recover gracefully.

### 4.2 Agent-driven onboarding

Replace state machine with an **onboarding note template** stored as a `notes` record (`type="onboarding"`, `ref_id=str(chat_id)`) in SQLite when a new user is detected:

```
onboarding_status: incomplete
collected:
  name: null
  company: null
  language: null
  lark_base_token: null
  lark_tables: {people: null, tasks: null, projects: null, ideas: null, reminders: null}
  first_team_member: null
missing: [name, company, language, lark_base_token, lark_tables]
```

The agent reads the onboarding note, determines what's missing, and asks conversationally — one natural question at a time. No forced yes/no. When `missing` is empty, the agent calls Lark provisioning and marks `onboarding_status: complete`.

**Language:** captured during onboarding, stored in boss record. Agent detects preferred language from conversation context (LLM-driven, not hardcoded). If boss wants to change language later, they say so naturally — no `set_language` tool needed.

### 4.3 Group onboarding

Same pattern — group note template tracks: `workspace linked`, `project linked`, `members introduced`. Agent checks template, asks what's missing in natural conversation flow.

---

## 5. Lark Sync Audit

### 5.1 Current sync status

| Operation | Before redesign | After redesign |
|-----------|----------------|----------------|
| create/update/delete task | ✅ Lark synced | ✅ unchanged |
| create/update/delete project | ❌ SQLite only | ✅ Lark first |
| add/update/delete person | ❌ SQLite only | ✅ Lark first |
| create/update/delete reminder | ⚠️ Lark→SQLite only (scheduler) | ✅ bidirectional |
| notes | ❌ SQLite only | ✅ Lark first (requires provisioning a `Notes` table in Lark Base during workspace setup — new field in `lark_table_notes` on `bosses` record) |
| ideas | ✅ Lark synced | ✅ unchanged |

### 5.2 Write pattern (all tools)

```python
# 1. Write Lark (source of truth)
record = await lark.create_record(token, table, fields)
# 2. Write SQLite (local cache)
await db.upsert_X(record["record_id"], fields)
# 3. Embed Qdrant (async, non-blocking)
asyncio.create_task(embed_and_upsert(...))
```

If step 1 fails → raise error, do not proceed. Surface: *"Không thể kết nối Lark, vui lòng thử lại."*

---

## 6. Outbound DM Logging

All bot-initiated outbound DMs are logged to `outbound_messages` table (schema in Section 3.4).

Logging points:
- `send_dm` tool call → `trigger_type="manual"`
- `create_task` assignee notification → `trigger_type="task_assigned"`
- Scheduler `_check_deadline_push` → `trigger_type="deadline_push"`
- Scheduler `_after_deadline_check` → `trigger_type="deadline_push"`
- `send_reminder` → `trigger_type="reminder"`

`get_communication_log` queries this table plus `task_notifications` table for a unified timeline.

---

## 7. Scheduler Redesign

### 7.1 Job table

| Job | Interval | Notes |
|-----|----------|-------|
| `_run_dynamic_reviews` | 1 min | Morning brief, evening summary, custom, group brief |
| `_check_deadline_push` | 30 min | 24h/2h push — DM + log outbound |
| `_after_deadline_check` | 30 min | **NEW** — overdue tasks: DM assignee + report to boss |
| `_check_reminders` | 1 min | Due reminders via LLM |
| `_sync_lark_to_sqlite` | 30 sec | Lark → SQLite sync |

**Remove:** `_check_deadlines` (hardcoded 9h30 cron) — covered by `_run_dynamic_reviews` with `morning_brief`.

### 7.2 `_after_deadline_check` (new)

```
Every 30 minutes:
1. Find tasks: deadline passed + status not in (Hoàn thành, Done, Huỷ, Cancelled)
2. Check task_notifications.notified_overdue — skip if already notified
3. For each unnotified overdue task:
   a. If assignee has Chat ID → DM assignee (LLM-generated), log to outbound_messages
   b. If assignee has no Chat ID → skip DM, note "chưa có tài khoản" in boss report
   c. Mark task_notifications.notified_overdue = 1
4. Aggregate report to boss: "Task X của Bách đã quá hạn 2h, em đã nhắc Bách lúc 17:00"
```

**`task_notifications` table additions:**
```sql
ALTER TABLE task_notifications ADD COLUMN notified_overdue INTEGER DEFAULT 0;
ALTER TABLE task_notifications ADD COLUMN notified_overdue_at TIMESTAMP;
```

### 7.3 Scheduler group context fix

When `_run_dynamic_reviews` sends to a `group_chat_id`, it must build group context (group note, linked project, recent participants) before generating the brief. Currently creates a personal `ChatContext` which lacks group context — this produces generic, irrelevant group briefs.

Fix: when `target_chat_id != owner_id` (i.e., sending to a group), call `build_group_context(group_chat_id, boss_chat_id)` and inject into the LLM prompt.

---

## 8. Multi-Workspace & Group/Personal — Consistency Rules

### 8.1 Standard params

Every tool that queries or writes people/tasks/projects/reminders/notes includes:
- `workspace_ids: str = "current"` — values: `"current"` \| `"all"` \| workspace name

### 8.2 Cross-workspace returns

When `workspace_ids != "current"`, every returned record includes a `workspace` tag. The agent uses this to reason about which result is relevant without needing additional tool calls.

### 8.3 Disambiguation rule

When multiple people share the same name across workspaces:
1. If in group context → prioritize the workspace that group belongs to
2. If in DM → prioritize workspace stored as `active_workspace_id` in `people_map` for this user (set by `switch_workspace`, defaults to their own workspace if boss)
3. If still ambiguous → return all matches with workspace tags, let agent ask clarifying question

This rule applies to: `get_person`, `send_dm`, `create_reminder(target)`, `update_task(assignee)`, `create_task(assignees)`.

### 8.4 `search_history` cross-context

`scope="current_chat"` (default) — searches current chat_id only.  
`scope="all"` — searches all chat_ids belonging to boss's workspace (DMs + all linked groups).

Qdrant query changes: filter by `boss_chat_id` instead of specific `chat_id` when `scope="all"`.

---

## 9. Removed / Consolidated

| Removed | Replaced by |
|---------|-------------|
| `broadcast_to_group` | `broadcast` (Communication domain, works from DM too) |
| `update_group_note` | `update_note(type="group", ref=group_id)` |
| `summarize_group_conversation` | `get_summary(scope="group")` |
| 3-step reset state machine | `reset_workspace(confirmed=True)` |
| `onboarding.py` state machine | Agent-driven onboarding note |
| `group_onboarding.py` state machine | Agent-driven group onboarding note |
| `set_language` tool | Captured in onboarding, LLM-detected thereafter |
| `approve_task_change` + `reject_task_change` | `manage_approval(id, action)` |
| `approve_join` + `reject_join` | `manage_join(requester, action)` |

---

## 10. Error Handling & Agent Recovery

### 10.1 Current problem

When a tool raises an exception (e.g., Lark API timeout, record not found), the exception propagates up through `asyncio.gather` to the outer `try/except` in `handle_message`, which sends a generic "Xin lỗi, có lỗi xảy ra" to the user. The agent never receives the error — it cannot retry, recover, or give a meaningful response.

### 10.2 Fix: error strings, not exceptions

`execute_tool` wraps all tool calls and converts exceptions to structured error strings returned as tool results:

```python
async def execute_tool(name: str, args: str, ctx: ChatContext) -> str:
    try:
        return await _dispatch(name, args, ctx)
    except LarkAPIError as e:
        return f"[TOOL_ERROR:lark] {e} — Lark không phản hồi. Thử lại hoặc báo người dùng."
    except RecordNotFoundError as e:
        return f"[TOOL_ERROR:not_found] {e}"
    except Exception as e:
        return f"[TOOL_ERROR:unknown] {name} thất bại: {e}"
```

The agent receives the error string as a normal tool result and can reason:
- Lark error → retry once, if still fails → tell boss clearly
- Not found → ask for clarification (different name? different workspace?)
- Unknown → surface the error message, do not fabricate a success response

### 10.3 System prompt guidance

Add to the agent system prompt:

> *"If a tool returns [TOOL_ERROR], do not claim the action succeeded. Read the error type: lark errors may be transient (retry once), not_found errors need clarification from the user, unknown errors should be surfaced as-is. Never silently ignore a tool error."*

---

## 11. Lark Sync-Back (Lark → SQLite)

### 11.1 Enum values from provisioning

Lark Base is created fresh during workspace setup — the system controls all field definitions. Enum values in this spec are **defined at provisioning time**, not confirmed against pre-existing data.

Canonical enum values (set during Lark Base table creation):

| Table | Field | Values |
|-------|-------|--------|
| Tasks | Status | `Mới` \| `Đang làm` \| `Hoàn thành` \| `Huỷ` |
| Tasks | Priority | `Cao` \| `Trung bình` \| `Thấp` |
| Projects | Status | `Chưa bắt đầu` \| `Đang thực hiện` \| `Hoàn thành` \| `Tạm dừng` \| `Huỷ` |
| People | Type | `Nhân viên` \| `Cộng tác viên` \| `Đối tác` |

These values must be hardcoded in tool descriptions and in Lark table field options — they are the single source of truth.

### 11.2 Sync-back scheduler job

`_sync_lark_to_sqlite` currently only syncs Reminders. Extend to all tables so manual edits in Lark UI propagate back to SQLite:

| Table | Sync direction | Interval |
|-------|---------------|----------|
| Reminders | Lark → SQLite | 30s (existing) |
| Tasks | Lark → SQLite | 5 min (new) |
| Projects | Lark → SQLite | 5 min (new) |
| People | Lark → SQLite | 5 min (new) |

Sync logic: fetch all Lark records, upsert into SQLite by `record_id`. If a record exists in SQLite but not Lark (deleted in Lark UI) → delete from SQLite and Qdrant.

---

## 12. Open Questions

1. **Lark People table for project members** — when `create_project(members=[...])`, does this add members to Lark People table if not already there? Clarify: only add to project association, not automatically create new People records.

2. **`save_idea` workspace** — ideas currently write to Lark Ideas table of boss's primary workspace. Cross-workspace idea creation not a priority for now — default to current workspace.

3. **Qdrant collection naming for cross-workspace** — currently `tasks_{boss_chat_id}`. For cross-workspace search, each workspace's boss_chat_id needs its own collection. The `search_tasks(workspace_ids="all")` needs to fan out to multiple collections. Implementation detail to resolve during development.

4. **`outbound_messages` historical data** — table starts empty at deployment. No backfill from previous notification logs. Document this limitation clearly to users on upgrade.
