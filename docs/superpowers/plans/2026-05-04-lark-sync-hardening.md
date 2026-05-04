# Lark Sync Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close DB↔Lark drift gaps for reminders and notes. Every write path inline-awaits Lark with retry. Reverse sync detects manual Lark edits (time changes, additions, deletions). `search_records` paginates instead of silently capping at 100.

**Architecture:**
- **Outbound** (DB → Lark): switch fire-and-forget `asyncio.create_task` to `await with_retry(...)`. Persist `lark_record_id` in DB after success so we can identify rows still pending sync.
- **Reverse-sync** (Lark → DB): existing `_sync_lark_to_sqlite` extends to: pull `Thời gian nhắc` time edits, pull rows lacking `SQLite ID` (manual additions), tombstone DB rows whose Lark counterpart vanished, reconcile DB rows with `lark_record_id IS NULL`.
- **Pagination**: `search_records` loops `page_token` until `has_more=false`, hard-capped at 5000 rows.
- **Conflict policy**: Lark wins.

**Tech Stack:** Python 3.12, aiosqlite, httpx, APScheduler, pytest with `asyncio_mode = "auto"`.

**Spec:** [docs/superpowers/specs/2026-05-04-lark-sync-hardening-design.md](../specs/2026-05-04-lark-sync-hardening-design.md)

---

## File Map

| File | Change |
|------|--------|
| `src/infrastructure/lark_client.py` | Add `with_retry()` helper, paginate `search_records()` |
| `src/db.py` | ALTER `reminders` and `notes` to add `lark_record_id TEXT`; add facade methods |
| `src/repositories/reminder_repo.py` | New methods: `set_lark_record_id`, `get_by_id`, `find_by_lark_id`, `list_unsynced_pending`, `list_with_lark_id`, `tombstone`, `update_remind_at_and_content` |
| `src/repositories/note_repo.py` | Modify `upsert` to return id; new methods: `set_lark_record_id`, `find_by_lark_id`, `list_unsynced`, `list_with_lark_id`, `delete_by_id`, `get_by_id` |
| `src/services/reminder_service.py` | `create_reminder` / `update_reminder` / `delete_reminder` all inline-await Lark + persist `lark_record_id` |
| `src/services/note_service.py` | `update_note` and `append_note` await `sync_note_to_lark`; persist `lark_record_id` |
| `src/scheduler.py` | Extend `_sync_lark_to_sqlite`: reminders block adds time-edit + manual-add + tombstone + reconcile; new notes block runs every 5 min |
| `tests/unit/test_lark_pagination.py` | NEW |
| `tests/unit/test_lark_with_retry.py` | NEW |
| `tests/unit/test_lark_record_id_columns.py` | NEW |
| `tests/unit/test_reminder_repo_lark_id.py` | NEW |
| `tests/unit/test_note_repo_lark_id.py` | NEW |
| `tests/unit/test_reminder_service_sync.py` | NEW |
| `tests/unit/test_note_service_sync.py` | NEW |
| `tests/unit/test_scheduler_reverse_sync_reminders.py` | NEW |
| `tests/unit/test_scheduler_reverse_sync_notes.py` | NEW |

---

## Task 1: Paginate `lark_client.search_records`

**Files:**
- Create: `tests/unit/test_lark_pagination.py`
- Modify: `src/infrastructure/lark_client.py:237-252`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_lark_pagination.py`:

```python
"""search_records must paginate using page_token until has_more=false."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.infrastructure.lark_client as lark


def _resp(items, has_more=False, page_token=None):
    body = {
        "code": 0,
        "data": {
            "items": [{"record_id": rid, "fields": fields} for rid, fields in items],
            "has_more": has_more,
            "page_token": page_token,
        },
    }
    r = MagicMock()
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


async def test_search_records_returns_all_pages():
    page1 = _resp([("r1", {"a": 1}), ("r2", {"a": 2})], has_more=True, page_token="p2")
    page2 = _resp([("r3", {"a": 3})], has_more=False)

    client = MagicMock()
    client.get = AsyncMock(side_effect=[page1, page2])
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"):
        rows = await lark.search_records("base", "tbl")

    assert [r["record_id"] for r in rows] == ["r1", "r2", "r3"]
    assert client.get.call_count == 2
    second_call_params = client.get.call_args_list[1].kwargs["params"]
    assert second_call_params.get("page_token") == "p2"


async def test_search_records_stops_on_hard_cap(caplog):
    # 11 pages of 500 — caller must receive 5000 then stop with a warning.
    pages = [
        _resp([(f"r{p}-{i}", {}) for i in range(500)], has_more=True, page_token=f"p{p+1}")
        for p in range(11)
    ]
    client = MagicMock()
    client.get = AsyncMock(side_effect=pages)
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"), \
         caplog.at_level("WARNING"):
        rows = await lark.search_records("base", "tbl")

    assert len(rows) == 5000
    assert any("hard cap" in rec.message.lower() for rec in caplog.records)


async def test_search_records_single_page_no_token():
    page = _resp([("r1", {"x": 1})], has_more=False)
    client = MagicMock()
    client.get = AsyncMock(return_value=page)
    with patch.object(lark, "_client", client), \
         patch.object(lark, "_get_token", new_callable=AsyncMock, return_value="tok"):
        rows = await lark.search_records("base", "tbl")

    assert rows == [{"record_id": "r1", "x": 1}]
    assert client.get.call_count == 1
    first_params = client.get.call_args.kwargs["params"]
    assert "page_token" not in first_params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_lark_pagination.py -v`

Expected: All three fail. `test_search_records_returns_all_pages` will see only 2 rows (page 1) and `client.get.call_count == 1`.

- [ ] **Step 3: Implement pagination**

Edit `src/infrastructure/lark_client.py`. Replace the `search_records` function (currently around lines 237–252) with:

```python
import logging  # add at top of file if not present

_HARD_CAP = 5000
_logger = logging.getLogger("infrastructure.lark")


async def search_records(base_token: str, table_id: str, filter_expr: str = "") -> list[dict]:
    items: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        resp = await _client.get(
            f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
            headers=await _headers(),
            params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
        data = body.get("data", {})
        for r in data.get("items") or []:
            items.append({"record_id": r["record_id"], **r["fields"]})
        if len(items) >= _HARD_CAP:
            _logger.warning(
                "search_records: hit hard cap %d for table %s — additional rows ignored",
                _HARD_CAP, table_id,
            )
            break
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break
    return items
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_lark_pagination.py -v`

Expected: 3 PASS. Also run existing tests to confirm no regression: `uv run pytest tests/unit/test_lark_provision.py -v`.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_lark_pagination.py src/infrastructure/lark_client.py
git commit -m "feat(lark): paginate search_records with hard cap"
```

---

## Task 2: `with_retry` helper for transient Lark failures

**Files:**
- Create: `tests/unit/test_lark_with_retry.py`
- Modify: `src/infrastructure/lark_client.py` (add helper near top of CRUD section)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_lark_with_retry.py`:

```python
"""with_retry retries httpx network errors and HTTP 5xx; never retries Lark business errors."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.infrastructure.lark_client as lark


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://x.test")
    resp = httpx.Response(status, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


async def test_with_retry_recovers_on_5xx():
    fn = AsyncMock(side_effect=[_http_error(503), "ok"])
    result = await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert result == "ok"
    assert fn.call_count == 2


async def test_with_retry_retries_network_error():
    fn = AsyncMock(side_effect=[httpx.ConnectError("boom"), "ok"])
    result = await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert result == "ok"


async def test_with_retry_does_not_retry_business_error():
    fn = AsyncMock(side_effect=Exception("Lark error: 1254 - permission denied"))
    with pytest.raises(Exception, match="Lark error"):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert fn.call_count == 1


async def test_with_retry_does_not_retry_4xx():
    fn = AsyncMock(side_effect=_http_error(403))
    with pytest.raises(httpx.HTTPStatusError):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    assert fn.call_count == 1


async def test_with_retry_gives_up_after_attempts():
    fn = AsyncMock(side_effect=[_http_error(503), _http_error(503), _http_error(503)])
    with pytest.raises(httpx.HTTPStatusError):
        await lark.with_retry(fn, attempts=2, backoff=0.0)
    # attempts=2 means: initial try + up to 2 retries = 3 total calls
    assert fn.call_count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_lark_with_retry.py -v`
Expected: All five fail with `AttributeError: module 'src.infrastructure.lark_client' has no attribute 'with_retry'`.

- [ ] **Step 3: Implement helper**

Add to `src/infrastructure/lark_client.py` immediately above the CRUD helpers section (after the provisioning helpers, around line 220):

```python
import asyncio  # add at top of file if not present
from typing import Any, Awaitable, Callable

# ---------------------------------------------------------------------------
# Retry wrapper — recoverable failures only
# ---------------------------------------------------------------------------


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    attempts: int = 2,
    backoff: float = 0.5,
) -> Any:
    """Retry httpx network errors and HTTP 5xx. attempts=2 means initial call + up to 2 retries.
    Lark business errors (raised as plain Exception with 'Lark error: code') are NOT retried."""
    last_exc: BaseException | None = None
    for tryno in range(attempts + 1):
        try:
            return await fn()
        except BaseException as exc:
            if not _is_transient(exc):
                raise
            last_exc = exc
            if tryno < attempts:
                await asyncio.sleep(backoff * (2 ** tryno))
    assert last_exc is not None
    raise last_exc
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_lark_with_retry.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_lark_with_retry.py src/infrastructure/lark_client.py
git commit -m "feat(lark): add with_retry helper for transient failures"
```

---

## Task 3: Schema — add `lark_record_id` columns and repo methods

**Files:**
- Create: `tests/unit/test_lark_record_id_columns.py`
- Create: `tests/unit/test_reminder_repo_lark_id.py`
- Create: `tests/unit/test_note_repo_lark_id.py`
- Modify: `src/db.py` (`_init_schema`, facade methods)
- Modify: `src/repositories/reminder_repo.py`
- Modify: `src/repositories/note_repo.py`

### Step 1: Write failing schema test

Create `tests/unit/test_lark_record_id_columns.py`:

```python
"""reminders.lark_record_id and notes.lark_record_id must be present after migration."""
import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema


@pytest_asyncio.fixture
async def db():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield conn


async def test_reminders_has_lark_record_id(db):
    async with db.execute("PRAGMA table_info(reminders)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_record_id" in cols


async def test_notes_has_lark_record_id(db):
    async with db.execute("PRAGMA table_info(notes)") as cur:
        cols = [row[1] async for row in cur]
    assert "lark_record_id" in cols


async def test_lark_record_id_nullable_default(db):
    """Existing rows should default to NULL, allowing migration of legacy data."""
    await db.execute(
        "INSERT INTO reminders (boss_chat_id, content, remind_at) VALUES (?, ?, ?)",
        ("boss-1", "demo", "2026-05-04 10:00:00"),
    )
    await db.commit()
    async with db.execute("SELECT lark_record_id FROM reminders") as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] is None
```

- [ ] **Step 2: Run schema test — verify failure**

Run: `uv run pytest tests/unit/test_lark_record_id_columns.py -v`
Expected: 3 FAIL — `lark_record_id` not in columns list.

- [ ] **Step 3: Migrate schema**

Edit `src/db.py`. Find the `bosses` ALTER block (around line 320–336). Append a similar block for `reminders` and `notes`:

```python
    # ---- Phase 6c forward-compat additions: lark_record_id on reminders/notes ----
    for table, col, definition in [
        ("reminders", "lark_record_id", "TEXT DEFAULT NULL"),
        ("notes",     "lark_record_id", "TEXT DEFAULT NULL"),
    ]:
        try:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        except Exception as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
```

- [ ] **Step 4: Run schema test — verify pass**

Run: `uv run pytest tests/unit/test_lark_record_id_columns.py -v`
Expected: 3 PASS.

### Step 5: Reminder repo — failing test for new methods

Create `tests/unit/test_reminder_repo_lark_id.py`:

```python
from datetime import datetime, timezone

import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield ReminderRepo(conn)


async def _make(repo, boss="b1", content="x"):
    return await repo.create(
        boss, content,
        datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
    )


async def test_set_and_get_lark_record_id(repo):
    rid = await _make(repo)
    await repo.set_lark_record_id(rid, "rec-abc")
    row = await repo.get_by_id(rid)
    assert row["lark_record_id"] == "rec-abc"


async def test_find_by_lark_id(repo):
    rid = await _make(repo)
    await repo.set_lark_record_id(rid, "rec-xyz")
    found = await repo.find_by_lark_id("b1", "rec-xyz")
    assert found is not None
    assert found["id"] == rid


async def test_find_by_lark_id_other_boss_returns_none(repo):
    rid = await _make(repo, boss="b1")
    await repo.set_lark_record_id(rid, "rec-1")
    assert await repo.find_by_lark_id("b2", "rec-1") is None


async def test_list_unsynced_pending(repo):
    r1 = await _make(repo, content="unsynced")
    r2 = await _make(repo, content="synced")
    await repo.set_lark_record_id(r2, "rec-2")
    rows = await repo.list_unsynced_pending("b1")
    ids = [r["id"] for r in rows]
    assert ids == [r1]


async def test_list_unsynced_pending_skips_done(repo):
    r1 = await _make(repo, content="will be done")
    await repo.mark_done(r1)
    rows = await repo.list_unsynced_pending("b1")
    assert rows == []


async def test_list_with_lark_id(repo):
    r1 = await _make(repo)
    r2 = await _make(repo)
    await repo.set_lark_record_id(r1, "rec-1")
    await repo.set_lark_record_id(r2, "rec-2")
    rows = await repo.list_with_lark_id("b1")
    pairs = sorted((r["id"], r["lark_record_id"]) for r in rows)
    assert pairs == [(r1, "rec-1"), (r2, "rec-2")]


async def test_tombstone(repo):
    rid = await _make(repo)
    await repo.tombstone(rid)
    row = await repo.get_by_id(rid)
    assert row["status"] == "done"


async def test_update_remind_at_and_content(repo):
    rid = await _make(repo)
    new_dt = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    await repo.update_remind_at_and_content(rid, content="updated", remind_at=new_dt)
    row = await repo.get_by_id(rid)
    assert row["content"] == "updated"
    assert row["remind_at"].startswith("2026-06-01 09:00")
```

- [ ] **Step 6: Run — verify failure**

Run: `uv run pytest tests/unit/test_reminder_repo_lark_id.py -v`
Expected: All fail (methods missing).

- [ ] **Step 7: Add reminder repo methods**

Edit `src/repositories/reminder_repo.py`. Append at end of `ReminderRepo` class:

```python
    async def set_lark_record_id(self, reminder_id: int, lark_record_id: str) -> None:
        await self._db.execute(
            "UPDATE reminders SET lark_record_id = ? WHERE id = ?",
            (lark_record_id, reminder_id),
        )
        await self._db.commit()

    async def get_by_id(self, reminder_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def find_by_lark_id(self, boss_chat_id: str, lark_record_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM reminders WHERE boss_chat_id = ? AND lark_record_id = ?",
            (str(boss_chat_id), lark_record_id),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_unsynced_pending(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM reminders
               WHERE boss_chat_id = ?
                 AND lark_record_id IS NULL
                 AND status = 'pending'""",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_with_lark_id(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM reminders
               WHERE boss_chat_id = ? AND lark_record_id IS NOT NULL""",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def tombstone(self, reminder_id: int) -> None:
        # Schema CHECK allows only ('pending', 'done'). Re-use 'done' as the tombstone
        # state — scheduler skips both 'done' and tombstoned rows for the same reason.
        await self._db.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?", (reminder_id,)
        )
        await self._db.commit()

    async def update_remind_at_and_content(
        self, reminder_id: int, *,
        content: Optional[str] = None,
        remind_at: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> None:
        sets: list[str] = []
        params: list = []
        if content is not None:
            sets.append("content = ?"); params.append(content)
        if remind_at is not None:
            sets.append("remind_at = ?")
            params.append(remind_at.isoformat(sep=" ", timespec="seconds"))
        if status is not None:
            sets.append("status = ?"); params.append(status)
        if not sets:
            return
        params.append(reminder_id)
        await self._db.execute(
            f"UPDATE reminders SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._db.commit()
```

- [ ] **Step 8: Run reminder repo tests — verify pass**

Run: `uv run pytest tests/unit/test_reminder_repo_lark_id.py -v`
Expected: 8 PASS.

### Step 9: Note repo — failing test

Create `tests/unit/test_note_repo_lark_id.py`:

```python
import aiosqlite
import pytest_asyncio
import pytest

from src.db import _init_schema
from src.repositories.note_repo import NoteRepo


@pytest_asyncio.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await _init_schema(conn)
        yield NoteRepo(conn)


async def test_upsert_returns_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    assert isinstance(rid, int) and rid > 0


async def test_upsert_returns_same_id_on_conflict(repo):
    a = await repo.upsert("b1", "personal", "x", "v1")
    b = await repo.upsert("b1", "personal", "x", "v2")
    assert a == b


async def test_set_lark_record_id_and_get_by_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    await repo.set_lark_record_id(rid, "rec-1")
    row = await repo.get_by_id(rid)
    assert row["lark_record_id"] == "rec-1"


async def test_find_by_lark_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "hello")
    await repo.set_lark_record_id(rid, "rec-1")
    found = await repo.find_by_lark_id("b1", "rec-1")
    assert found["id"] == rid


async def test_list_unsynced(repo):
    a = await repo.upsert("b1", "personal", "x", "v")
    b = await repo.upsert("b1", "personal", "y", "v")
    await repo.set_lark_record_id(b, "rec-b")
    rows = await repo.list_unsynced("b1")
    assert [r["id"] for r in rows] == [a]


async def test_list_with_lark_id(repo):
    a = await repo.upsert("b1", "personal", "x", "v")
    b = await repo.upsert("b1", "personal", "y", "v")
    await repo.set_lark_record_id(a, "rec-a")
    await repo.set_lark_record_id(b, "rec-b")
    rows = await repo.list_with_lark_id("b1")
    assert sorted(r["lark_record_id"] for r in rows) == ["rec-a", "rec-b"]


async def test_delete_by_id(repo):
    rid = await repo.upsert("b1", "personal", "x", "v")
    await repo.delete_by_id(rid)
    assert await repo.get_by_id(rid) is None
```

- [ ] **Step 10: Run note repo test — verify failure**

Run: `uv run pytest tests/unit/test_note_repo_lark_id.py -v`
Expected: All fail.

- [ ] **Step 11: Modify NoteRepo**

Replace `src/repositories/note_repo.py` entirely with:

```python
"""notes table — personal / project / group / idea notes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from src.repositories._base import row_to_dict


class NoteRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(
        self, boss_chat_id: str, note_type: str, ref_id: str,
    ) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
            (str(boss_chat_id), note_type, ref_id),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def get_by_id(self, note_id: int) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def upsert(
        self, boss_chat_id: str, note_type: str, ref_id: str, content: str,
    ) -> int:
        """Upsert and return the row id."""
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        await self._db.execute(
            """
            INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(boss_chat_id, type, ref_id) DO UPDATE SET
                content    = excluded.content,
                updated_at = excluded.updated_at
            """,
            (str(boss_chat_id), note_type, ref_id, content, now),
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT id FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
            (str(boss_chat_id), note_type, ref_id),
        ) as cur:
            row = await cur.fetchone()
        return int(row["id"]) if row else 0

    async def set_lark_record_id(self, note_id: int, lark_record_id: str) -> None:
        await self._db.execute(
            "UPDATE notes SET lark_record_id = ? WHERE id = ?",
            (lark_record_id, note_id),
        )
        await self._db.commit()

    async def find_by_lark_id(self, boss_chat_id: str, lark_record_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id = ?",
            (str(boss_chat_id), lark_record_id),
        ) as cur:
            row = await cur.fetchone()
        return row_to_dict(row)

    async def list_unsynced(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id IS NULL",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_with_lark_id(self, boss_chat_id: str) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM notes WHERE boss_chat_id = ? AND lark_record_id IS NOT NULL",
            (str(boss_chat_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def delete_by_id(self, note_id: int) -> None:
        await self._db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await self._db.commit()

    async def update_content_by_id(self, note_id: int, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        await self._db.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, note_id),
        )
        await self._db.commit()
```

- [ ] **Step 12: Update `db.update_note` facade to return id**

Edit `src/db.py:570-575`. Replace with:

```python
async def update_note(
    boss_chat_id: str, note_type: str, ref_id: str, content: str,
    db_path: str = "data/history.db",
) -> int:
    repo: NoteRepo = await _repo("note", NoteRepo)
    return await repo.upsert(boss_chat_id, note_type, ref_id, content)
```

- [ ] **Step 13: Run note repo test — verify pass**

Run: `uv run pytest tests/unit/test_note_repo_lark_id.py tests/unit/test_lark_record_id_columns.py -v`
Expected: All PASS.

- [ ] **Step 14: Sanity check — run full unit suite**

Run: `uv run pytest tests/unit -v --tb=short`
Expected: All PASS. Pay special attention that no existing test that calls `update_note` breaks now that it returns an int — the previous return value was `None`; existing callers that used the return value as truthy may need a glance. Currently no existing test checks the return value of `update_note`, so this should be safe.

- [ ] **Step 15: Commit**

```bash
git add src/db.py src/repositories/reminder_repo.py src/repositories/note_repo.py \
        tests/unit/test_lark_record_id_columns.py \
        tests/unit/test_reminder_repo_lark_id.py \
        tests/unit/test_note_repo_lark_id.py
git commit -m "feat(db): add lark_record_id columns and repo helpers"
```

---

## Task 4: `reminder_service.create_reminder` — inline await + persist lark_record_id

**Files:**
- Create: `tests/unit/test_reminder_service_sync.py`
- Modify: `src/services/reminder_service.py:58-116`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reminder_service_sync.py`:

```python
"""reminder_service must inline-await Lark sync and persist lark_record_id.
On Lark failure: keep DB row, return graceful message; reconciler will retry."""
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import reminder_service


def _ctx(boss_chat_id="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss_chat_id,
        sender_name="Boss",
        sender_type="boss",
        boss_chat_id=boss_chat_id,
        boss_name="Boss",
        lark_base_token="base",
        lark_table_people="ppl",
        lark_table_tasks="tsk",
        lark_table_projects="prj",
        lark_table_ideas="idea",
        lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss_chat_id,
        is_group=False,
        group_name="",
        messages_collection="m",
        tasks_collection="t",
    )


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    # Provision a boss row so resolve_target lookups don't blow up if needed.
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas, lark_table_reminders,"
        " lark_table_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "base", "ppl", "tsk", "prj", "idea", "rmd", "notes"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_create_reminder_persists_lark_record_id(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-123")
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark", sync_mock
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.search_records",
        AsyncMock(return_value=[]),
    )

    msg = await reminder_service.create_reminder(
        _ctx(), content="check email", remind_at="2026-05-04 10:00",
    )

    assert "Da tao nhac nho" in msg
    sync_mock.assert_awaited_once()
    async with in_memory_db.execute(
        "SELECT lark_record_id FROM reminders WHERE boss_chat_id = 'b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-123"


async def test_create_reminder_lark_failure_keeps_db_row(in_memory_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=Exception("Lark down")),
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.search_records",
        AsyncMock(return_value=[]),
    )

    msg = await reminder_service.create_reminder(
        _ctx(), content="check email", remind_at="2026-05-04 10:00",
    )

    assert "dang cho dong bo" in msg.lower() or "đang chờ đồng bộ" in msg.lower()
    async with in_memory_db.execute(
        "SELECT id, lark_record_id FROM reminders WHERE boss_chat_id = 'b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None  # DB row kept
    assert row["lark_record_id"] is None  # not synced
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: Both fail. (`with_retry` not used, `lark_record_id` not persisted, no graceful failure message.)

- [ ] **Step 3: Modify `create_reminder`**

Edit `src/services/reminder_service.py`. Replace the body of `create_reminder` (the function starting at line 58) with:

```python
async def create_reminder(
    ctx: ChatContext,
    content: str,
    remind_at: str,
    target: str = "",
    task_keyword: str = "",
    project: str = "",
    workspace_ids: str = "current",
) -> str:
    """
    Create a reminder. task_keyword links to a task — scheduler will fetch live task
    status when the reminder fires. project is optional context for the message.
    """
    try:
        remind_dt = _local_remind_string_to_utc_naive(remind_at)
    except ValueError:
        return f"Dinh dang thoi gian khong hop le: '{remind_at}'. Vui long dung YYYY-MM-DD HH:MM."

    target_chat_id = None
    target_name = ""
    if target:
        target_chat_id, target_name = await _resolve_target(ctx, target)
        if not target_name:
            target_name = target

    stored_content = content
    if project:
        stored_content = f"[project:{project}] {stored_content}"
    if task_keyword:
        stored_content = f"[task:{task_keyword}] {stored_content}"

    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=stored_content,
        remind_at=remind_dt,
        target_chat_id=target_chat_id,
        target_name=target_name,
    )

    base = (
        f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
        if target_name and target_chat_id
        else f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."
    )

    if not ctx.lark_table_reminders:
        return base

    try:
        record_id = await lark.with_retry(lambda: lark.sync_reminder_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_reminders,
            {
                "content": stored_content,
                "remind_at_local": remind_at,
                "target_name": target_name,
                "status": "pending",
            },
            reminder_id,
        ))
        if record_id:
            from src.repositories.reminder_repo import ReminderRepo
            repo = ReminderRepo(await db.get_db())
            await repo.set_lark_record_id(reminder_id, record_id)
        return base
    except Exception:
        import logging as _logging
        _logging.getLogger("services.reminder").warning(
            "Lark sync failed for reminder %d; reconciler will retry", reminder_id,
            exc_info=True,
        )
        return base + " (đang chờ đồng bộ Lark)"
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/reminder_service.py tests/unit/test_reminder_service_sync.py
git commit -m "feat(reminder): inline-await Lark sync on create + persist record id"
```

---

## Task 5: `reminder_service.update_reminder` — sync to Lark

**Files:**
- Modify: `tests/unit/test_reminder_service_sync.py` (add tests)
- Modify: `src/services/reminder_service.py:145-184`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/test_reminder_service_sync.py`:

```python
async def test_update_reminder_syncs_lark(in_memory_db, monkeypatch):
    # Pre-create a reminder with a lark_record_id
    rid = await db.create_reminder(
        boss_chat_id="b1", content="old",
        remind_at=__import__("datetime").datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(in_memory_db).set_lark_record_id(rid, "rec-1")

    sync_mock = AsyncMock(return_value="rec-1")
    monkeypatch.setattr(
        "src.services.reminder_service.lark.sync_reminder_to_lark", sync_mock
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )

    await reminder_service.update_reminder(
        _ctx(), reminder_id=rid, content="new content",
    )

    sync_mock.assert_awaited_once()
    fields = sync_mock.await_args.args[2]
    assert fields["content"] == "new content"


async def test_update_reminder_lark_fail_returns_graceful_message(in_memory_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="old",
        remind_at=__import__("datetime").datetime(2026, 5, 4, 10),
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=Exception("Lark down")),
    )

    msg = await reminder_service.update_reminder(
        _ctx(), reminder_id=rid, content="new content",
    )
    assert "đang chờ đồng bộ" in msg.lower() or "dang cho dong bo" in msg.lower()
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: 2 new FAIL.

- [ ] **Step 3: Modify `update_reminder`**

Edit `src/services/reminder_service.py`. Replace `update_reminder` body with:

```python
async def update_reminder(
    ctx: ChatContext,
    reminder_id: int,
    content: Optional[str] = None,
    remind_at: Optional[str] = None,
    target: Optional[str] = None,
) -> str:
    kwargs: dict = {}
    if content is not None:
        kwargs["content"] = content
    if remind_at is not None:
        try:
            kwargs["remind_at"] = _local_remind_string_to_utc_naive(remind_at)
        except ValueError:
            return f"Dinh dang thoi gian khong hop le: '{remind_at}'. Dung YYYY-MM-DD HH:MM."

    update_target = False
    target_chat_id: Optional[int] = None
    target_name = ""
    if target is not None:
        update_target = True
        if target.strip() == "":
            target_chat_id = None
            target_name = ""
        else:
            target_chat_id, target_name = await _resolve_target(ctx, target)
            if not target_name:
                target_name = target

    ok = await db.update_reminder(
        reminder_id,
        ctx.boss_chat_id,
        **kwargs,
        update_target=update_target,
        target_chat_id=target_chat_id,
        target_name=target_name,
    )
    if not ok:
        return f"Khong tim thay nhac nho #{reminder_id} hoac khong co truong nao de cap nhat."

    base = f"Da cap nhat nhac nho #{reminder_id}."

    if not ctx.lark_table_reminders:
        return base

    from src.repositories.reminder_repo import ReminderRepo
    repo = ReminderRepo(await db.get_db())
    row = await repo.get_by_id(reminder_id)
    if not row:
        return base

    remind_at_local = remind_at or _utc_naive_stored_to_local_display(row["remind_at"])
    try:
        rec_id = await lark.with_retry(lambda: lark.sync_reminder_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_reminders,
            {
                "content": row["content"],
                "remind_at_local": remind_at_local,
                "target_name": row.get("target_name") or "",
                "status": row["status"],
            },
            reminder_id,
        ))
        if rec_id and not row.get("lark_record_id"):
            await repo.set_lark_record_id(reminder_id, rec_id)
        return base
    except Exception:
        import logging as _logging
        _logging.getLogger("services.reminder").warning(
            "Lark update sync failed for reminder %d", reminder_id, exc_info=True,
        )
        return base + " (đang chờ đồng bộ Lark)"
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: 4 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/services/reminder_service.py tests/unit/test_reminder_service_sync.py
git commit -m "feat(reminder): inline-await Lark sync on update"
```

---

## Task 6: `reminder_service.delete_reminder` — Lark-first delete

**Files:**
- Modify: `tests/unit/test_reminder_service_sync.py` (add tests)
- Modify: `src/services/reminder_service.py:187-191`

- [ ] **Step 1: Add failing tests**

Append to `tests/unit/test_reminder_service_sync.py`:

```python
async def test_delete_reminder_lark_first(in_memory_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=__import__("datetime").datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(in_memory_db).set_lark_record_id(rid, "rec-1")

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.reminder_service.lark.delete_record", delete_mock
    )
    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )

    msg = await reminder_service.delete_reminder(_ctx(), reminder_id=rid)

    delete_mock.assert_awaited_once()
    assert "Da xoa" in msg
    async with in_memory_db.execute(
        "SELECT id FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    assert row is None  # DB row removed


async def test_delete_reminder_lark_fail_keeps_db(in_memory_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=__import__("datetime").datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(in_memory_db).set_lark_record_id(rid, "rec-1")

    monkeypatch.setattr(
        "src.services.reminder_service.lark.with_retry",
        AsyncMock(side_effect=Exception("Lark down")),
    )

    msg = await reminder_service.delete_reminder(_ctx(), reminder_id=rid)

    assert "thu lai" in msg.lower() or "thử lại" in msg.lower()
    async with in_memory_db.execute(
        "SELECT id FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None  # DB row preserved


async def test_delete_reminder_no_lark_record_id_skips_lark_call(in_memory_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=__import__("datetime").datetime(2026, 5, 4, 10),
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.reminder_service.lark.delete_record", delete_mock
    )
    msg = await reminder_service.delete_reminder(_ctx(), reminder_id=rid)
    delete_mock.assert_not_awaited()
    assert "Da xoa" in msg
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: 3 new FAIL.

- [ ] **Step 3: Modify `delete_reminder`**

Edit `src/services/reminder_service.py`. Replace `delete_reminder` with:

```python
async def delete_reminder(ctx: ChatContext, reminder_id: int) -> str:
    from src.repositories.reminder_repo import ReminderRepo
    repo = ReminderRepo(await db.get_db())
    row = await repo.get_by_id(reminder_id)
    if not row or str(row.get("boss_chat_id")) != str(ctx.boss_chat_id):
        return f"Khong tim thay nhac nho #{reminder_id}."

    lark_id = row.get("lark_record_id")
    if lark_id and ctx.lark_table_reminders:
        try:
            await lark.with_retry(lambda: lark.delete_record(
                ctx.lark_base_token, ctx.lark_table_reminders, lark_id,
            ))
        except Exception:
            import logging as _logging
            _logging.getLogger("services.reminder").warning(
                "Lark delete failed for reminder %d", reminder_id, exc_info=True,
            )
            return f"Lark dang loi, chua xoa duoc #{reminder_id} — anh thu lai sau."

    ok = await db.delete_reminder(reminder_id, ctx.boss_chat_id)
    if not ok:
        return f"Khong tim thay nhac nho #{reminder_id}."
    return f"Da xoa nhac nho #{reminder_id}."
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_reminder_service_sync.py -v`
Expected: 7 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/services/reminder_service.py tests/unit/test_reminder_service_sync.py
git commit -m "feat(reminder): Lark-first delete with rollback-on-failure semantics"
```

---

## Task 7: `note_service.update_note` and `append_note` — sync to Lark

**Files:**
- Create: `tests/unit/test_note_service_sync.py`
- Modify: `src/services/note_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_note_service_sync.py`:

```python
"""note_service must inline-await Lark sync and persist lark_record_id."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest_asyncio
import pytest

import src.db as db
from src.context import ChatContext
from src.services import note_service


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


async def test_update_note_calls_sync_and_persists_id(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-1")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    monkeypatch.setattr(
        "src.services.note_service.lark.with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )

    msg = await note_service.update_note(
        _ctx(), note_type="personal", ref_id="b1", content="hi",
    )
    assert "Đã cập nhật" in msg
    sync_mock.assert_awaited_once()

    async with in_memory_db.execute(
        "SELECT lark_record_id FROM notes WHERE boss_chat_id='b1' AND type='personal' AND ref_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-1"


async def test_append_note_calls_sync(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-2")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    monkeypatch.setattr(
        "src.services.note_service.lark.with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )
    await note_service.update_note(_ctx(), note_type="personal", ref_id="b1", content="A")
    sync_mock.reset_mock()
    await note_service.append_note(_ctx(), note_type="personal", ref_id="b1", content="B")
    sync_mock.assert_awaited_once()
    fields = sync_mock.await_args.args[2]
    assert "A\n\nB" in fields["content"]


async def test_update_note_no_lark_table_skips_sync(in_memory_db, monkeypatch):
    sync_mock = AsyncMock(return_value="rec-x")
    monkeypatch.setattr(
        "src.services.note_service.lark.sync_note_to_lark", sync_mock
    )
    ctx = _ctx()
    object.__setattr__(ctx, "lark_table_notes", "")  # tenant without notes table
    await note_service.update_note(ctx, note_type="personal", ref_id="b1", content="hi")
    sync_mock.assert_not_awaited()
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_note_service_sync.py -v`
Expected: 3 FAIL (sync not called, id not persisted).

- [ ] **Step 3: Modify `note_service`**

Replace `src/services/note_service.py` entirely with:

```python
"""Note read/write tools. Takes ChatContext as first argument."""
import asyncio
import logging
from datetime import datetime, timezone

from src import db
from src.context import ChatContext
from src.infrastructure import lark_client as lark

logger = logging.getLogger("services.note")


async def _embed_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> None:
    """Async background: embed note to Qdrant notes_{boss_chat_id} collection."""
    try:
        from src.infrastructure import qdrant_client as qdrant
        from src.agent.llm_for_ctx import get_llm_for_ctx
        llm = await get_llm_for_ctx(ctx)
        collection = f"notes_{ctx.boss_chat_id}_{llm.embedding_dim}"
        await qdrant.ensure_collection(collection, dim=llm.embedding_dim)
        vector, _ = await llm.embed(content)
        point_id = abs(hash(f"note_{ctx.boss_chat_id}_{note_type}_{ref_id}")) % (2 ** 53)
        await qdrant.upsert_note(
            collection=collection,
            point_id=point_id,
            boss_chat_id=ctx.boss_chat_id,
            text=content,
            vector=vector,
            note_type=note_type,
            ref=ref_id,
        )
    except Exception:
        logger.warning("Qdrant embed failed for note (%s/%s)", note_type, ref_id, exc_info=True)


async def _sync_note_to_lark(
    ctx: ChatContext, note_type: str, ref_id: str, content: str, sqlite_id: int,
) -> None:
    """Inline-await Lark sync; persist lark_record_id on success.
    On failure: log warning. Reverse-sync reconciler will retry on next pass."""
    if not ctx.lark_table_notes:
        return
    try:
        rec_id = await lark.with_retry(lambda: lark.sync_note_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_notes,
            {
                "type": note_type,
                "ref_id": ref_id,
                "content": content,
                "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
            },
            sqlite_id,
        ))
        if rec_id:
            from src.repositories.note_repo import NoteRepo
            repo = NoteRepo(await db.get_db())
            existing = await repo.get_by_id(sqlite_id)
            if existing and not existing.get("lark_record_id"):
                await repo.set_lark_record_id(sqlite_id, rec_id)
    except Exception:
        logger.warning(
            "Lark sync failed for note (%s/%s); reconciler will retry",
            note_type, ref_id, exc_info=True,
        )


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    sqlite_id = await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, content))
    await _sync_note_to_lark(ctx, note_type, ref_id, content, sqlite_id)
    return f"Đã cập nhật note ({note_type}/{ref_id})."


async def get_note(ctx: ChatContext, note_type: str, ref_id: str) -> str:
    note = await db.get_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
    )
    if note is None:
        return ""
    return note.get("content", "")


async def append_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    """Appends content to an existing note without overwriting. Creates if not exists."""
    existing = await db.get_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
    )
    if existing and existing.get("content"):
        new_content = existing["content"] + "\n\n" + content
    else:
        new_content = content
    sqlite_id = await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=new_content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, new_content))
    await _sync_note_to_lark(ctx, note_type, ref_id, new_content, sqlite_id)
    return f"Đã cập nhật note ({note_type}/{ref_id})."
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_note_service_sync.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/note_service.py tests/unit/test_note_service_sync.py
git commit -m "feat(notes): inline-await Lark sync for update_note and append_note"
```

---

## Task 8: Reverse-sync — reminders extension (time edit, manual add, tombstone, reconcile)

**Files:**
- Create: `tests/unit/test_scheduler_reverse_sync_reminders.py`
- Modify: `src/scheduler.py:252-296`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_scheduler_reverse_sync_reminders.py`:

```python
"""Verify reverse-sync handles: time edits, manual adds, tombstone, reconcile push.

Tests call _reverse_sync_reminders_for_boss directly (skipping the every-5-min
gate inside _sync_lark_to_sqlite) so the notes block does not interfere."""
from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.scheduler as scheduler

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BOSS = {
    "chat_id": "b1", "name": "Boss",
    "lark_base_token": "base", "lark_table_reminders": "rmd",
}


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas, lark_table_reminders,"
        " lark_table_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "base", "ppl", "tsk", "prj", "idea", "rmd", "notes"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_reverse_sync_pulls_time_change(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(setup_db).set_lark_record_id(rid, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-1",
            "Nội dung": "x",
            "Thời gian nhắc": "2026-06-15 09:00",
            "Trạng thái": "pending",
            "SQLite ID": rid,
        }]),
    )
    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT remind_at FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    # Stored UTC for Asia/Ho_Chi_Minh 2026-06-15 09:00 = 2026-06-15 02:00 UTC
    assert row["remind_at"].startswith("2026-06-15 02:00")


async def test_reverse_sync_tombstones_vanished(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="x",
        remind_at=datetime(2026, 5, 4, 10),
    )
    from src.repositories.reminder_repo import ReminderRepo
    await ReminderRepo(setup_db).set_lark_record_id(rid, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT status FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "done"


async def test_reverse_sync_pulls_manual_add(setup_db, monkeypatch):
    sync_back_mock = AsyncMock(return_value="rec-99")
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-99",
            "Nội dung": "manually added",
            "Thời gian nhắc": "2026-07-01 14:30",
            "Trạng thái": "pending",
            "Người nhận": "",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", sync_back_mock)
    monkeypatch.setattr(
        scheduler.lark, "with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )

    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT id, content, remind_at, lark_record_id FROM reminders"
        " WHERE boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["content"] == "manually added"
    assert row["lark_record_id"] == "rec-99"
    sync_back_mock.assert_awaited()  # SQLite ID written back to Lark


async def test_reverse_sync_skips_unparseable_time(setup_db, monkeypatch, caplog):
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-bad",
            "Nội dung": "x",
            "Thời gian nhắc": "not a date",
            "Trạng thái": "pending",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", AsyncMock())
    monkeypatch.setattr(
        scheduler.lark, "with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )
    with caplog.at_level("WARNING"):
        await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute("SELECT COUNT(*) AS n FROM reminders") as cur:
        row = await cur.fetchone()
    assert row["n"] == 0  # parse failed → no row created


async def test_reverse_sync_reconciles_unsynced_db_row(setup_db, monkeypatch):
    rid = await db.create_reminder(
        boss_chat_id="b1", content="needs sync",
        remind_at=datetime(2026, 5, 4, 10),
    )
    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    sync_mock = AsyncMock(return_value="rec-new")
    monkeypatch.setattr(scheduler.lark, "sync_reminder_to_lark", sync_mock)
    monkeypatch.setattr(
        scheduler.lark, "with_retry",
        AsyncMock(side_effect=lambda fn, **kw: fn()),
    )

    await scheduler._reverse_sync_reminders_for_boss(BOSS, TZ)

    async with setup_db.execute(
        "SELECT lark_record_id, status FROM reminders WHERE id = ?", (rid,)
    ) as cur:
        row = await cur.fetchone()
    # Tombstone must NOT have happened (lark_record_id was NULL before this pass).
    assert row["lark_record_id"] == "rec-new"
    assert row["status"] == "pending"
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_scheduler_reverse_sync_reminders.py -v`
Expected: All 5 fail.

- [ ] **Step 3: Implement extended reminder reverse-sync**

Edit `src/scheduler.py`. Replace `_sync_lark_to_sqlite` with:

```python
async def _sync_lark_to_sqlite():
    """Lark → SQLite reverse-sync.

    Reminders block runs every call (every 30s). Tasks status sync + Notes block
    run only on the every-5-min gate.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    bosses = await db.get_all_bosses()
    now = datetime.utcnow()
    do_full_sync = (now.minute % 5 == 0 and now.second < 35)
    settings_tz = ZoneInfo(_settings.timezone) if _settings else ZoneInfo("Asia/Ho_Chi_Minh")

    for boss in bosses:
        try:
            await _reverse_sync_reminders_for_boss(boss, settings_tz)
        except Exception:
            logger.exception("[scheduler] reminder reverse-sync failed for %s", boss.get("name"))

        if not do_full_sync:
            continue

        # Task terminal-state sync (existing behaviour) ------------------------------
        task_tbl = boss.get("lark_table_tasks", "")
        if task_tbl:
            try:
                tasks = await lark.search_records(boss["lark_base_token"], task_tbl)
                for t in tasks:
                    record_id = t.get("record_id")
                    status = t.get("Status", "")
                    if status in ("Hoàn thành", "Huỷ", "Done", "Cancelled") and record_id:
                        await db._db.execute(
                            """UPDATE task_notifications SET notified_overdue=1
                               WHERE task_record_id=? AND boss_chat_id=?""",
                            (record_id, str(boss["chat_id"])),
                        )
                await db._db.commit()
            except Exception:
                logger.exception("[scheduler] task terminal sync failed for %s", boss.get("name"))

        # Notes block (full sync, every 5 min) -- task 9 wires this in.
        try:
            await _reverse_sync_notes_for_boss(boss)
        except Exception:
            logger.exception("[scheduler] notes reverse-sync failed for %s", boss.get("name"))


async def _reverse_sync_reminders_for_boss(boss: dict, settings_tz) -> None:
    from datetime import datetime
    from src.repositories.reminder_repo import ReminderRepo

    tbl = boss.get("lark_table_reminders", "")
    if not tbl:
        return

    repo = ReminderRepo(db._db)
    boss_chat_id = str(boss["chat_id"])
    base = boss["lark_base_token"]
    records = await lark.search_records(base, tbl)

    seen_lark_ids: set[str] = set()
    for rec in records:
        rec_id = rec.get("record_id", "")
        if rec_id:
            seen_lark_ids.add(rec_id)
        sqlite_id = rec.get("SQLite ID")

        if isinstance(sqlite_id, (int, float)) and int(sqlite_id) > 0:
            # Update existing DB row from Lark.
            sqlite_id = int(sqlite_id)
            new_content = rec.get("Nội dung", "")
            new_status = rec.get("Trạng thái", "pending")
            new_status = "pending" if new_status not in ("pending", "done") else new_status
            remind_at_str = rec.get("Thời gian nhắc", "")
            remind_at_dt = None
            if remind_at_str:
                try:
                    naive = datetime.strptime(remind_at_str, "%Y-%m-%d %H:%M")
                    remind_at_dt = naive.replace(tzinfo=settings_tz).astimezone(
                        ZoneInfo("UTC")
                    ).replace(tzinfo=None)
                except (ValueError, TypeError):
                    logger.warning(
                        "[scheduler] bad time '%s' on lark reminder %s",
                        remind_at_str, rec_id,
                    )
            await repo.update_remind_at_and_content(
                sqlite_id, content=new_content, remind_at=remind_at_dt,
                status=new_status,
            )
        else:
            # Manual-add: create DB row, write SQLite ID back to Lark.
            remind_at_str = rec.get("Thời gian nhắc", "")
            try:
                naive = datetime.strptime(remind_at_str, "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                logger.warning(
                    "[scheduler] cannot parse time on manual-add lark reminder %s: %r",
                    rec_id, remind_at_str,
                )
                continue
            remind_dt = naive.replace(tzinfo=settings_tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            new_id = await db.create_reminder(
                boss_chat_id=boss_chat_id,
                content=rec.get("Nội dung", ""),
                remind_at=remind_dt,
                target_chat_id=None,
                target_name=rec.get("Người nhận", "") or "",
            )
            if rec_id:
                await repo.set_lark_record_id(new_id, rec_id)
            try:
                await lark.with_retry(lambda: lark.sync_reminder_to_lark(
                    base, tbl,
                    {
                        "content": rec.get("Nội dung", ""),
                        "remind_at_local": remind_at_str,
                        "target_name": rec.get("Người nhận", "") or "",
                        "status": "pending",
                    },
                    new_id,
                ))
            except Exception:
                logger.warning(
                    "[scheduler] could not write SQLite ID back to lark %s", rec_id,
                    exc_info=True,
                )

    # Tombstone vanished: DB rows with lark_record_id not in `seen_lark_ids`.
    for row in await repo.list_with_lark_id(boss_chat_id):
        if row["lark_record_id"] not in seen_lark_ids and row["status"] == "pending":
            await repo.tombstone(row["id"])

    # Reconcile push: DB rows lacking lark_record_id (status pending only).
    for row in await repo.list_unsynced_pending(boss_chat_id):
        try:
            remind_local = row["remind_at"]
            # remind_at stored as 'YYYY-MM-DD HH:MM:SS' UTC naive — convert back to local for Lark display.
            try:
                dt_utc = datetime.fromisoformat(remind_local.strip()).replace(tzinfo=ZoneInfo("UTC"))
                remind_local_str = dt_utc.astimezone(settings_tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                remind_local_str = remind_local
            rec_id = await lark.with_retry(lambda: lark.sync_reminder_to_lark(
                base, tbl,
                {
                    "content": row["content"],
                    "remind_at_local": remind_local_str,
                    "target_name": row.get("target_name") or "",
                    "status": row["status"],
                },
                row["id"],
            ))
            if rec_id:
                await repo.set_lark_record_id(row["id"], rec_id)
        except Exception:
            logger.warning(
                "[scheduler] reconcile push failed for reminder %d", row["id"],
                exc_info=True,
            )


async def _reverse_sync_notes_for_boss(boss: dict) -> None:
    """Wired in Task 9. Stub here so _sync_lark_to_sqlite always finds the symbol."""
    return
```

Add to imports at top of `src/scheduler.py` (if not already present):

```python
from zoneinfo import ZoneInfo
```

`ZoneInfo` is referenced inside the function — make sure the module-level import is present.

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_scheduler_reverse_sync_reminders.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py tests/unit/test_scheduler_reverse_sync_reminders.py
git commit -m "feat(scheduler): full reminder reverse-sync (time edit, manual add, tombstone, reconcile)"
```

---

## Task 9: Reverse-sync — notes block

**Files:**
- Create: `tests/unit/test_scheduler_reverse_sync_notes.py`
- Modify: `src/scheduler.py` (`_reverse_sync_notes_for_boss`)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_scheduler_reverse_sync_notes.py`:

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
import src.scheduler as scheduler


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, lark_base_token, lark_table_people,"
        " lark_table_tasks, lark_table_projects, lark_table_ideas, lark_table_reminders,"
        " lark_table_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "base", "ppl", "tsk", "prj", "idea", "rmd", "notes"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_notes_reverse_sync_pulls_lark_edit(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="old",
    )
    from src.repositories.note_repo import NoteRepo
    await NoteRepo(setup_db).set_lark_record_id(sqlite_id, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-1",
            "Loại": "personal", "Ref ID": "b1",
            "Nội dung": "edited via Lark UI",
            "SQLite ID": sqlite_id,
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "with_retry",
                        AsyncMock(side_effect=lambda fn, **kw: fn()))
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", AsyncMock())

    await scheduler._reverse_sync_notes_for_boss(
        {"chat_id": "b1", "lark_base_token": "base", "lark_table_notes": "notes"}
    )

    async with setup_db.execute(
        "SELECT content FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row["content"] == "edited via Lark UI"


async def test_notes_reverse_sync_pulls_manual_add(setup_db, monkeypatch):
    sync_back = AsyncMock(return_value="rec-99")
    monkeypatch.setattr(
        scheduler.lark, "search_records",
        AsyncMock(return_value=[{
            "record_id": "rec-99",
            "Loại": "project", "Ref ID": "P-1",
            "Nội dung": "manually added in lark",
        }]),
    )
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", sync_back)
    monkeypatch.setattr(scheduler.lark, "with_retry",
                        AsyncMock(side_effect=lambda fn, **kw: fn()))

    await scheduler._reverse_sync_notes_for_boss(
        {"chat_id": "b1", "lark_base_token": "base", "lark_table_notes": "notes"}
    )

    note = await db.get_note("b1", "project", "P-1")
    assert note is not None
    assert note["content"] == "manually added in lark"
    assert note["lark_record_id"] == "rec-99"


async def test_notes_reverse_sync_deletes_vanished(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="x",
    )
    from src.repositories.note_repo import NoteRepo
    await NoteRepo(setup_db).set_lark_record_id(sqlite_id, "rec-1")

    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(scheduler.lark, "with_retry",
                        AsyncMock(side_effect=lambda fn, **kw: fn()))
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", AsyncMock())

    await scheduler._reverse_sync_notes_for_boss(
        {"chat_id": "b1", "lark_base_token": "base", "lark_table_notes": "notes"}
    )

    async with setup_db.execute(
        "SELECT id FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row is None


async def test_notes_reverse_sync_reconciles_unsynced(setup_db, monkeypatch):
    sqlite_id = await db.update_note(
        boss_chat_id="b1", note_type="personal", ref_id="b1", content="needs sync",
    )
    monkeypatch.setattr(
        scheduler.lark, "search_records", AsyncMock(return_value=[]),
    )
    sync_mock = AsyncMock(return_value="rec-new")
    monkeypatch.setattr(scheduler.lark, "sync_note_to_lark", sync_mock)
    monkeypatch.setattr(scheduler.lark, "with_retry",
                        AsyncMock(side_effect=lambda fn, **kw: fn()))

    await scheduler._reverse_sync_notes_for_boss(
        {"chat_id": "b1", "lark_base_token": "base", "lark_table_notes": "notes"}
    )

    async with setup_db.execute(
        "SELECT lark_record_id FROM notes WHERE id = ?", (sqlite_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row["lark_record_id"] == "rec-new"
```

- [ ] **Step 2: Run — verify failure**

Run: `uv run pytest tests/unit/test_scheduler_reverse_sync_notes.py -v`
Expected: 4 fail (notes block is a stub).

- [ ] **Step 3: Implement notes reverse-sync**

Edit `src/scheduler.py`. Replace the stub `_reverse_sync_notes_for_boss` with:

```python
async def _reverse_sync_notes_for_boss(boss: dict) -> None:
    from src.repositories.note_repo import NoteRepo
    from datetime import datetime, timezone

    tbl = boss.get("lark_table_notes", "")
    if not tbl:
        return

    repo = NoteRepo(db._db)
    boss_chat_id = str(boss["chat_id"])
    base = boss["lark_base_token"]
    records = await lark.search_records(base, tbl)

    seen_lark_ids: set[str] = set()
    for rec in records:
        rec_id = rec.get("record_id", "")
        if rec_id:
            seen_lark_ids.add(rec_id)
        note_type = rec.get("Loại", "")
        ref_id = str(rec.get("Ref ID", "") or "")
        content = rec.get("Nội dung", "")
        if not note_type or not ref_id:
            continue
        sqlite_id_raw = rec.get("SQLite ID")

        if isinstance(sqlite_id_raw, (int, float)) and int(sqlite_id_raw) > 0:
            sqlite_id = int(sqlite_id_raw)
            existing = await repo.get_by_id(sqlite_id)
            if existing and existing.get("content") != content:
                await repo.update_content_by_id(sqlite_id, content)
        else:
            new_id = await repo.upsert(boss_chat_id, note_type, ref_id, content)
            if rec_id:
                await repo.set_lark_record_id(new_id, rec_id)
            try:
                await lark.with_retry(lambda: lark.sync_note_to_lark(
                    base, tbl,
                    {
                        "type": note_type, "ref_id": ref_id,
                        "content": content,
                        "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
                    },
                    new_id,
                ))
            except Exception:
                logger.warning(
                    "[scheduler] could not write SQLite ID back for note %s", rec_id,
                    exc_info=True,
                )

    # Delete vanished
    for row in await repo.list_with_lark_id(boss_chat_id):
        if row["lark_record_id"] not in seen_lark_ids:
            await repo.delete_by_id(row["id"])

    # Reconcile push
    for row in await repo.list_unsynced(boss_chat_id):
        try:
            rec_id = await lark.with_retry(lambda: lark.sync_note_to_lark(
                base, tbl,
                {
                    "type": row["type"], "ref_id": row["ref_id"],
                    "content": row["content"],
                    "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
                },
                row["id"],
            ))
            if rec_id:
                await repo.set_lark_record_id(row["id"], rec_id)
        except Exception:
            logger.warning(
                "[scheduler] reconcile push failed for note %d", row["id"],
                exc_info=True,
            )
```

- [ ] **Step 4: Run — verify pass**

Run: `uv run pytest tests/unit/test_scheduler_reverse_sync_notes.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full unit suite**

Run: `uv run pytest tests/unit -v --tb=short`
Expected: All PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/scheduler.py tests/unit/test_scheduler_reverse_sync_notes.py
git commit -m "feat(scheduler): bidirectional notes reverse-sync"
```

---

## Task 10: Smoke test in Docker + final integration check

**Files:**
- None (verification only)

- [ ] **Step 1: Confirm full unit suite green**

Run: `uv run pytest tests -v --tb=short`
Expected: All PASS.

- [ ] **Step 2: Rebuild docker image (src is COPY'd at build time, not bind-mounted)**

Run:
```bash
docker compose up -d --build app
```
Wait until `docker compose ps` shows `app` as healthy.

- [ ] **Step 3: Tail logs and exercise the bot**

Run: `docker compose logs -f app | head -200` in one terminal. In Telegram (or whatever channel is wired):
1. Send `/nhắc tôi gọi điện cho khách lúc 2026-05-05 10:00`. Expect reply confirming creation. Open Lark Reminders table — row should appear within seconds.
2. Edit the `Thời gian nhắc` cell in Lark to `2026-05-05 14:00`. Wait ≤ 35 s. Run `/list` (or whatever lists reminders) — `remind_at` should reflect the new time.
3. Delete the row in Lark. Wait ≤ 35 s. List reminders with `status=pending` — the reminder should be gone.
4. Manually add a new row in Lark: `Nội dung=test`, `Thời gian nhắc=2026-05-05 16:00`, `Trạng thái=pending`. Wait ≤ 35 s. List reminders — the new row should appear with a `SQLite ID` written back to Lark.
5. Send a note via the bot (any flow that triggers `update_note`). Verify a row appears in Lark `Notes` within seconds.
6. Edit the Lark note content. Wait up to 5 min. Use `get_note` (e.g., trigger any agent flow that re-reads the note) — content should reflect the Lark edit.

Acceptance: every numbered scenario above behaves as described.

- [ ] **Step 4: Inspect logs for unexpected warnings**

Search the docker log output for `Lark sync failed`, `reconcile push failed`, `bad time`, and `hard cap`. None should appear during normal operation. (The `hard cap` warning is benign on small tenants but flag it if seen on tenants with < 5000 records.)

- [ ] **Step 5: No commit needed for this task**

The smoke test produces no code changes. If a regression is found, file a follow-up ticket and either fix in-place or revert specific commits.

---

## Self-review notes

- All steps reference exact file paths and line numbers; no `TODO` placeholders remain.
- Each task ends with a commit; commits are small enough to revert individually.
- The `with_retry` helper has parameters `attempts` and `backoff` consistent across all callers in tasks 4-9.
- Repo method names match between definition (Task 3) and consumers (Tasks 4-9): `set_lark_record_id`, `get_by_id`, `find_by_lark_id`, `list_unsynced_pending`, `list_with_lark_id`, `tombstone`, `update_remind_at_and_content` (reminder); `get_by_id`, `set_lark_record_id`, `find_by_lark_id`, `list_unsynced`, `list_with_lark_id`, `delete_by_id`, `update_content_by_id` (note).
- Tests use `pytest_asyncio` fixtures, in-memory `aiosqlite`, and mock `lark` module attributes via `monkeypatch.setattr(...)`. `asyncio_mode = "auto"` is set in `pyproject.toml`, so no `@pytest.mark.asyncio` decorators are needed.
- Schema migration follows the existing `bosses` ALTER pattern (try/except duplicate column).
- Tombstone re-uses `status='done'` to avoid a CHECK-constraint migration.
