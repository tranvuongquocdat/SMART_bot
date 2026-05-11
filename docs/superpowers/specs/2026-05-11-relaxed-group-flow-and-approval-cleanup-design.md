# Relaxed Group Flow & Approval Cleanup

**Date:** 2026-05-11
**Status:** Draft — awaiting user approval
**Scope:** Two thin slices: relax group-flow gates, and collapse the approval write paths into a single deterministic chokepoint.

## Goals

Strip friction from two flows the boss hits most:

1. **Group task / reminder assignment** — let the bot work even when not group admin, accept assignees who have never onboarded, and post the result back into the group it came from.
2. **Membership approvals** — make it impossible for the LLM to grant access. Boss approval becomes a single deterministic state transition with one write path.

Quality bar: **net `git diff --stat` must show deletions ≥ insertions** outside schema migration. Removing code is the point.

## Non-goals

- Cross-channel identity unification (drop hardcoded `"telegram"` provider). Separate spec.
- URL / link ingestion (YouTube, TikTok, article). Separate spec.
- Scheduler job consolidation, prompt trimming, validation cleanup. Tech debt, defer.
- Lark abstraction (`KnowledgeBackend` interface). YAGNI.

---

## Part 1 — Relaxed group flow

### 1.1 Drop the admin gate

Currently several group flows refuse to proceed when the bot is not a chat admin (e.g. `group_onboarding`, pin/unpin paths). Replace each hard refusal with `try / except UnsupportedOperation`. The bot continues; admin-only side effects are skipped with a one-line log.

| File | Change |
|---|---|
| `src/group_onboarding.py` | Remove `bot_must_be_admin` precondition. Continue onboarding regardless. |
| `src/channels/telegram_singleton.py` (`pin_chat_message`, `set_chat_title`, `set_chat_description`, `ban_chat_member`) | Wrap each call in try / except, swallow `UnsupportedOperation`, log warning. |
| `src/services/group_service.py` | Drop any caller-side admin checks; rely on the channel layer. |

### 1.2 Drop the onboard gate for assignment

Today `create_task` and `create_reminder` either drop the assignee or warn `"không có trong danh sách nhân sự"` when the tagged person is not in the Lark People table. The new behavior:

- Accept the assignee as a plain string. Always create the Lark row.
- If the assignee has an `internal_id` (resolved from a mention or known person), DM them and also post a summary into the source group.
- If the assignee has no `internal_id`, only post in the source group. The bot does not attempt to DM.

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

### 1.5 Surface mentions to the LLM

Mentions are already resolved to `internal_id` in `IncomingMessage.mentions` but never reach the prompt. Prepend a structured context block to the user turn whenever mentions are present:

```
[Mentioned in this message]
- @Lan → person_id=abc-123 (known)
- @Tân → person_id=null (not in system)
```

Add an optional `assignee_id` parameter to `create_task` and `create_reminder` in `src/agent/tool_definitions.py` (alongside the existing `assignee` name string). The LLM passes the resolved id when available; the name string remains the fallback. The Lark display name is still derived from the mention text or the LLM's parse. When `assignee_id` is set, services use it directly and skip `_find_assignee_chat_id` for that turn.

---

## Part 2 — Approval gate cleanup

### 2.1 One canonical `activate()` function

Today five callsites write `memberships.status='active'`:

| Callsite | Caller | Gate |
|---|---|---|
| `join_service.approve_join` | LLM tool | pending check |
| `onboarding.handle_boss_join_decision` | regex parser | pending check |
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

### 2.2 Remove approval gates from LLM tool surface

Delete from `src/agent/tool_definitions.py` and `src/agent/handlers/`:

- `approve_join`
- `reject_join`
- `approve_task_change`
- `reject_task_change`

The underlying functions in `services/join_service.py` and `services/tasks_service.py` stay — they are invoked only by the deterministic boss-reply parser.

### 2.3 Generalize the deterministic boss-reply parser

`onboarding.handle_boss_join_decision` already parses `"approve <id>"` / `"reject <id>"`. Generalize and move into `src/agent/boss_decision_parser.py`. Each pattern is a strict regex; both English and Vietnamese decision keywords are accepted to match real boss usage:

| Pattern (English / Vietnamese) | Action |
|---|---|
| `approve <id>` / `duyet <id>` | activate via join |
| `reject <id>` / `tu choi <id>` | reject_join |
| `ok task <name>` / `duyet task <name>` | approve_task_change(approval_id) |
| `reject task <name>` / `tu choi task <name>` | reject_task_change(approval_id) |

Patterns are anchored (`^…$` after `strip()`) so natural-language messages like `"ok let me approve that task later"` do not trigger.

Wired in `controllers/message_router.py` as a pre-LLM step:

- If the sender is a boss AND the message matches a known pattern → run the parser. On hit, reply with the parser's outcome and **skip the LLM** for this turn. On parser "no matching pending row", reply with a short error (`"No pending approval matches '<id>'"`) and skip the LLM.
- If the message does not match any pattern → fall through to the LLM as today.

The parser is intentionally regex-strict to avoid accidental triggers from natural-language messages that happen to contain `"approve"` or `"ok task"`.

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
4. User asks to join workspace B from inside workspace A → bot calls `request_join` (LLM tool, still allowed); membership is `pending`; boss B is notified; **LLM cannot grant access** — verified by removing the tools from the schema.
5. Boss B replies `"approve <id>"` → deterministic parser activates the membership; no LLM round trip.
6. `git grep -n "status='active'"` on the implementation branch returns only matches inside `services/membership_service.py` and tests.
7. `git diff --stat HEAD~..HEAD`: deletions ≥ insertions, excluding the new `membership_service.py` and `boss_decision_parser.py`.

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
| `test_approve_join_tool_removed_from_definitions` | `tool_definitions.TOOL_DEFINITIONS` does not contain `approve_join` etc. |
| `test_boss_reply_approve_runs_parser_not_llm` | Message router sees `"approve <id>"` from a boss with a pending row → parser invoked, LLM not called |
| `test_boss_reply_ok_task_routes_to_parser` | Message router sees `"ok task <name>"` from a boss with a pending task approval → parser invoked |
| `test_link_contact_rejects_when_pending_elsewhere` | Pending membership in workspace X → `link_contact_to_person` from workspace Y returns CONFLICT |
| `test_mentions_in_prompt` | Mentions present → user turn contains `[Mentioned in this message]` block with resolved ids |

## Out-of-scope, captured as follow-up

- Hardcoded `"telegram"` provider in `_find_assignee_chat_id`, `_resolve_target`, `_check_deadlines`. Track as Zalo-first identity spec.
- URL / link ingestion handlers. Track as separate feature spec.
- Scheduler job overlap (`_check_deadlines` + `_check_deadline_push` + `_after_deadline_check`). Tech debt note.
- Prompt size in `secretary_agent.py` and friends. Tech debt note.
- Validation cruft in `tool_definitions.py` (enums, regex, length). Tech debt note.
