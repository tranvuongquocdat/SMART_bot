# Drop Onboard-Gate — Stub Person Everywhere

**Date:** 2026-05-18
**Status:** Design approved
**Scope:** Small — prompt + tool descriptions only

## Problem

Boss in a group says *"giao task design banner cho Tân, deadline thứ 6"*. Tân has never DM'd the bot, so there's no `Person.chat_id`. Today the LLM refuses or routes around it because:

- `create_task` / `create_reminder` tool descriptions push *"dùng đúng tên trong danh sách nhân sự"* and *"phải có Chat ID"*.
- No system-prompt rule teaches the secretary to create a stub Person on the fly.

Boss expects the bot to record the task, announce it in the group, and remind there — Tân can be linked later when he first messages the bot.

## Goal

Remove every onboard-gate that blocks actions for people who haven't onboarded. A `Person` row is the source of truth — `chat_id` is optional. Stubs (no chat_id) appear in workload, lists, task assignment, reminder targeting, etc. exactly like fully-onboarded people; the only difference is the bot can't DM them, so messages route through the source group or the boss.

## Non-goals

- Refactor `services/`, `db.py`, repos, or Lark schema.
- Add new tools or new code paths.
- Change channel layer or onboarding flow itself.
- Auto-link stub → real Person at first DM (already handled by `membership_service.activate()`; verify but don't redesign).

## Architecture

Single change point: secretary system prompt. One rule block teaches the LLM the unified flow. Tool descriptions get small fixes so they don't contradict the new rule.

```
boss command (any action with a person name)
       ↓
[LLM] check existence — list_people / get_people fuzzy match
       ↓
   exact hit → use it
   multiple hits → CONFIRM which one, then use
   fuzzy hit → CONFIRM "ý anh là X?", then use OR create new
   no hit → create stub via add_people(name=..., no chat_id)
       ↓
[LLM] continue with original action (create_task / create_reminder / …)
       ↓
service layer — already correct: silent DM-skip + fallback fire chain
```

The same rule covers two creation paths:

1. **Bulk add upfront** — *"team gồm A, B, C, D"* → LLM calls `add_people` once per name.
2. **Auto-add on assignment** — *"giao cho Tân"* (Tân unknown) → fuzzy → confirm → add_people → create_task.

Both use the same tool, the same service code path, and the same DB row shape.

## Components touched

| File | Change | Size |
|---|---|---|
| `src/agent/secretary_agent.py` | Add prompt block "Người chưa onboard" with the unified flow + 2 disambiguation rules | ~15-20 lines of prompt |
| `src/agent/tool_definitions.py` | Strip contradicting hints from descriptions | ~5 small edits |
| `tests/unit/` | 5 new unit tests (listed below) | New files |

### Prompt block (to add)

Insert in `secretary_agent.py` system prompt, near the section that explains task / reminder tools. Roughly:

> **Quy tắc: người chưa onboard.**
> Trong hệ thống một Person không nhất thiết phải có Chat ID — người chưa từng DM bot vẫn được lưu như Person bình thường, chỉ là không DM được.
>
> Trước khi giao task / nhắc / cập nhật cho ai đó:
> 1. `list_people` hoặc `get_people` để tra cứu.
> 2. Nếu trùng nhiều người cùng tên → **CONFIRM** sếp muốn người nào (liệt kê group/role để phân biệt).
> 3. Nếu chỉ fuzzy gần đúng → **CONFIRM** "ý anh là X ạ, hay người khác?".
> 4. Không thấy → `add_people(name=..., chat_id để trống)` rồi tiếp tục action gốc.
>
> Khi sếp đưa danh sách *"team gồm A, B, C"* → gọi `add_people` mỗi người một lần.

### Tool description edits (`tool_definitions.py`)

- `create_task` (line 23): drop *"dùng đúng tên trong danh sách nhân sự"* from the `assignee` description. Replace with *"Tên người được giao — nếu chưa có trong hệ thống, hãy thêm trước bằng `add_people`."*
- `create_reminder` (line 527): drop *"Trước khi gọi, dùng list_people / check_team_engagement để lấy danh sách tên có Chat ID."* Replace with channel-neutral *"Trước khi gọi, đảm bảo người nhận đã có Person row (gọi `add_people` nếu chưa)."*
- `add_people` (line 131): `chat_id` description currently *"Chat ID Telegram (nếu biết). Thường chưa có, bỏ trống"* — make channel-agnostic: *"Chat ID của người trên kênh đã DM bot (Zalo/Telegram/…). Thường chưa có, bỏ trống."*
- `update_task` (line ~84), `get_workload` (line 448), `check_effort` (line 232): scan and remove any phrasing requiring chat_id or onboarded status. Keep *"GỌI TRƯỚC khi giao task"* on `check_effort` — that's a useful habit, not a gate.

## Data flow examples

**Case 1 — assignment to unknown name (group):**
Boss: *"giao design banner cho Tân, deadline thứ 6"* → LLM `get_people("Tân")` returns nothing → LLM asks *"Tân nào ạ? Em chưa có trong hệ thống, thêm mới nhé?"* → Boss confirms → LLM `add_people(name="Tân", group="Media")` → LLM `create_task(...)` → group announce fires.

**Case 2 — duplicate name:**
Boss: *"giao cho Tân"* → `get_people("Tân")` returns 2 hits (Tân Nguyễn / Tân Lê) → LLM: *"Tân nào ạ — Tân Nguyễn (Design) hay Tân Lê (Sale)?"* → Boss picks → continue.

**Case 3 — bulk team add:**
Boss DM: *"team mới: A (dev), B (designer), C (PM)"* → LLM calls `add_people` 3 times → reply *"Đã thêm A, B, C vào team."*

**Case 4 — reminder fires for stub:**
Reminder due for Tân (chat_id null). `_resolve_task_targets` (scheduler.py:78-88) returns `primary=None, fallback=source_group` → message lands in the source group. If reminder was set in boss DM, fallback chain ends at boss.

**Case 5 — stub later onboards:**
Tân DMs bot for the first time on Zalo → onboarding flow calls `membership_service.activate()` → chokepoint resolves the existing stub by name + writes the chat_id. Old tasks / reminders stay linked via Lark `record_id`. *(Verify activate's name-match logic during implementation; if missing, add a tiny match-by-name fallback in activate.)*

## Error handling & edge cases

| Case | Behavior |
|---|---|
| Boss confirms wrong stub | Use existing `delete_people` / `update_people` |
| Multiple same-name people exist | LLM MUST confirm which one before any action (system prompt rule 2) |
| Typo creates near-duplicate ("Tân", "Tan") | `get_people` fuzzy match should normalize diacritics + whitespace. **Verify in implementation**; if missing, small fix in `people_service.get_people` |
| Boss says "giao cho cả team Media" | Out of scope. `check_team_engagement` / `list_people(group=...)` already exist; LLM can use them |
| Stub onboards later | Rely on `membership_service.activate()` chokepoint. **Verify** it matches stub by name; if not, add name-fallback there |
| LLM skips fuzzy match and creates duplicate | Regression unit test asserts prompt block exists + LLM call order |
| Boss sets reminder for stub in DM (no source group) | Fallback chain ends at boss DM. Accepted limitation |
| Stub workspace | `add_people` writes to current workspace context. Already correct |

## Assumptions to verify in implementation plan

1. `get_people` normalizes Unicode diacritics + whitespace before fuzzy match.
2. `membership_service.activate()` can resolve an existing stub Person by name when a fresh chat_id arrives — needed for Case 5.

Both are small fixes if missing; not separate specs.

## Testing

Unit tests only — user will smoke-test in real chat afterwards.

| Test | Verifies |
|---|---|
| `test_add_people_stub.py` | `add_people(name="Tân")` (no chat_id) creates Lark row, no membership.activate, no crash |
| `test_stub_in_workload.py` | Stub appears in `get_workload` / `list_people` like any member |
| `test_create_task_stub_assignee.py` | `create_task(assignee="Tân")` (stub) creates Lark record + group announce; no DM attempted |
| `test_secretary_prompt_stub_rule.py` | System prompt contains the rule block + both disambiguation cases |
| `test_tool_desc_no_chatid_gate.py` | `create_task` / `create_reminder` descriptions do NOT contain *"Chat ID"* / *"đúng tên trong danh sách"* gating phrases |

No integration / LLM-driven tests — too flaky, costly; covered by user smoke-test.

## Out of scope (separate specs)

- Zalo polish (deferred — fragile right now).
- `db.py` → repos consolidation, `scheduler.py` split, `tool_definitions.py` slimming, onboarding flow merger.

## Rollback

Single git revert restores prior prompt + tool descriptions. No data migration, no schema change.
