# db.py → Repos (Round 1-3: bosses, memberships, reminders)

**Date:** 2026-05-18
**Status:** Design approved
**Scope:** First 3 rounds of an N-round incremental refactor.

## Problem

`src/db.py` is 958 lines containing ~52 free functions that already delegate to per-table repositories in `src/repositories/`. The dual surface (free function vs repo direct) is the root cause of repeated migration-time breakage: schema changes need to be reflected in two paths, and one of them is silently missed every refactor.

The refactor goal — long-term — is to make `db.py` schema-and-connection only, with all reads/writes going through repos.

## Goal (this spec)

Migrate **three high-touch tables** off `db.py` free functions in three independent rounds. Each round is a single commit, additive-only on schema, with a fixture-from-old test guard.

- **Round 1:** `bosses` (3 functions, ~38 callers)
- **Round 2:** `memberships` (5 functions, ~30 callers)
- **Round 3:** `reminders` (7 functions, ~12 callers)

Rounds 4-10 (notes, sessions, identity, conversations, messages, notifications, reviews, onboarding_state, token_usage) will follow the same template in later sessions; this spec only covers the first three but the template generalizes.

## Non-goals

- Touching schema (no `ALTER`, `DROP`, `RENAME`).
- Changing repo class signatures unless a caller proves a method is missing.
- Re-platforming away from SQLite + repo pattern.
- Refactoring `scheduler.py`, `tool_definitions.py`, or onboarding (those are separate slimming subsystems).

## Architecture

For each round:

```
1. Verify repo surface
   - Map every db.X(...) in scope to a repo.Y(...) call.
   - If a method is missing, ADD it on the repo (no behavior change in db.py).

2. Migrate callers
   - grep "db.X" in src/ → replace with `(await db._repo("name", RepoCls)).X(...)`
     OR with an explicit `RepoCls(await db.get_db()).X(...)` when a connection
     is already in scope.
   - One file per edit batch is fine; commit happens at end of round.

3. Drop the wrappers in db.py
   - Remove the free functions of this round.
   - Imports of those names elsewhere now error → guarantees no stragglers.

4. Migration-discipline test (fixture-from-old)
   - tests/unit/test_db_migration_from_round_N.py:
     - Copy a pre-round DB snapshot into tmp.
     - Run _init_schema (idempotent).
     - Use the migrated repo path to read the old rows.
     - Assert: same row count, same key fields, no exception.
```

Two helpers in `db.py` stay (they are infrastructure, not table-level):
- `_repo(name, cls)` — process-wide repo cache keyed by connection.
- `_ephemeral_repo(db, cls)` — wrap a caller-owned connection without caching.

Callers that already hold a connection prefer `_ephemeral_repo` / direct construction; the cache-backed `_repo` is the default.

## Round 1 — bosses

| db.py function | Repo method | Notes |
|---|---|---|
| `get_boss(chat_id)` and `get_boss(db, chat_id)` | `BossRepo.get(chat_id)` | The dual-signature form (connection vs chat_id) is consolidated: callers that pass a connection switch to `BossRepo(conn).get(...)` directly; the rest go through `db._repo("boss", BossRepo).get(...)`. |
| `create_boss(...)` | `BossRepo.create(...)` | Same keyword-arg surface. |
| `get_all_bosses()` | `BossRepo.list_all()` | |

Approx caller surface (verified by grep):

- `src/context_builder.py` — 4 sites of `db.get_boss`
- `src/main.py` — 1 site of `db.get_all_bosses`
- `src/scheduler.py` — 4 sites (`get_all_bosses` × 3, `get_boss` × 1+)
- Plus ~28 more across services / agent / onboarding (full count via grep at execution time)

## Round 2 — memberships

| db.py function | Repo method |
|---|---|
| `get_memberships(user_id)` (incl. dual-arg form) | `MembershipRepo.list_for_user(user_id)` |
| `get_all_memberships_for_boss(boss_chat_id)` | `MembershipRepo.list_for_boss(boss_chat_id)` |
| `get_membership(db, chat_id, boss_chat_id)` | `MembershipRepo(db).get(chat_id, boss_chat_id)` |
| `upsert_membership(db, ...)` | `MembershipRepo(db).upsert(...)` |
| `delete_membership(db, ...)` | `MembershipRepo(db).delete(...)` |
| `get_person(chat_id)` (legacy people_map) | `MembershipRepo.get_person_legacy(chat_id)` |
| `add_person(chat_id, boss_chat_id, ...)` (legacy) | Already a façade that calls `membership_service.activate(...)`. Keep the facade *outside* db.py — move to `services.membership_service` as `add_person_legacy` (or update callers to call `activate` directly). |
| `delete_person(chat_id)` (legacy) | `MembershipRepo.delete_person_legacy(chat_id)` |

## Round 3 — reminders

All 7 wrappers are already pure pass-through. Direct map:

| db.py function | Repo method |
|---|---|
| `create_reminder(...)` | `ReminderRepo.create(...)` |
| `get_due_reminders(now)` | `ReminderRepo.get_due(now)` |
| `mark_reminder_done(id)` | `ReminderRepo.mark_done(id)` |
| `list_reminders(boss_chat_id, status, limit)` | `ReminderRepo.list_for_boss(...)` |
| `update_reminder(...)` | `ReminderRepo.update(...)` |
| `delete_reminder(id, boss_chat_id)` | `ReminderRepo.delete(id, boss_chat_id)` |
| `sync_reminder_from_lark(db, sqlite_id, content, status)` | `ReminderRepo(db).sync_from_lark(...)` |

## Components touched (cumulative across 3 rounds)

| File | Change |
|---|---|
| `src/db.py` | Remove ~15 wrapper functions (round 1: 3, round 2: 5, round 3: 7). |
| `src/context_builder.py`, `src/main.py`, `src/scheduler.py`, `src/onboarding.py`, `src/group_onboarding.py`, `src/context.py`, `src/services/*.py`, `src/agent/*.py`, `src/controllers/*.py` | Update call sites for each table. |
| `tests/unit/test_db_migration_from_round_<N>.py` (3 new files) | Fixture-from-old guards. |
| `src/services/membership_service.py` | Receive the `add_person` façade if we move it out of `db.py`. |

## Migration discipline (per round)

From `feedback_db_migration_discipline.md`:

1. **Backup** — `cp data/history.db data/history.db.before-round-<N>` (developer-side, not committed; documented in plan).
2. **Schema changes** — none in this refactor.
3. **Additive only** — none in this refactor.
4. **Fixture-from-old test** — new test file per round. Test plan: build a tiny SQLite DB matching pre-round schema, fill 1-2 rows, then exercise the migrated repo path.
5. **Eliminate dual write surface** — exactly the point of this refactor.
6. **Lark field changes** — N/A.
7. **PR checklist** — included in commit message bullet list, one tick per step (or N/A).

## Testing

- **Per-round fixture-from-old test** (mandatory) — see step 4 above.
- **Full unit suite must stay green** — 239 pre-existing passes (6 known-flaky pre-existing failures are excluded from regression accounting; document those in the round-1 commit message).
- **Self-test harness (`scripts/self_test.py`)** — run once after Round 3 lands to smoke real flows. Not blocking per round; we trust the unit suite for inter-round confidence.

## Rollback

Each round is a single commit. Rollback = `git revert <round-sha>`. No schema rollback needed.

If a round's commit reveals a behavior gap between the wrapper and the repo (rare; the wrappers are already pure delegators), pause: fix the repo first in a separate commit, then redo the round.

## Out of scope

- Rounds 4-10 (other tables). Same template; later session.
- Other slimming pillars (scheduler split, tool_definitions diet, onboarding merger). Separate specs.
