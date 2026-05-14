# Relaxed Group Flow & Approval Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relax the group-flow gates (admin, onboard) so the bot serves more cases, and collapse all active-membership writes into one chokepoint with hardened LLM approval tools.

**Architecture:** Inline-await Lark sync continues. One new file `src/services/membership_service.py` owns every `status='active'` write. `_init_schema` gains one column (`reminders.source_chat_id`) that lets the scheduler fire group-created reminders back into the originating group. The four approval tools stay LLM-callable but already-existing Python guards now route through `activate()`; the dead `handle_boss_join_decision` regex parser is deleted.

**Tech Stack:** Python 3.12, aiosqlite, httpx, APScheduler, pytest `asyncio_mode = "auto"`.

**Spec:** [docs/superpowers/specs/2026-05-11-relaxed-group-flow-and-approval-cleanup-design.md](../specs/2026-05-11-relaxed-group-flow-and-approval-cleanup-design.md)

---

## File Map

| File | Change |
|------|--------|
| `src/db.py` | ALTER `reminders` to add `source_chat_id TEXT` |
| `src/repositories/reminder_repo.py` | `create()` accepts `source_chat_id`; new getter for routing |
| `src/services/reminder_service.py` | `create_reminder` passes `ctx.chat_id` as `source_chat_id` when `ctx.is_group`; post group summary |
| `src/services/tasks_service.py` | `create_task` posts group summary; drop "không có trong danh sách" warning lines |
| `src/scheduler.py` | Reminder fire routes target → source_group → boss |
| `src/services/membership_service.py` | NEW — `activate()` chokepoint |
| `src/services/join_service.py` | `approve_join` routes write through `activate()` |
| `src/services/people_service.py` | `add_person` LLM tool routes through `activate(source="boss_add")` |
| `src/services/communication_service.py` | `link_contact_to_person` routes through `activate(source="link_contact")`; conflict check for pending-elsewhere |
| `src/onboarding.py` | `_complete_boss` routes through `activate(source="self_boss")`; delete `handle_boss_join_decision` |
| `src/db.py` | `add_person` facade still exists but delegates to `activate()` |
| `src/group_onboarding.py` | Drop the admin precondition in `start()` |
| `src/agent/tool_definitions.py` | Tighten descriptions for the 4 approval tools |
| `tests/unit/test_reminder_source_chat_id.py` | NEW |
| `tests/unit/test_scheduler_reminder_routing.py` | NEW |
| `tests/unit/test_create_task_group_announce.py` | NEW |
| `tests/unit/test_create_reminder_group_announce.py` | NEW |
| `tests/unit/test_create_task_no_warning.py` | NEW |
| `tests/unit/test_membership_service_activate.py` | NEW |
| `tests/unit/test_approve_join_via_activate.py` | NEW |
| `tests/unit/test_add_person_via_activate.py` | NEW |
| `tests/unit/test_link_contact_via_activate.py` | NEW |
| `tests/unit/test_group_onboarding_no_admin_gate.py` | NEW |
| `tests/unit/test_approval_tool_descriptions.py` | NEW |
| `tests/unit/test_handle_boss_join_decision_removed.py` | NEW |
| `tests/unit/test_llm_called_with_history.py` | NEW |

---

## Task 1: Schema — `reminders.source_chat_id`

**Files:**
- Create: `tests/unit/test_reminder_source_chat_id.py`
- Modify: `src/db.py` (near the existing reminders/notes ALTER block)
- Modify: `src/repositories/reminder_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reminder_source_chat_id.py`:

```python
"""reminders.source_chat_id column + repo support."""
from datetime import datetime, timezone

import aiosqlite
import pytest
import pytest_asyncio

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield ReminderRepo(conn)


async def test_reminders_has_source_chat_id(repo):
    async with repo._db.execute("PRAGMA table_info(reminders)") as cur:
        cols = [row[1] async for row in cur]
    assert "source_chat_id" in cols


async def test_create_persists_source_chat_id(repo):
    rid = await repo.create(
        boss_chat_id="b1",
        content="x",
        remind_at=datetime(2026, 5, 11, 10, tzinfo=timezone.utc),
        source_chat_id="group-abc",
    )
    row = await repo.get_by_id(rid)
    assert row["source_chat_id"] == "group-abc"


async def test_create_source_chat_id_optional(repo):
    rid = await repo.create(
        boss_chat_id="b1",
        content="x",
        remind_at=datetime(2026, 5, 11, 10, tzinfo=timezone.utc),
    )
    row = await repo.get_by_id(rid)
    assert row["source_chat_id"] is None
```

- [ ] **Step 2: Run the test — expect failures**

Run: `.venv/bin/pytest tests/unit/test_reminder_source_chat_id.py -v`
Expected: 3 fail — column missing, kwarg unknown.

- [ ] **Step 3: Add the column in `_init_schema`**

Edit `src/db.py`. Find the `Phase 6c forward-compat additions` block (added in the previous spec, around the `lark_record_id` ALTER block). Add a third entry:

```python
    # ---- Phase 6c forward-compat: lark_record_id on reminders/notes ----
    for table, col, definition in [
        ("reminders", "lark_record_id", "TEXT DEFAULT NULL"),
        ("notes",     "lark_record_id", "TEXT DEFAULT NULL"),
        ("reminders", "source_chat_id", "TEXT DEFAULT NULL"),
    ]:
        try:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
```

- [ ] **Step 4: Extend `ReminderRepo.create` and add `_db` access for tests**

Edit `src/repositories/reminder_repo.py`. Replace the `create` method:

```python
    async def create(
        self, boss_chat_id: str, content: str, remind_at: datetime,
        target_chat_id: Optional[str] = None, target_name: str = "",
        source_chat_id: Optional[str] = None,
    ) -> int:
        remind_at_str = remind_at.isoformat(sep=" ", timespec="seconds")
        cur = await self._db.execute(
            "INSERT INTO reminders "
            "(boss_chat_id, target_chat_id, target_name, content, remind_at, source_chat_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(boss_chat_id), target_chat_id, target_name, content, remind_at_str,
             source_chat_id),
        )
        await self._db.commit()
        return cur.lastrowid
```

- [ ] **Step 5: Run the test — expect pass**

Run: `.venv/bin/pytest tests/unit/test_reminder_source_chat_id.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Propagate the new arg through `db.create_reminder` facade**

Edit `src/db.py`. Find `async def create_reminder(...)`. Update to:

```python
async def create_reminder(
    boss_chat_id: str, content: str, remind_at: datetime,
    target_chat_id: Optional[str] = None, target_name: str = "",
    source_chat_id: Optional[str] = None,
    db_path: str = "data/history.db",
) -> int:
    repo: ReminderRepo = await _repo("reminder", ReminderRepo)
    return await repo.create(
        boss_chat_id, content, remind_at, target_chat_id, target_name,
        source_chat_id,
    )
```

- [ ] **Step 7: Commit**

```bash
git add src/db.py src/repositories/reminder_repo.py tests/unit/test_reminder_source_chat_id.py
git commit -m "feat(db): add reminders.source_chat_id column + repo support"
```

---

## Task 2: `reminder_service.create_reminder` persists `source_chat_id` from group ctx

**Files:**
- Modify: `tests/unit/test_reminder_service_sync.py` (append)
- Modify: `src/services/reminder_service.py`

- [ ] **Step 1: Append failing test**

Append to `tests/unit/test_reminder_service_sync.py`:

```python
async def test_create_reminder_persists_source_chat_id_in_group(in_memory_db, monkeypatch):
    """When ctx.is_group is True, source_chat_id = ctx.chat_id."""
    async def _passthrough(fn, **kw):
        return await fn()
    monkeypatch.setattr("src.services.reminder_service.lark.with_retry", _passthrough)
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark",
        AsyncMock(return_value="rec-1"),
    )

    ctx = _ctx()
    object.__setattr__(ctx, "is_group", True)
    object.__setattr__(ctx, "chat_id", "group-xyz")

    await reminder_service.create_reminder(
        ctx, content="standup tomorrow", remind_at="2026-05-12 09:00",
    )

    async with in_memory_db.execute(
        "SELECT source_chat_id FROM reminders WHERE boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["source_chat_id"] == "group-xyz"


async def test_create_reminder_no_source_chat_id_in_dm(in_memory_db, monkeypatch):
    async def _passthrough(fn, **kw):
        return await fn()
    monkeypatch.setattr("src.services.reminder_service.lark.with_retry", _passthrough)
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark",
        AsyncMock(return_value="rec-1"),
    )

    await reminder_service.create_reminder(
        _ctx(), content="ping me", remind_at="2026-05-12 09:00",
    )

    async with in_memory_db.execute(
        "SELECT source_chat_id FROM reminders WHERE boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["source_chat_id"] is None
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_reminder_service_sync.py::test_create_reminder_persists_source_chat_id_in_group tests/unit/test_reminder_service_sync.py::test_create_reminder_no_source_chat_id_in_dm -v`
Expected: 2 FAIL.

- [ ] **Step 3: Modify `create_reminder` in `src/services/reminder_service.py`**

In the `create_reminder` function, find the call to `db.create_reminder(...)`. Change to:

```python
    source_chat_id = str(ctx.chat_id) if ctx.is_group else None
    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=stored_content,
        remind_at=remind_dt,
        target_chat_id=target_chat_id,
        target_name=target_name,
        source_chat_id=source_chat_id,
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_reminder_service_sync.py -v`
Expected: All PASS (4 existing + 2 new = 6 total — adjust depending on Task 5's tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/reminder_service.py tests/unit/test_reminder_service_sync.py
git commit -m "feat(reminder): persist source_chat_id from group ctx"
```

---

## Task 3: Scheduler — route reminder fire to `source_chat_id` when no target

**Files:**
- Create: `tests/unit/test_reminder_destination.py`
- Modify: `src/agent/reminder_agent.py`

Extract destination logic into a pure helper so it can be unit-tested without spinning up the full `send_reminder` LLM + DB path.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reminder_destination.py`:

```python
"""Pure destination logic: target → source_group → boss."""
from src.agent.reminder_agent import _destination_for


def test_target_wins():
    row = {"target_chat_id": "user-xyz", "source_chat_id": "group-abc", "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "user-xyz"
    assert cc_boss is True


def test_source_group_when_no_target():
    row = {"target_chat_id": None, "source_chat_id": "group-abc", "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "group-abc"
    assert cc_boss is False


def test_boss_when_no_target_no_source():
    row = {"target_chat_id": None, "source_chat_id": None, "boss_chat_id": "b1"}
    chat_id, cc_boss = _destination_for(row)
    assert chat_id == "b1"
    assert cc_boss is False
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_reminder_destination.py -v`
Expected: ImportError — `_destination_for` doesn't exist.

- [ ] **Step 3: Add `_destination_for` helper and use it in `send_reminder`**

Open `src/agent/reminder_agent.py`. Just below the imports (before `REMINDER_PROMPT`), add:

```python
def _destination_for(row: dict) -> tuple[str, bool]:
    """Pick the dispatch chat for a reminder row.

    Returns (chat_id, cc_boss_separately).
    Priority: target_chat_id → source_chat_id → boss_chat_id.
    Boss is cc'd only when the reminder went to a specific target person.
    """
    if row.get("target_chat_id"):
        return row["target_chat_id"], True
    if row.get("source_chat_id"):
        return row["source_chat_id"], False
    return row["boss_chat_id"], False
```

Now find the bottom of `send_reminder` (currently lines 135-147):

```python
    if target_id:
        await telegram.send(target_id, reply)
        await db.log_outbound_dm(
            boss_chat_id=boss_chat_id,
            to_chat_id=target_id,
            to_name=target_name or "",
            content=reply,
            trigger_type="reminder",
        )
        # Báo sếp biết đã nhắc (raw, không cần LLM cho dòng này).
        await telegram.send(boss_chat_id, f"✓ Đã nhắc {target_name or 'người nhận'}: {content}")
    else:
        await telegram.send(boss_chat_id, reply)
```

Replace with:

```python
    dest_chat_id, cc_boss = _destination_for(reminder)
    await telegram.send(dest_chat_id, reply)
    if dest_chat_id == target_id:
        await db.log_outbound_dm(
            boss_chat_id=boss_chat_id,
            to_chat_id=target_id,
            to_name=target_name or "",
            content=reply,
            trigger_type="reminder",
        )
    if cc_boss:
        # Raw confirmation back to boss; not via LLM.
        await telegram.send(boss_chat_id, f"✓ Đã nhắc {target_name or 'người nhận'}: {content}")
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_reminder_destination.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent/reminder_agent.py tests/unit/test_reminder_destination.py
git commit -m "feat(scheduler): route reminder fire — target, source_group, boss"
```

---

## Task 4: Announce task / reminder in source group

**Files:**
- Create: `tests/unit/test_create_task_group_announce.py`
- Create: `tests/unit/test_create_reminder_group_announce.py`
- Modify: `src/services/tasks_service.py`
- Modify: `src/services/reminder_service.py`

- [ ] **Step 1: Write failing task announce test**

Create `tests/unit/test_create_task_group_announce.py`:

```python
"""create_task posts a summary into the source group when ctx.is_group."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import tasks_service


def _group_ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="group-xyz", is_group=True, group_name="Test Group",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_create_task_posts_in_group(in_memory_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.tasks_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.lark.search_records",
        AsyncMock(return_value=[]),
    )
    sent = AsyncMock()
    monkeypatch.setattr("src.services.tasks_service.telegram.send", sent)

    await tasks_service.create_task(
        _group_ctx(), name="prepare deck",
        assignee="Lan", deadline="2026-05-15",
    )

    # Find the group post among possibly-multiple sends
    group_calls = [c for c in sent.await_args_list if c.args[0] == "group-xyz"]
    assert group_calls, "no message posted into the source group"
    msg = group_calls[0].args[1]
    assert "prepare deck" in msg
    assert "Lan" in msg
```

- [ ] **Step 2: Write failing reminder announce test**

Create `tests/unit/test_create_reminder_group_announce.py`:

```python
"""create_reminder posts a summary into the source group when ctx.is_group."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import reminder_service


def _group_ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="group-xyz", is_group=True, group_name="Test Group",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_create_reminder_posts_in_group(in_memory_db, monkeypatch):
    async def _passthrough(fn, **kw):
        return await fn()
    monkeypatch.setattr("src.services.reminder_service.lark.with_retry", _passthrough)
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark",
        AsyncMock(return_value="rec-1"),
    )
    sent = AsyncMock()
    monkeypatch.setattr("src.services.reminder_service.telegram.send", sent)

    await reminder_service.create_reminder(
        _group_ctx(), content="standup 9am", remind_at="2026-05-12 09:00",
    )

    group_calls = [c for c in sent.await_args_list if c.args[0] == "group-xyz"]
    assert group_calls, "no message posted into the source group"
    msg = group_calls[0].args[1]
    assert "standup 9am" in msg
```

- [ ] **Step 3: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_create_task_group_announce.py tests/unit/test_create_reminder_group_announce.py -v`
Expected: 2 FAIL — `telegram.send` not called with group id.

- [ ] **Step 4: Add `telegram` import + group post in `tasks_service.create_task`**

Open `src/services/tasks_service.py`. Confirm `from src.channels import telegram_singleton as telegram` is already at top (it is — line 7).

After the `record = await lark.create_record(...)` line in `create_task` (and after the `record_id` assignment), and before the loop building `notification_statuses`, add:

```python
    if ctx.is_group:
        deadline_disp = deadline or "không có deadline"
        assignee_disp = assignee_display or "chưa giao"
        summary = f"Task: {name} → {assignee_disp} | deadline {deadline_disp}"
        try:
            await telegram.send(str(ctx.chat_id), summary, save_history=False)
        except Exception:
            import logging as _logging
            _logging.getLogger("services.tasks").warning(
                "group announce failed for task %s", record_id, exc_info=True,
            )
```

- [ ] **Step 5: Add group post in `reminder_service.create_reminder`**

Open `src/services/reminder_service.py`. Find the `create_reminder` function. At the very end, after the existing return statements, restructure to compute `base` once and post the group summary before returning. Replace the final block (the `try / except` that calls `with_retry` and returns `base` or `base + " (đang chờ đồng bộ Lark)"`) so that the group summary is sent before returning. Concretely:

Find:

```python
    base = (
        f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
        if target_name and target_chat_id
        else f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."
    )

    if not ctx.lark_table_reminders:
        return base
```

Replace with:

```python
    base = (
        f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
        if target_name and target_chat_id
        else f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."
    )

    if ctx.is_group:
        target_disp = target_name or "sếp"
        summary = f"Reminder: {content} for {target_disp} at {remind_at}"
        try:
            await telegram.send(str(ctx.chat_id), summary, save_history=False)
        except Exception:
            import logging as _logging
            _logging.getLogger("services.reminder").warning(
                "group announce failed for reminder %d", reminder_id, exc_info=True,
            )

    if not ctx.lark_table_reminders:
        return base
```

Add at the top of the file if not already present:

```python
from src.channels import telegram_singleton as telegram
```

(Verify by grepping `grep -n "telegram_singleton" src/services/reminder_service.py` — add only if missing.)

- [ ] **Step 6: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_create_task_group_announce.py tests/unit/test_create_reminder_group_announce.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/tasks_service.py src/services/reminder_service.py \
        tests/unit/test_create_task_group_announce.py \
        tests/unit/test_create_reminder_group_announce.py
git commit -m "feat(group): announce new task/reminder in source group"
```

---

## Task 5: Drop the "không có trong danh sách" warning in `create_task`

**Files:**
- Create: `tests/unit/test_create_task_no_warning.py`
- Modify: `src/services/tasks_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_create_task_no_warning.py`:

```python
"""create_task must not return any '⚠️' or 'không có trong danh sách' warning lines."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import tasks_service


def _ctx(boss="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss, boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_create_task_no_warning_for_unknown_assignee(in_memory_db, monkeypatch):
    """Lark People returns empty (assignee not onboarded) → tool result has no warning lines."""
    monkeypatch.setattr(
        "src.services.tasks_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.lark.search_records",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.services.tasks_service.telegram.send", AsyncMock(),
    )

    msg = await tasks_service.create_task(
        _ctx(), name="prepare deck", assignee="Tân",
    )

    assert "⚠️" not in msg
    assert "không có trong danh sách" not in msg
    assert "chưa có tài khoản liên kết" not in msg
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_create_task_no_warning.py -v`
Expected: 1 FAIL — current code returns a `⚠️` line.

- [ ] **Step 3: Modify `create_task` in `src/services/tasks_service.py`**

Locate the per-assignee loop:

```python
    for aname in assignee_list:
        achat_id, found = await _find_assignee_chat_id(ctx, aname)
        if not found:
            notification_statuses.append(f"⚠️ '{aname}' không có trong danh sách nhân sự")
        elif not achat_id:
            notification_statuses.append(f"⚠️ '{aname}' chưa có tài khoản liên kết")
        else:
            ...
```

Replace with:

```python
    for aname in assignee_list:
        achat_id, found = await _find_assignee_chat_id(ctx, aname)
        if achat_id:
            if first_assignee_chat_id is None:
                first_assignee_chat_id = achat_id
            asyncio.create_task(_notify_assignee_task(
                achat_id, name, deadline,
                ctx.sender_name or ctx.boss_name, ctx.boss_chat_id,
            ))
            notification_statuses.append(f"✓ Đã thông báo {aname}")
        # else: silently skip DM. Group announce still happens via Task 4.
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_create_task_no_warning.py tests/unit/test_create_task_group_announce.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/tasks_service.py tests/unit/test_create_task_no_warning.py
git commit -m "feat(tasks): drop assignee-not-found warning; silently skip DM"
```

---

## Task 6: `membership_service.activate()` chokepoint

**Files:**
- Create: `src/services/membership_service.py`
- Create: `tests/unit/test_membership_service_activate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_membership_service_activate.py`:

```python
"""activate() is the single chokepoint for status='active' membership writes."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.services import membership_service


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token,"
        " lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme Co", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_activate_writes_active_membership(setup_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    monkeypatch.setattr(
        "src.services.membership_service.telegram.send", AsyncMock(),
    )
    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    async with setup_db.execute(
        "SELECT status FROM memberships WHERE chat_id='u1' AND boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "active"


async def test_activate_notifies_only_on_pending_transition(setup_db, monkeypatch):
    """When prior row was pending → notify. When prior row didn't exist → no notify."""
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    sent = AsyncMock()
    monkeypatch.setattr("src.services.membership_service.telegram.send", sent)

    # Case A: no prior row → no notification
    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    assert sent.await_count == 0

    # Case B: prior pending row → notification
    await setup_db.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) "
        "VALUES ('u2', 'b1', 'member', 'Bob', 'pending')"
    )
    await setup_db.commit()
    await membership_service.activate(
        chat_id="u2", boss_chat_id="b1",
        person_type="member", name="Bob",
        source="approval",
    )
    assert sent.await_count == 1
    notify_args = sent.await_args.args
    assert notify_args[0] == "u2"
    assert "approved" in notify_args[1].lower() or "Acme Co" in notify_args[1]


async def test_activate_upserts_lark_people_when_no_record_id(setup_db, monkeypatch):
    create_mock = AsyncMock(return_value={"record_id": "lark-new"})
    monkeypatch.setattr("src.services.membership_service.lark.create_record", create_mock)
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())

    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    create_mock.assert_awaited_once()
    fields = create_mock.await_args.args[2]
    assert fields["Tên"] == "Alice"
    assert fields["Type"] == "member"


async def test_activate_skips_lark_when_record_id_provided(setup_db, monkeypatch):
    create_mock = AsyncMock()
    monkeypatch.setattr("src.services.membership_service.lark.create_record", create_mock)
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())

    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="approval",
        lark_record_id="existing-rec",
    )
    create_mock.assert_not_awaited()


async def test_activate_emits_audit_log(setup_db, monkeypatch, caplog):
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())
    with caplog.at_level("INFO"):
        await membership_service.activate(
            chat_id="u1", boss_chat_id="b1",
            person_type="member", name="Alice",
            source="boss_add",
        )
    audit_lines = [r for r in caplog.records if "membership.activate" in r.message]
    assert audit_lines
    assert "boss_add" in audit_lines[0].message
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_membership_service_activate.py -v`
Expected: All fail — module does not exist.

- [ ] **Step 3: Create `src/services/membership_service.py`**

```python
"""Single chokepoint for `memberships.status='active'` writes.

Every code path that needs to grant active membership goes through `activate()`.
No other module should call `repo.upsert(..., status='active')` directly."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from src import db
from src.channels import telegram_singleton as telegram
from src.infrastructure import lark_client as lark
from src.repositories.membership_repo import MembershipRepo

logger = logging.getLogger("services.membership")

Source = Literal["approval", "boss_add", "self_boss", "link_contact"]


async def activate(
    *,
    chat_id: str,
    boss_chat_id: str,
    person_type: str,
    name: str,
    source: Source,
    lark_record_id: Optional[str] = None,
    request_info: Optional[str] = None,
) -> None:
    """Promote a person to active membership in a workspace. Single write path.

    - If the prior row was status='pending', send the approved-user
      notification regardless of `source` (semantically an approval).
    - Upsert Lark People if `lark_record_id` is None.
    - Emit one audit log line tagged with `source`.
    """
    _db = await db.get_db()
    repo = MembershipRepo(_db)

    prior = await repo.get(str(chat_id), str(boss_chat_id))
    was_pending = bool(prior and prior.get("status") == "pending")

    # Upsert Lark People when no record id is supplied.
    rec_id = lark_record_id
    if not rec_id:
        boss = await db.get_boss(str(boss_chat_id))
        if boss and boss.get("lark_base_token") and boss.get("lark_table_people"):
            ext = await db.lookup_external_for_person(chat_id)
            chat_id_for_lark = int(ext[1]) if ext and ext[1].isdigit() else 0
            fields = {
                "Tên": name,
                "Chat ID": chat_id_for_lark,
                "Type": person_type,
                "Ghi chú": request_info or "",
            }
            try:
                created = await lark.create_record(
                    boss["lark_base_token"], boss["lark_table_people"], fields,
                )
                rec_id = created.get("record_id", "")
            except Exception:
                logger.warning(
                    "lark People upsert failed for chat_id=%s", chat_id, exc_info=True,
                )

    await repo.upsert(
        str(chat_id), str(boss_chat_id), person_type, name,
        status="active", request_info=request_info, lark_record_id=rec_id,
    )

    if was_pending:
        boss = await db.get_boss(str(boss_chat_id))
        company = (boss or {}).get("company") or (boss or {}).get("name", "the workspace")
        try:
            await telegram.send(
                str(chat_id),
                f"Your request to join {company} has been approved as {person_type}. "
                f"You can now interact with the AI secretary.",
            )
        except Exception:
            logger.warning(
                "approved-user notification failed for chat_id=%s", chat_id, exc_info=True,
            )

    logger.info(
        "membership.activate source=%s chat_id=%s boss=%s type=%s",
        source, chat_id, boss_chat_id, person_type,
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_membership_service_activate.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/membership_service.py tests/unit/test_membership_service_activate.py
git commit -m "feat(membership): add activate() chokepoint for active-status writes"
```

---

## Task 7: Migrate `approve_join` and `_complete_boss` to `activate()`

**Files:**
- Create: `tests/unit/test_approve_join_via_activate.py`
- Modify: `src/services/join_service.py`
- Modify: `src/onboarding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_approve_join_via_activate.py`:

```python
"""approve_join must call membership_service.activate(source='approval')."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import join_service


def _boss_ctx(boss_id="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss_id, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss_id, boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss_id, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status, request_info) "
        "VALUES ('u1', 'b1', 'member', 'Alice', 'pending', 'Hi please add')"
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_approve_join_routes_through_activate(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.join_service.membership_service.activate", activate_mock,
    )

    result = await join_service.approve_join(
        _boss_ctx(), membership_chat_id="u1",
    )
    activate_mock.assert_awaited_once()
    kwargs = activate_mock.await_args.kwargs
    assert kwargs["chat_id"] == "u1"
    assert kwargs["boss_chat_id"] == "b1"
    assert kwargs["source"] == "approval"
    assert kwargs["person_type"] == "member"
    assert "Approved" in result


async def test_approve_join_refuses_when_no_pending(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.join_service.membership_service.activate", activate_mock,
    )
    result = await join_service.approve_join(
        _boss_ctx(), membership_chat_id="does-not-exist",
    )
    activate_mock.assert_not_awaited()
    assert "No pending" in result
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_approve_join_via_activate.py -v`
Expected: 1 FAIL (`test_approve_join_routes_through_activate`); the other may pass because the existing pending check already covers it.

- [ ] **Step 3: Modify `approve_join` in `src/services/join_service.py`**

Replace the body after the pending check so it delegates to `activate()`:

```python
async def approve_join(ctx: ChatContext, membership_chat_id: str, role: str = None) -> str:
    """Approve a join request. Routes the write through membership_service.activate()."""
    from src.services import membership_service

    _db = await db.get_db()
    membership = await db.get_membership(_db, str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    person_type = role or membership["person_type"]
    name = membership["name"] or "Unknown"
    request_info = membership.get("request_info", "")

    await membership_service.activate(
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=person_type,
        name=name,
        source="approval",
        request_info=request_info,
    )

    company = ctx.boss_name
    return f"Approved {name} as {person_type} in {company}."
```

- [ ] **Step 4: Migrate `_complete_boss` in `src/onboarding.py` to `activate()`**

Locate `_complete_boss` (around line 120). Find the call to `db.add_person(person_id, chat_id, "boss", name)`. Replace with:

```python
    from src.services import membership_service
    await membership_service.activate(
        chat_id=person_id,
        boss_chat_id=chat_id,
        person_type="boss",
        name=name,
        source="self_boss",
    )
```

- [ ] **Step 5: Run the test**

Run: `.venv/bin/pytest tests/unit/test_approve_join_via_activate.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/join_service.py src/onboarding.py tests/unit/test_approve_join_via_activate.py
git commit -m "feat(membership): route approve_join and self-boss onboarding through activate()"
```

---

## Task 8: Migrate `add_person` and `link_contact_to_person`

**Files:**
- Create: `tests/unit/test_add_person_via_activate.py`
- Create: `tests/unit/test_link_contact_via_activate.py`
- Modify: `src/services/people_service.py`
- Modify: `src/services/communication_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_add_person_via_activate.py`:

```python
"""people_service.add_person routes the membership write through activate(source='boss_add')."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import people_service


def _ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="b1", is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_add_person_routes_through_activate(setup_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.people_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.people_service.membership_service.activate", activate_mock,
    )

    await people_service.add_person(
        _ctx(), name="Alice", chat_id="u1", person_type="member",
    )

    activate_mock.assert_awaited_once()
    assert activate_mock.await_args.kwargs["source"] == "boss_add"
    assert activate_mock.await_args.kwargs["chat_id"] == "u1"


async def test_add_person_without_chat_id_skips_activate(setup_db, monkeypatch):
    """If no chat_id supplied, only Lark write happens — no membership write."""
    monkeypatch.setattr(
        "src.services.people_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.people_service.membership_service.activate", activate_mock,
    )
    await people_service.add_person(
        _ctx(), name="External Partner", person_type="partner",
    )
    activate_mock.assert_not_awaited()
```

Create `tests/unit/test_link_contact_via_activate.py`:

```python
"""link_contact_to_person routes through activate(source='link_contact').
Conflict check: if the chat_id has a pending row in a different workspace, refuse."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import communication_service


def _ctx(boss="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss, boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_link_contact_routes_through_activate(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.communication_service.membership_service.activate",
        activate_mock,
    )
    monkeypatch.setattr(
        "src.services.communication_service.lark.search_records",
        AsyncMock(return_value=[{
            "record_id": "lark-1", "Tên": "Alice", "Type": "member",
        }]),
    )
    monkeypatch.setattr(
        "src.services.communication_service.lark.update_record", AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.communication_service.db.resolve_or_create_person",
        AsyncMock(return_value="u-internal"),
    )
    monkeypatch.setattr(
        "src.services.communication_service._workspace_helper.resolve_workspaces",
        AsyncMock(return_value=[{
            "lark_base_token": "base", "lark_table_people": "ppl",
            "boss_id": "b1", "workspace_name": "Acme",
        }]),
    )

    await communication_service.link_contact_to_person(
        _ctx(), chat_id="12345", lark_record_id="lark-1",
    )

    activate_mock.assert_awaited_once()
    assert activate_mock.await_args.kwargs["source"] == "link_contact"


async def test_link_contact_refuses_when_pending_elsewhere(setup_db, monkeypatch):
    """Person has a pending membership in another workspace → CONFLICT, no activate call."""
    await setup_db.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) "
        "VALUES ('u-internal', 'OTHER_BOSS', 'member', 'Alice', 'pending')"
    )
    await setup_db.commit()
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.communication_service.membership_service.activate",
        activate_mock,
    )
    monkeypatch.setattr(
        "src.services.communication_service.lark.search_records",
        AsyncMock(return_value=[{
            "record_id": "lark-1", "Tên": "Alice", "Type": "member",
        }]),
    )
    monkeypatch.setattr(
        "src.services.communication_service.lark.update_record", AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.communication_service.db.resolve_or_create_person",
        AsyncMock(return_value="u-internal"),
    )
    monkeypatch.setattr(
        "src.services.communication_service._workspace_helper.resolve_workspaces",
        AsyncMock(return_value=[{
            "lark_base_token": "base", "lark_table_people": "ppl",
            "boss_id": "b1", "workspace_name": "Acme",
        }]),
    )

    result = await communication_service.link_contact_to_person(
        _ctx(), chat_id="12345", lark_record_id="lark-1",
    )
    activate_mock.assert_not_awaited()
    assert "CONFLICT" in result or "pending" in result.lower()
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_add_person_via_activate.py tests/unit/test_link_contact_via_activate.py -v`
Expected: 4 fail.

- [ ] **Step 3: Modify `people_service.add_person`**

Open `src/services/people_service.py`. Locate the `if chat_id and ctx.boss_chat_id:` block (around line 83) which calls `db.add_person(...)`. Replace with:

```python
    if chat_id and ctx.boss_chat_id:
        from src.services import membership_service
        # Resolve external → internal id (chat_id arg is external Telegram numeric).
        internal_id = await db.resolve_or_create_person(
            "telegram", str(chat_id), name, "",
        )
        await membership_service.activate(
            chat_id=internal_id,
            boss_chat_id=str(ctx.boss_chat_id),
            person_type=person_type,
            name=name,
            source="boss_add",
            lark_record_id=None,  # Lark People row already created above; activate will skip.
        )
```

Note: the existing code calls `lark.create_record` for People before this block (creates the Lark row). To prevent `activate()` from creating a *second* Lark row, we need to capture the record id and pass it. Adjust the earlier call:

Replace `await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)` with:

```python
    lark_rec = await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)
    lark_record_id = lark_rec.get("record_id", "")
```

And in the activate call use `lark_record_id=lark_record_id or None`.

- [ ] **Step 4: Modify `communication_service.link_contact_to_person`**

Open `src/services/communication_service.py`. Locate the `# Also insert membership` block (around line 417). Replace the `db.add_person(...)` call with:

```python
    # Resolve external → internal id.
    internal_person_id = await db.resolve_or_create_person(
        "telegram", str(chat_id), name, "",
    )

    # Conflict check: pending membership in a DIFFERENT workspace must be approved
    # via the proper flow, not silently activated here.
    _db = await db.get_db()
    async with _db.execute(
        "SELECT boss_chat_id FROM memberships "
        "WHERE chat_id = ? AND status = 'pending' AND boss_chat_id != ?",
        (internal_person_id, str(ctx.boss_chat_id)),
    ) as cur:
        pending_elsewhere = await cur.fetchone()
    if pending_elsewhere:
        return (
            f"[CONFLICT] Contact has a pending join request in workspace "
            f"{pending_elsewhere[0]}. Use the approval flow there instead."
        )

    from src.services import membership_service
    try:
        await membership_service.activate(
            chat_id=internal_person_id,
            boss_chat_id=str(ctx.boss_chat_id),
            person_type=person_type,
            name=name,
            source="link_contact",
            lark_record_id=lark_record_id,
        )
    except Exception:
        logger.warning("link_contact_to_person: activate failed", exc_info=True)
```

- [ ] **Step 5: Remove `db.add_person` body so nothing else can sneak through**

Open `src/db.py`. Replace the `add_person` function (around line 514) with:

```python
async def add_person(
    chat_id: str, boss_chat_id: str, person_type: str, name: str = "",
    db_path: str = "data/history.db",
) -> None:
    """Legacy facade. New code must call `services.membership_service.activate()` directly."""
    from src.services import membership_service
    await membership_service.activate(
        chat_id=str(chat_id),
        boss_chat_id=str(boss_chat_id),
        person_type=person_type,
        name=name or "",
        source="boss_add",
    )
```

This keeps any legacy import working while routing the write through the chokepoint.

- [ ] **Step 6: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_add_person_via_activate.py tests/unit/test_link_contact_via_activate.py tests/unit/test_approve_join_via_activate.py tests/unit/test_membership_service_activate.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add src/services/people_service.py src/services/communication_service.py src/db.py \
        tests/unit/test_add_person_via_activate.py tests/unit/test_link_contact_via_activate.py
git commit -m "feat(membership): route add_person and link_contact through activate()"
```

---

## Task 9: Drop the admin gate in `group_onboarding.start()`

**Files:**
- Create: `tests/unit/test_group_onboarding_no_admin_gate.py`
- Modify: `src/group_onboarding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_group_onboarding_no_admin_gate.py`:

```python
"""group_onboarding.start must not refuse based on bot admin status."""
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.group_onboarding as group_onboarding


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_start_continues_when_bot_not_admin(setup_db, monkeypatch):
    """Bot status is 'member' (not admin) → onboarding still picks up; no early return
    that asks the user to promote the bot."""
    monkeypatch.setattr(group_onboarding.telegram, "get_bot_id", AsyncMock(return_value="bot-1"))
    monkeypatch.setattr(
        group_onboarding.telegram, "get_chat_member",
        AsyncMock(return_value={"status": "member"}),
    )
    send_mock = AsyncMock()
    monkeypatch.setattr(group_onboarding, "_send_and_save", send_mock)

    await group_onboarding.start("group-xyz", "sender-1")

    # Must NOT send the "promote me to admin" message
    for call in send_mock.await_args_list:
        msg = call.args[1] if len(call.args) > 1 else ""
        assert "Administrator" not in msg, f"unexpected admin prompt: {msg}"
    # Must reach the workspace-selection prompt
    msgs = [c.args[1] for c in send_mock.await_args_list if len(c.args) > 1]
    assert any("workspace" in m.lower() or "thuộc workspace" in m for m in msgs), \
        f"workspace prompt missing; sent: {msgs}"
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_group_onboarding_no_admin_gate.py -v`
Expected: FAIL — the admin guard sends the "promote to admin" message and returns.

- [ ] **Step 3: Remove the admin gate in `src/group_onboarding.py`**

Locate `async def start(...)` (around line 165). Replace the body from `bot_id = await telegram.get_bot_id()` through the `return` (lines 167-178) with simply:

```python
async def start(group_chat_id: str, sender_id: str) -> None:
    """Entry point — begin workspace selection. Admin rights are optional; if the bot
    lacks them, admin-only operations will degrade gracefully at the channel layer."""
    bosses = await db.get_all_bosses()
    if not bosses:
        await _send_and_save(
            group_chat_id,
            "Chưa có workspace nào được đăng ký. Nhờ sếp đăng ký với bot trước nhé.",
        )
        return

    lines = ["Nhóm này thuộc workspace nào?\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} (sếp: {b['name']})")
    await _send_and_save(group_chat_id, "\n".join(lines))

    await db.save_onboarding_state(group_chat_id, {
        "step": "collecting",
```

(The `save_onboarding_state` call continues with its existing body; do not delete anything past the start function.)

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_group_onboarding_no_admin_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/group_onboarding.py tests/unit/test_group_onboarding_no_admin_gate.py
git commit -m "feat(group): drop admin precondition; onboarding works without bot admin"
```

---

## Task 10: Tighten approval tool descriptions

**Files:**
- Create: `tests/unit/test_approval_tool_descriptions.py`
- Modify: `src/agent/tool_definitions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_approval_tool_descriptions.py`:

```python
"""Approval-tool descriptions must communicate the gate to the LLM."""
from src.agent.tool_definitions import TOOL_DEFINITIONS


def _desc(name: str) -> str:
    for t in TOOL_DEFINITIONS:
        fn = t.get("function", {})
        if fn.get("name") == name:
            return fn.get("description", "")
    raise AssertionError(f"tool {name} not in TOOL_DEFINITIONS")


def test_approve_join_description_mentions_pending_and_boss():
    d = _desc("approve_join").lower()
    assert "pending" in d
    assert "only" in d or "must" in d  # explicit conditional wording


def test_reject_join_description_mentions_pending_and_boss():
    d = _desc("reject_join").lower()
    assert "pending" in d


def test_approve_task_change_description_mentions_pending():
    d = _desc("approve_task_change").lower()
    assert "pending" in d


def test_reject_task_change_description_mentions_pending():
    d = _desc("reject_task_change").lower()
    assert "pending" in d
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_approval_tool_descriptions.py -v`
Expected: 4 fail.

- [ ] **Step 3: Rewrite the four tool descriptions in `src/agent/tool_definitions.py`**

Find the four tool definitions (`approve_join`, `reject_join`, `approve_task_change`, `reject_task_change`) and replace each `description` field as follows:

```python
# approve_join
"description": (
    "Activate a pending join request as the boss of THIS workspace. Only call when "
    "the boss is replying to an approval prompt AND the supplied membership_chat_id "
    "matches an existing pending row in this workspace. The function refuses (no "
    "write) if no matching pending row exists."
),
```

```python
# reject_join
"description": (
    "Reject a pending join request as the boss of THIS workspace. Only call when "
    "the boss is replying to an approval prompt AND the supplied membership_chat_id "
    "matches an existing pending row. The function refuses (no write) if no "
    "matching pending row exists."
),
```

```python
# approve_task_change
"description": (
    "Approve a pending task-change request. Only call when the boss is replying to "
    "an approval prompt AND the supplied approval_id matches an existing pending "
    "task-change row in this workspace. The function refuses (no write) if no "
    "matching pending row exists."
),
```

```python
# reject_task_change
"description": (
    "Reject a pending task-change request. Only call when the boss is replying to "
    "an approval prompt AND the supplied approval_id matches an existing pending "
    "task-change row in this workspace. The function refuses (no write) if no "
    "matching pending row exists."
),
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_approval_tool_descriptions.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent/tool_definitions.py tests/unit/test_approval_tool_descriptions.py
git commit -m "feat(tools): tighten approval-tool descriptions with explicit preconditions"
```

---

## Task 11: Delete `handle_boss_join_decision`

**Files:**
- Create: `tests/unit/test_handle_boss_join_decision_removed.py`
- Modify: `src/onboarding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_handle_boss_join_decision_removed.py`:

```python
"""handle_boss_join_decision is dead code (regex parser) and must be removed."""
import pytest

import src.onboarding as onboarding


def test_handle_boss_join_decision_attribute_gone():
    assert not hasattr(onboarding, "handle_boss_join_decision"), (
        "handle_boss_join_decision must be removed; "
        "approval flow is handled by the LLM tools (see §2.3 of the spec)."
    )
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/unit/test_handle_boss_join_decision_removed.py -v`
Expected: FAIL — attribute still exists.

- [ ] **Step 3: Delete `handle_boss_join_decision` from `src/onboarding.py`**

Remove the entire `async def handle_boss_join_decision(...)` function (starts around line 423). The function has zero callers (verified by grep). Remove it cleanly.

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/unit/test_handle_boss_join_decision_removed.py -v`
Expected: PASS.

- [ ] **Step 5: Run full unit suite to confirm no regression**

Run: `.venv/bin/pytest tests/unit -q --tb=short`
Expected: All PASS except the 4 pre-existing failures in `tests/unit/test_context.py` (string vs int — unrelated).

- [ ] **Step 6: Commit**

```bash
git add src/onboarding.py tests/unit/test_handle_boss_join_decision_removed.py
git commit -m "feat(onboarding): delete dead handle_boss_join_decision regex parser"
```

---

## Task 12: History-context regression guard

**Files:**
- Create: `tests/unit/test_llm_called_with_history.py`

- [ ] **Step 1: Write the regression test**

Create `tests/unit/test_llm_called_with_history.py`:

```python
"""Regression guard: any LLM call from secretary_agent must include recent message history.

This is a structural rule (see feedback_message_semantics.md). Future refactors that
strip history from the prompt break this test."""
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) "
        "VALUES ('b1', 'b1', 'boss', 'Boss', 'active')"
    )
    # Seed a few prior messages so history exists to be included.
    for role, text in [
        ("user", "first msg"),
        ("assistant", "ack"),
        ("user", "second msg"),
        ("assistant", "ack2"),
    ]:
        await conn.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) "
            "VALUES ('b1', ?, ?, datetime('now'))", (role, text),
        )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_secretary_agent_includes_history_in_llm_call(setup_db, monkeypatch):
    """secretary_agent.handle_message → llm.chat_with_tools is called with messages
    list that contains at least 2 of the seeded prior turns."""
    from src.agent import secretary_agent
    from src.config import Settings

    # Stub out everything that would do I/O so we only observe the prompt.
    chat_mock = AsyncMock(return_value=(MagicMock(content="hi", tool_calls=[]), {}))
    fake_llm = MagicMock()
    fake_llm.chat_with_tools = chat_mock
    fake_llm.embed = AsyncMock(return_value=([0.0] * 4, 4))
    fake_llm.embedding_dim = 4

    monkeypatch.setattr(
        "src.agent.secretary_agent.get_llm_for_ctx",
        AsyncMock(return_value=fake_llm),
    )
    monkeypatch.setattr(
        "src.agent.secretary_agent.telegram.send",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "src.agent.secretary_agent.qdrant.upsert", AsyncMock(),
    )
    monkeypatch.setattr(
        "src.agent.secretary_agent.qdrant.search", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(secretary_agent, "_settings", Settings())

    await secretary_agent.handle_message(
        "third msg", chat_id="b1", sender_id="b1",
        is_group=False, bot_mentioned=False,
    )

    chat_mock.assert_awaited()
    messages = chat_mock.await_args.args[0]
    # At least 2 of the seeded "first msg" / "second msg" lines should appear.
    text_blob = "\n".join(
        (m.get("content") or "") if isinstance(m, dict) else "" for m in messages
    )
    assert "first msg" in text_blob or "second msg" in text_blob, (
        "secretary_agent must include recent message history in the LLM prompt; "
        f"got: {text_blob[:500]}"
    )
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/unit/test_llm_called_with_history.py -v`

Expected: PASS (current code already includes history via `_build_turn_messages` → `db.get_recent`). If it fails, that means the regression already exists and must be repaired by ensuring `_build_turn_messages` reads recent messages from `db.get_recent` and prepends them to the LLM call.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_llm_called_with_history.py
git commit -m "test(agent): regression guard — LLM call must include recent history"
```

---

## Task 13: Final full-suite + Docker smoke

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite green**

Run: `.venv/bin/pytest tests/unit -q --tb=short`
Expected: All PASS except the 4 pre-existing failures in `tests/unit/test_context.py`. Verify the count matches (162 passing before this branch + 30-ish new = around 192 passing). Confirm no new failure beyond those four.

- [ ] **Step 2: Docker rebuild**

`src/` is `COPY`'d into the image at build time — `restart` alone does not pick up code changes (see memory). Run:

```bash
docker compose up -d --build app
```

Wait for the `app` service to report healthy.

- [ ] **Step 3: Tail logs and run the 5 scenarios from the spec**

In one terminal:

```bash
docker compose logs -f app | head -200
```

In Telegram or your active channel:

1. From a group where the bot is **not** admin, send `@bot nhắc anh Tân chiếu thứ 3 lúc 14h họp marketing`. The bot must accept (no "promote me to admin" message), create the reminder in Lark, and post a summary back in the group. Anh Tân has no Lark People row → the bot must not produce an `⚠️` warning.
2. Wait until the reminder fires (or shorten the time on a test row). The reminder text appears in the same group, not the boss DM.
3. From a DM, ask the bot to join workspace B (the bot you are not yet in). Bot calls `request_join`; bot B's boss is notified. The user does not get auto-granted.
4. As bot B's boss, reply naturally (`"ok duyệt nhé"` or `"approve abc-XXX"` where the id is wrong). For the natural reply, the LLM understands and calls `approve_join` → guard passes → membership becomes active. For the wrong id, the guard returns the refusal string.
5. From the boss DM, ask `"thêm Anh Quân làm partner, chat_id 12345"`. The `add_person` tool runs → routes through `activate(source="boss_add")` → membership is active.

Spot-check `data/history.db` after a couple of scenarios:

```bash
docker compose exec app sqlite3 /app/data/history.db \
    "SELECT chat_id, boss_chat_id, person_type, status FROM memberships;"
```

Each active row should correspond to a scenario you ran; no rows should be active that you did not approve.

- [ ] **Step 4: Inspect logs for unexpected warnings**

Look for these patterns in the docker log output. None should appear during a healthy run:

- `membership.activate` lines should appear with the correct `source=` tag — one per scenario above.
- No `Lark sync failed`, `reconcile push failed`, `bad time`, `hard cap`.
- No raised exception from `UnsupportedOperation` (any admin-only call attempt should swallow and log a single warning line, not crash).

- [ ] **Step 5: No commit needed**

Smoke test produces no code changes. If a scenario fails, file a follow-up or revert specific commits.

---

## Self-review notes

- Every spec section maps to a task: §1.1→T9, §1.2→T5 (warning) + part of T4 (announce), §1.3→T4, §1.4→T1+T2+T3, §2.1→T6+T7+T8, §2.2→T10, §2.3→T10+T11+T12, §2.4→T8.
- All steps reference exact file paths and replacements; no `TODO` or `TBD`.
- Function and tool names used across tasks match (e.g., `activate(source=…)`, `_find_assignee_chat_id`, `handle_boss_join_decision`).
- Tests use `pytest_asyncio` fixtures with in-memory `aiosqlite` + `_init_schema`, matching the established codebase pattern.
- Schema migration follows the existing `bosses` ALTER convention with the duplicate-column try/except guard.
- Tombstoning is not needed in this spec (the previous Lark-sync-hardening spec already handled it).
