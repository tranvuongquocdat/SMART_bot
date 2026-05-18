# db.py → Repos (Round 1-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to follow this task-by-task. User has indicated all rounds collapse into one final commit, so the per-round commits below are conceptual checkpoints, not separate commits.

**Goal:** Migrate callers of `bosses`, `memberships`, `reminders` off `db.py` free functions and onto repo classes; remove the wrappers from `db.py`.

**Architecture:** Pure mechanical refactor. Repos already exist with matching methods. `db.py` wrappers are pure pass-through. Each caller's `db.X(...)` becomes `(await db._repo("name", RepoCls)).X(...)` — or `RepoCls(conn).X(...)` if a connection is already in scope.

**Tech Stack:** Python 3.12, aiosqlite, pytest.

**Spec:** `docs/superpowers/specs/2026-05-18-db-py-to-repos-design.md`

**Final-commit mode:** User selected single end-of-work commit. Execute Round 1 → Round 2 → Round 3 → run full unit suite → single commit covering all 3 rounds.

---

## Replacement legend

Two forms appear at call sites:

```python
# Form A — no connection in scope (most common)
await db.get_boss(chat_id)
# →
boss_repo = await db._repo("boss", BossRepo)
await boss_repo.get(chat_id)
# OR, when the call is one-shot, inline:
await (await db._repo("boss", BossRepo)).get(chat_id)

# Form B — caller already holds a connection (`_db`, `conn`, etc.)
await db.get_boss(_db, chat_id)
# →
await BossRepo(_db).get(chat_id)
```

Pick Form A by default. Use Form B only where the existing call passes a connection.

Imports required at top of each touched file (only if not already present):
```python
from src import db
from src.repositories.boss_repo import BossRepo
from src.repositories.membership_repo import MembershipRepo
from src.repositories.reminder_repo import ReminderRepo
```

`from src import db` already exists everywhere; the repo imports are added only where the new code references them.

---

## Round 1 — bosses

**Goal:** Remove `get_boss`, `create_boss`, `get_all_bosses` from `src/db.py`. Migrate 38 call sites.

### Task 1.1 — Migrate call sites

- [ ] **Step 1: For each file/line below, perform the replacement.**

Use the form indicated. Read the file once before editing it; do all replacements in that file in a single Edit call where practical.

| File | Line | Original | Replacement |
|---|---|---|---|
| `src/main.py` | 162 | `await db.get_all_bosses()` | `await (await db._repo("boss", BossRepo)).list_all()` |
| `src/context_builder.py` | 29 | `await db.get_boss(sender_id)` | `await (await db._repo("boss", BossRepo)).get(sender_id)` |
| `src/context_builder.py` | 42 | `await db.get_boss(m["boss_chat_id"])` | `await (await db._repo("boss", BossRepo)).get(m["boss_chat_id"])` |
| `src/context_builder.py` | 156 | `await db.get_boss(boss_chat_id)` | `await (await db._repo("boss", BossRepo)).get(boss_chat_id)` |
| `src/context_builder.py` | 193 | `await db.get_boss(sid)` | `await (await db._repo("boss", BossRepo)).get(sid)` |
| `src/agent/reminder_agent.py` | 94 | `await db.get_boss(boss_chat_id)` | `await (await db._repo("boss", BossRepo)).get(boss_chat_id)` |
| `src/scheduler.py` | 51, 65, 116, 257, 320, 457, 815 | `await db.get_all_bosses()` | `await (await db._repo("boss", BossRepo)).list_all()` |
| `src/scheduler.py` | 232 | `await db.get_boss(r["boss_chat_id"])` | `await (await db._repo("boss", BossRepo)).get(r["boss_chat_id"])` |
| `src/scheduler.py` | 740 | `bosses_cache[owner_id] = await db.get_boss(owner_id)` | `bosses_cache[owner_id] = await (await db._repo("boss", BossRepo)).get(owner_id)` |
| `src/utils/chat_id_resolver.py` | 65 | `await db.get_boss(str(boss_chat_id))` | `await (await db._repo("boss", BossRepo)).get(str(boss_chat_id))` |
| `src/group_onboarding.py` | 168 | `await db.get_all_bosses()` | `await (await db._repo("boss", BossRepo)).list_all()` |
| `src/services/join_service.py` | 18 | `await db.get_all_bosses()` | `await (await db._repo("boss", BossRepo)).list_all()` |
| `src/services/join_service.py` | 48 | `await db.get_boss(target_boss_id)` | `await (await db._repo("boss", BossRepo)).get(target_boss_id)` |
| `src/services/membership_service.py` | 45, 105 | `await db.get_boss(str(boss_chat_id))` | `await (await db._repo("boss", BossRepo)).get(str(boss_chat_id))` |
| `src/channels/zalo_bridge/inbound_filter.py` | 73, 76 | `await db.get_boss(person_id)` / `await db.get_boss(conv_id)` | `await (await db._repo("boss", BossRepo)).get(person_id)` / `.get(conv_id)` |
| `src/services/_workspace_helper.py` | 28 | `await db.get_boss(int(active_ws_id))` | `await (await db._repo("boss", BossRepo)).get(int(active_ws_id))` |
| `src/services/_workspace_helper.py` | 35 | `await db.get_boss(ctx.sender_chat_id)` | `await (await db._repo("boss", BossRepo)).get(ctx.sender_chat_id)` |
| `src/services/_workspace_helper.py` | 51 | `await db.get_boss(m["boss_chat_id"])` | `await (await db._repo("boss", BossRepo)).get(m["boss_chat_id"])` |
| `src/controllers/message_router.py` | 91 | `await db.get_boss(sender_id)` | `await (await db._repo("boss", BossRepo)).get(sender_id)` |
| `src/agent/advisor_agent.py` | 153, 180 | `await db.get_boss(ctx.boss_chat_id)` | `await (await db._repo("boss", BossRepo)).get(ctx.boss_chat_id)` |
| `src/onboarding.py` | 122 | `await db.create_boss(...)` | `await (await db._repo("boss", BossRepo)).create(...)` |
| `src/onboarding.py` | 247, 408, 503 | `await db.get_all_bosses()` | `await (await db._repo("boss", BossRepo)).list_all()` |
| `src/agent/secretary_agent.py` | 351 | `await db.get_boss(boss_chat_id)` | `await (await db._repo("boss", BossRepo)).get(boss_chat_id)` |
| `src/agent/secretary_agent.py` | 518 | `await db.get_boss(boss_id) or {}` | `await (await db._repo("boss", BossRepo)).get(boss_id) or {}` |
| `src/agent/llm_for_ctx.py` | 38 | `await db.get_boss(ctx.boss_chat_id) or {}` | `await (await db._repo("boss", BossRepo)).get(ctx.boss_chat_id) or {}` |
| `src/services/reset_service.py` | 28, 90 | `await db.get_boss(ctx.boss_chat_id)` / `await db.get_boss(boss_id)` | Same pattern |
| `src/context.py` | 46, 67, 87, 96, 104 | `await db_mod.get_boss(_db, ...)` (Form B with `_db` already in scope) | `await BossRepo(_db).get(...)` |
| `src/services/tasks_service.py` | 333 | `await db_mod.get_boss(str(ctx.boss_chat_id))` | `await (await db_mod._repo("boss", BossRepo)).get(str(ctx.boss_chat_id))` |

- [ ] **Step 2: Sanity grep — no `db.get_boss` / `db.create_boss` / `db.get_all_bosses` left in `src/`**

```bash
grep -rn 'db\.\(get_boss\|create_boss\|get_all_bosses\)\b' src/ --include="*.py"
grep -rn 'db_mod\.\(get_boss\|create_boss\|get_all_bosses\)\b' src/ --include="*.py"
```

Expected: empty. If non-empty, finish the misses before continuing.

### Task 1.2 — Drop wrappers from `db.py`

- [ ] **Step 1: Remove the three boss free functions.**

In `src/db.py`, delete lines 437-474 (the block starting `async def get_boss` through the end of `async def get_all_bosses`). Replace the block with a single comment:

```python
# bosses table — see src/repositories/boss_repo.BossRepo
```

### Task 1.3 — Fixture-from-old test

- [ ] **Step 1: Create `tests/unit/test_db_migration_round1_bosses.py`**

```python
"""Round 1 fixture-from-old: a pre-round DB snapshot (one boss row inserted
via raw SQL the way it would have lived on prod) must still be readable
through BossRepo after _init_schema is applied. Guards against accidental
schema drift during the boss free-function removal."""
import aiosqlite
import pytest

from src.db import _init_schema
from src.repositories.boss_repo import BossRepo


async def test_pre_round_boss_row_still_readable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        # Insert a row the way create_boss would have.
        await conn.execute(
            "INSERT INTO bosses "
            "(chat_id, name, company, lark_base_token, lark_table_people, "
            " lark_table_tasks, lark_table_projects, lark_table_ideas, "
            " lark_table_reminders, lark_table_notes, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("boss-old-1", "Old Boss", "OldCo",
             "base-tok", "tp", "tt", "tprj", "ti", "tr", "tn",
             "old@example.com"),
        )
        await conn.commit()

        repo = BossRepo(conn)

        got = await repo.get("boss-old-1")
        assert got is not None
        assert got["name"] == "Old Boss"
        assert got["company"] == "OldCo"
        assert got["lark_base_token"] == "base-tok"

        listed = await repo.list_all()
        assert any(b["chat_id"] == "boss-old-1" for b in listed)
    finally:
        await conn.close()
```

- [ ] **Step 2: Run it**

`uv run pytest tests/unit/test_db_migration_round1_bosses.py -v`
Expected: PASS.

---

## Round 2 — memberships

**Goal:** Remove `get_memberships`, `get_all_memberships_for_boss`, `get_membership`, `upsert_membership`, `delete_membership`, `get_person`, `add_person`, `delete_person` from `src/db.py`. Migrate ~13 call sites.

### Task 2.1 — Migrate call sites

| File | Line | Original | Replacement |
|---|---|---|---|
| `src/context_builder.py` | 26 | `await db.get_memberships(str(sender_id))` | `await (await db._repo("membership", MembershipRepo)).list_for_user(str(sender_id))` |
| `src/onboarding.py` | 272, 560 | `await db.upsert_membership(...)` (5-arg form, no conn) | `await (await db._repo("membership", MembershipRepo)).upsert(...)` |
| `src/onboarding.py` | 358 | `await db.get_memberships(str(sender_id))` | `await (await db._repo("membership", MembershipRepo)).list_for_user(str(sender_id))` |
| `src/services/_workspace_helper.py` | 33 | `await db.get_memberships(str(ctx.sender_chat_id))` | Same as above with `ctx.sender_chat_id` |
| `src/services/people_service.py` | 311 | `await db.delete_person(internal_id)` | `await (await db._repo("membership", MembershipRepo)).delete_person_legacy(internal_id)` |
| `src/services/join_service.py` | 19 | `await db.get_memberships(str(ctx.sender_chat_id))` | Same |
| `src/services/join_service.py` | 38, 110 | `await db.upsert_membership(...)` | Same pattern |
| `src/services/join_service.py` | 70, 106 | `await db.get_membership(_db, ...)` (Form B) | `await MembershipRepo(_db).get(...)` |
| `src/context.py` | 49 | `await db_mod.get_membership(_db, str(sender_id), str(boss["chat_id"]))` | `await MembershipRepo(_db).get(str(sender_id), str(boss["chat_id"]))` |
| `src/context.py` | 64 | `await db_mod.get_memberships(_db, str(sender_id))` (Form B with `_db`) | `await MembershipRepo(_db).list_for_user(str(sender_id))` |

For `db.add_person(...)` — only used inside `db.py` itself currently as a legacy facade; **no production callsites** call it. Action: when dropping the wrapper, delete the body. If grep finds any caller during execution, redirect to `services.membership_service.activate(...)` directly.

Add `from src.repositories.membership_repo import MembershipRepo` to the top of any file that uses it and doesn't already import.

- [ ] **Step 1: Apply replacements.**
- [ ] **Step 2: Sanity grep**

```bash
grep -rn 'db\.\(get_memberships\|get_all_memberships_for_boss\|get_membership\|upsert_membership\|delete_membership\|get_person\|add_person\|delete_person\)\b' src/ --include="*.py"
grep -rn 'db_mod\.\(get_memberships\|get_membership\)\b' src/ --include="*.py"
```

Expected: empty.

### Task 2.2 — Drop wrappers from `db.py`

- [ ] **Step 1:** In `src/db.py`, delete the 8 functions named above (lines ~553-576 + 759-794 — read once before editing to get exact ranges; ranges shift as other rounds are also editing this file in the same session).

Replace with a single comment:

```python
# memberships table — see src/repositories/membership_repo.MembershipRepo
```

### Task 2.3 — Fixture-from-old test

- [ ] **Step 1: Create `tests/unit/test_db_migration_round2_memberships.py`**

```python
"""Round 2 fixture-from-old: pre-round memberships rows survive _init_schema
and remain queryable through MembershipRepo."""
import aiosqlite

from src.db import _init_schema
from src.repositories.membership_repo import MembershipRepo


async def test_pre_round_memberships_still_readable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        # Seed a boss + two memberships
        await conn.execute(
            "INSERT INTO bosses (chat_id, name, lark_base_token, lark_table_people, "
            "lark_table_tasks, lark_table_projects, lark_table_ideas, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("boss-1", "Boss", "b", "p", "t", "pj", "i", ""),
        )
        await conn.execute(
            "INSERT INTO memberships "
            "(chat_id, boss_chat_id, person_type, name, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("u1", "boss-1", "member", "Alice", "active"),
        )
        await conn.execute(
            "INSERT INTO memberships "
            "(chat_id, boss_chat_id, person_type, name, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("u2", "boss-1", "partner", "Bob", "active"),
        )
        await conn.commit()

        repo = MembershipRepo(conn)

        assert (await repo.get("u1", "boss-1"))["name"] == "Alice"
        for_user = await repo.list_for_user("u2")
        assert any(m["name"] == "Bob" for m in for_user)
        for_boss = await repo.list_for_boss("boss-1")
        assert len(for_boss) == 2
    finally:
        await conn.close()
```

- [ ] **Step 2: Run it**

`uv run pytest tests/unit/test_db_migration_round2_memberships.py -v` → PASS.

---

## Round 3 — reminders

**Goal:** Remove `create_reminder`, `get_due_reminders`, `mark_reminder_done`, `list_reminders`, `update_reminder`, `delete_reminder`, `sync_reminder_from_lark` from `src/db.py`. Migrate 7 call sites.

### Task 3.1 — Migrate call sites

| File | Line | Original | Replacement |
|---|---|---|---|
| `src/agent/reminder_agent.py` | 154 | `await db.mark_reminder_done(reminder["id"])` | `await (await db._repo("reminder", ReminderRepo)).mark_done(reminder["id"])` |
| `src/scheduler.py` | 223 | `await db.get_due_reminders()` | `await (await db._repo("reminder", ReminderRepo)).get_due()` |
| `src/scheduler.py` | 588 | `await db.create_reminder(...)` | `await (await db._repo("reminder", ReminderRepo)).create(...)` |
| `src/services/reminder_service.py` | 85 | `await db.create_reminder(...)` | Same |
| `src/services/reminder_service.py` | 148 | `await db.list_reminders(ctx.boss_chat_id, status=status, limit=limit)` | `await (await db._repo("reminder", ReminderRepo)).list_for_boss(ctx.boss_chat_id, status=status, limit=limit)` |
| `src/services/reminder_service.py` | 195 | `await db.update_reminder(...)` | `await (await db._repo("reminder", ReminderRepo)).update(...)` |
| `src/services/reminder_service.py` | 261 | `await db.delete_reminder(reminder_id, ctx.boss_chat_id)` | `await (await db._repo("reminder", ReminderRepo)).delete(reminder_id, ctx.boss_chat_id)` |

`db.sync_reminder_from_lark` is only called inside `db.py` itself (or in the legacy reverse-sync scheduler block — verify with grep). If a caller exists, migrate to `ReminderRepo(conn).sync_from_lark(...)` using the connection in scope.

- [ ] **Step 1:** Apply replacements. Add `from src.repositories.reminder_repo import ReminderRepo` where used.
- [ ] **Step 2:** Sanity grep

```bash
grep -rn 'db\.\(create_reminder\|get_due_reminders\|mark_reminder_done\|list_reminders\|update_reminder\|delete_reminder\|sync_reminder_from_lark\)\b' src/ --include="*.py"
```

Expected: empty.

### Task 3.2 — Drop wrappers from `db.py`

- [ ] In `src/db.py`, delete the 7 reminder free functions (lines ~644-700 — re-read range; it has shifted). Replace with comment `# reminders table — see src/repositories/reminder_repo.ReminderRepo`.

### Task 3.3 — Fixture-from-old test

- [ ] **Step 1: Create `tests/unit/test_db_migration_round3_reminders.py`**

```python
"""Round 3 fixture-from-old: a reminder row inserted with the pre-round
schema is still readable, due-listable, and mark-done-able via
ReminderRepo."""
from datetime import datetime, timedelta, timezone

import aiosqlite

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


async def test_pre_round_reminder_still_actionable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        # Insert a due reminder
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(
            sep=" ", timespec="seconds",
        )
        await conn.execute(
            "INSERT INTO reminders "
            "(boss_chat_id, target_chat_id, target_name, content, remind_at, "
            " status, source_chat_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("boss-1", None, "", "old reminder", past, "pending", None),
        )
        await conn.commit()

        repo = ReminderRepo(conn)

        due = await repo.get_due()
        assert any(r["content"] == "old reminder" for r in due)

        rid = due[0]["id"]
        await repo.mark_done(rid)

        # Re-query: should no longer be 'pending'
        async with conn.execute(
            "SELECT status FROM reminders WHERE id = ?", (rid,)
        ) as cur:
            row = await cur.fetchone()
        assert row["status"] == "done"
    finally:
        await conn.close()
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_db_migration_round3_reminders.py -v` → PASS.

---

## Final verification + commit

- [ ] **Step 1: Run full unit suite**

`uv run pytest tests/unit -q --no-header`
Expected: same 239 pre-existing PASS plus 3 new round-tests = 242 PASS. The 6 known pre-existing failures (`test_context.py`, `test_scheduler_reverse_sync_reminders.py`, `test_zalo_messenger.py`) remain — note in commit message.

- [ ] **Step 2: Re-grep the full surface**

```bash
grep -rn 'db\(_mod\)\?\.\(get_boss\|create_boss\|get_all_bosses\|get_memberships\|get_all_memberships_for_boss\|get_membership\|upsert_membership\|delete_membership\|get_person\|add_person\|delete_person\|create_reminder\|get_due_reminders\|mark_reminder_done\|list_reminders\|update_reminder\|delete_reminder\|sync_reminder_from_lark\)\b' src/ --include="*.py"
```

Expected: empty.

- [ ] **Step 3: Single commit**

```bash
git add src/ tests/unit/test_db_migration_round*.py
git commit -m "refactor(db): callers go through repos — round 1-3 (bosses, memberships, reminders)

Round 1: bosses (3 wrappers removed, 38 call sites migrated)
Round 2: memberships (8 wrappers removed, 13 call sites migrated)
Round 3: reminders (7 wrappers removed, 7 call sites migrated)

db.py shrinks by ~250 lines. Schema unchanged. Per-round
fixture-from-old test guards verify pre-round rows remain readable
through the new repo path. 7-step migration discipline:
  1. backup snapshot — N/A in CI, local-only
  2. _migrate_schema unchanged — only code paths refactored
  3. additive-only — no DROP/ALTER
  4. fixture-from-old tests added (1 per round)
  5. dual write surface eliminated for these 3 tables
  6. Lark — N/A
  7. checklist — this message

Pre-existing 6 unit failures unchanged (test_context.py x4,
test_scheduler_reverse_sync_reminders.py, test_zalo_messenger.py) —
not in scope.

Spec: docs/superpowers/specs/2026-05-18-db-py-to-repos-design.md
Plan: docs/superpowers/plans/2026-05-18-db-py-to-repos-round-1-3.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notes

- Spec section "Round 1 bosses" → Tasks 1.1-1.3.
- Spec section "Round 2 memberships" → Tasks 2.1-2.3.
- Spec section "Round 3 reminders" → Tasks 3.1-3.3.
- Spec section "Migration discipline" steps 1-7 → covered by per-round fixture tests + commit message tick list.
- Spec section "Testing" → final-verification step runs full unit suite.

No placeholders. Every call-site replacement table contains literal source-form and replacement-form. The note "ranges shift as other rounds also edit this file" warns the engineer to re-read `db.py` between rounds.
