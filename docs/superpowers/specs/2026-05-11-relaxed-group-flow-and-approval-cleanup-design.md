# Relaxed Group Flow & Approval Cleanup

**Date:** 2026-05-11
**Status:** Draft — awaiting user approval
**Scope:** Two thin slices: relax group-flow gates, and collapse the approval write paths into a single deterministic chokepoint.

## Goals

Strip friction from two flows the boss hits most:

1. **Group task / reminder assignment** — let the bot work even when not group admin, accept assignees who have never onboarded, and post the result back into the group it came from.
2. **Membership approvals** — collapse every active-membership write into one chokepoint (`activate()`), and harden the LLM-callable approval tools with strict preconditions and guards so the bot stops hallucinating approvals. The LLM still owns intent interpretation (with conversational history), but it cannot bypass the guard or scatter writes across the codebase.

Quality bar: **net `git diff --stat` must show deletions ≥ insertions** outside schema migration. Removing code is the point.

## Non-goals

- Cross-channel identity unification (drop hardcoded `"telegram"` provider). Separate spec.
- URL / link ingestion (YouTube, TikTok, article). Separate spec.
- Scheduler job consolidation, prompt trimming, validation cleanup. Tech debt, defer.
- Lark abstraction (`KnowledgeBackend` interface). YAGNI.

---

## Part 1 — Relaxed group flow

### 1.1 Drop the admin gate

Principle: any admin-only side effect (pin, kick, set title, etc.) raises `UnsupportedOperation` at the channel layer and is swallowed there with a one-line warning log. Callers stop checking `is_admin`. The bot continues serving every other flow.

Concretely: `group_onboarding` removes the `bot_must_be_admin` precondition; admin-only messenger methods get a uniform try/except wrapper. Implementation details are left to the plan.

### 1.2 Drop the onboard gate for assignment

Today `create_task` and `create_reminder` either drop the assignee or warn `"không có trong danh sách nhân sự"` when the tagged person is not in the Lark People table. The new behavior:

- Accept the assignee as a plain string. Always create the Lark row.
- The bot still tries to resolve the assignee to an `internal_id` via the Lark People lookup. If found → DM the person AND post a summary into the source group.
- If lookup misses (assignee not onboarded yet) → only post in the source group. The bot does not attempt to DM.

`_find_assignee_chat_id` (the Lark People lookup) stays — it covers the case where the boss types `"giao Anh A task X"` without an `@` mention. Behavior change: when the lookup misses, return `(None, False)` silently instead of producing a warning string for the caller. The caller decides: with `internal_id` → DM + group post, without → group post only.

No new validation. No new "pending assignee" concept. The Lark `Assignee` field is the source of truth; the bot's job is to surface activity to whoever is around.

### 1.3 Announce in the source group

When `create_task` or `create_reminder` is called from a group context (`ctx.is_group == True`), post a one-line summary into `ctx.chat_id` after the Lark write succeeds:

```
Task: {name} → {assignee} | deadline {deadline}
```

```
Reminder: {content} for {target} at {time}
```

5–10 lines per service, no new helpers.

### 1.4 Reminder fire to source group

Reminders created in a group should fire back into that group, not silently DM the boss.

Add one column via `_init_schema` ALTER:

```sql
ALTER TABLE reminders ADD COLUMN source_chat_id TEXT DEFAULT NULL;
```

`create_reminder` fills `source_chat_id` with `ctx.chat_id` when `ctx.is_group`. Scheduler routing on fire:

1. `target_chat_id` set → DM that person.
2. Else `source_chat_id` set → post into the source group.
3. Else → DM boss (current behavior).

---

## Part 2 — Approval gate cleanup

### 2.1 One canonical `activate()` function

Today active-membership writes are scattered across these callsites:

| Callsite | Caller | Gate today |
|---|---|---|
| `join_service.approve_join` | LLM tool | pending check |
| `onboarding.handle_boss_join_decision` | regex parser | pending check — **deleted in §2.3** |
| `services.people_service.add_person` → `db.add_person` | LLM tool | none |
| `services.communication_service.link_contact_to_person` → `db.add_person` | LLM tool | none |
| `onboarding._complete_boss` | self-onboard | own workspace only |

Replace with one function: `src/services/membership_service.py::activate(...)`.

```python
async def activate(
    *,
    chat_id: str,
    boss_chat_id: str,
    person_type: str,
    name: str,
    source: Literal["approval", "boss_add", "self_boss", "link_contact"],
    lark_record_id: str | None = None,
    request_info: str | None = None,
) -> None: ...
```

Inside:
1. Look up the prior row. If it existed with `status='pending'`, this is an approval-equivalent transition — send the approved-user notification regardless of `source`.
2. Upsert `memberships` with `status='active'`.
3. Upsert Lark People if `lark_record_id` is `None`.
4. Emit one audit log line tagged with `source`.

All five callsites delegate to this. Direct `repo.upsert(..., status='active')` calls outside this function are removed. Pending → active transitions notify the user the same way, no matter which path the boss used.

### 2.2 Harden the approval tools (do not remove them)

The four approval tools (`approve_join`, `reject_join`, `approve_task_change`, `reject_task_change`) remain LLM-callable. The bug is not that they exist — it is that they are loose. Tighten them per §2.3: precondition wording in descriptions, runtime guards inside the functions, and `activate()` as the sole write path. The LLM still owns interpretation, with conversational history as context; the function refuses obviously wrong calls.

### 2.3 Approval flow: LLM semantic intent, gated tools

**No regex parser.** Real boss replies are too varied — `"duyệt đi"`, `"ok approve"`, `"yes em ok rồi"`, replying to the notification with `"ừ"` — patterns cannot cover them and bot looks dumb when they miss. Interpretation always goes through the LLM with conversational context.

Remove the existing `onboarding.handle_boss_join_decision` function and any code that calls it.

Keep `approve_join`, `reject_join`, `approve_task_change`, `reject_task_change` as **tools the LLM can call**, but harden them:

1. **Tool description rewrite.** Each tool's description spells out the precondition: a pending row must exist for the supplied id, AND the immediately-preceding bot message must have been a request for that decision. The LLM enforces this implicitly by reading context.

2. **Tool-level guard.** Inside each function, refuse to act when:
   - The supplied id has no `status='pending'` row, OR
   - The pending row's `boss_chat_id` is not `ctx.boss_chat_id`.

   Refusal returns a short string the LLM relays to the boss (`"No pending approval matches <id>."`). The LLM cannot bypass this — the guard runs in Python before any Lark/DB write.

3. **History context required.** The agent loop must include at least the last 5 messages of the current conversation when calling the LLM on a turn that could plausibly contain an approval decision (boss DM with at least one open pending approval). This is a general rule for any message-interpreting LLM call, not specific to approvals — see related test `test_llm_always_called_with_history`.

The boss's notification message is updated to invite natural replies (`"Reply naturally — e.g. 'approve', 'duyệt nhé', 'no thanks'"`) instead of dictating an exact phrase.

The `activate()` chokepoint from §2.1 still owns the write. The LLM tools call into `activate()`. No path outside `activate()` flips `memberships.status` to active. The audit log distinguishes the source.

### 2.4 Consequences

- `add_person` LLM tool: kept (boss explicitly adds someone). Its DB write now flows through `activate(source="boss_add")`. No behavioral change for the boss; just a single audit path.
- `link_contact_to_person` LLM tool: kept. Its membership-active side effect flows through `activate(source="link_contact")`. If the target chat_id has a pending membership for a *different* workspace, the function rejects with a clear error and instructs the boss to use the approval flow instead.
- Spec-locked invariant: no code path outside `activate()` may write `memberships.status='active'`.

---

## Schema migration

Single column added, via the existing `_init_schema` idempotent ALTER pattern:

```sql
ALTER TABLE reminders ADD COLUMN source_chat_id TEXT DEFAULT NULL;
```

No data backfill needed. Existing rows have `source_chat_id IS NULL` and fall through to the current DM-boss path on fire.

## Acceptance criteria

1. Boss tags an un-onboarded person in a group with a deadline → bot creates the Lark task, posts a summary in the group, does not DM (no `internal_id`).
2. Scheduler reminder created in a group with no target → on fire, posts into the source group, not the boss DM.
3. Bot added to a new group without admin rights → group onboarding completes; pin / kick attempts log warnings but do not abort.
4. User asks to join workspace B from inside workspace A → bot calls `request_join` (LLM tool); membership is `pending`; boss B is notified.
5. Boss B replies naturally (`"approve"`, `"ok duyệt nhé"`, `"yes"`, etc.) → LLM with recent history understands intent → calls `approve_join` → guard passes → membership active via `activate()`.
6. Boss B replies `"approve abc-XXX"` for an id that does not have a pending row → guard refuses → bot replies `"No pending approval matches abc-XXX"`. No write.
7. `git grep` for direct active-status writes returns only matches inside `services/membership_service.py` and tests.
8. `git diff --stat`: deletions ≥ insertions outside the new `membership_service.py`.

## Test plan

Unit tests in `tests/unit/`. Existing patterns: in-memory aiosqlite via `_init_schema`, mock the lark module via `monkeypatch`.

| Test | Verifies |
|---|---|
| `test_create_task_announces_in_group` | Group ctx + create_task → group receives summary message |
| `test_create_task_un_onboarded_assignee` | Assignee name not in Lark People → task created with `Assignee` string, no DM attempted, group post sent |
| `test_create_reminder_persists_source_chat_id` | Group ctx → `source_chat_id` column populated |
| `test_scheduler_fires_reminder_to_source_group` | Reminder with `source_chat_id` set, no `target_chat_id` → scheduler sends into group |
| `test_scheduler_fires_reminder_to_boss_when_no_source` | Both null → falls back to boss DM (regression guard) |
| `test_group_onboarding_without_admin_continues` | Bot not admin → onboarding still completes |
| `test_pin_swallows_unsupported_operation` | `UnsupportedOperation` from messenger.pin → caller does not raise |
| `test_membership_activate_is_single_chokepoint` | Static check: `grep -rn "status=.active." src` only matches `membership_service.py` |
| `test_activate_via_approval_audit_tag` | `activate(source="approval", ...)` writes an audit row tagged `"approval"` |
| `test_approve_join_guard_refuses_when_no_pending` | `approve_join` called with id that has no pending row → returns refusal string, no DB write |
| `test_approve_join_guard_refuses_when_wrong_workspace` | Pending row exists but belongs to a different `boss_chat_id` → refusal, no write |
| `test_approve_task_change_guard_refuses_when_no_pending` | Same guard pattern for tasks |
| `test_approve_join_writes_via_activate_only` | Successful approval call routes through `membership_service.activate(source="approval")` |
| `test_llm_always_called_with_history` | Any LLM call path includes ≥ N recent messages in the prompt (no system-prompt-only invocations allowed) |
| `test_handle_boss_join_decision_removed` | `onboarding.handle_boss_join_decision` no longer exists (importing it raises `AttributeError`) |
| `test_link_contact_rejects_when_pending_elsewhere` | Pending membership in workspace X → `link_contact_to_person` from workspace Y returns CONFLICT |

## Out-of-scope, captured as follow-up

- Hardcoded `"telegram"` provider in `_find_assignee_chat_id`, `_resolve_target`, `_check_deadlines`. Track as Zalo-first identity spec.
- URL / link ingestion handlers. Track as separate feature spec.
- Scheduler job overlap (`_check_deadlines` + `_check_deadline_push` + `_after_deadline_check`). Tech debt note.
- Prompt size in `secretary_agent.py` and friends. Tech debt note.
- Validation cruft in `tool_definitions.py` (enums, regex, length). Tech debt note.
