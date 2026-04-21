# Notes Lark Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync bot notes (`update_note` / `append_note`) to Lark so the boss can see them in the Lark Base UI.

**Architecture:** `lark.sync_note_to_lark` already exists and uses the SQLite row `id` as the upsert key in Lark (field `SQLite ID`). The Lark Notes table is already provisioned with all required fields. The only missing pieces are: (1) `db.update_note` must return the SQLite row id so we can pass it to the Lark sync, and (2) `src/tools/note.py` must call the sync as a fire-and-forget background task after each write.

**Tech Stack:** Python 3.12, aiosqlite, `src/services/lark.py` (`sync_note_to_lark`)

---

## File Map

| File | What changes |
|------|-------------|
| `src/db.py` | `update_note`: add SELECT after INSERT to return the row's `id` (int) |
| `src/tools/note.py` | Add `_sync_note_lark` helper; wire into `update_note` and `append_note`; import lark |
| `src/tools/__init__.py` | Update `update_note` description — remove "chỉ bot dùng, user không thấy" |

No schema migration needed — `sync_note_to_lark` in lark.py already handles upsert by `SQLite ID`, and the Notes Lark table already has the `SQLite ID` field from `provision_workspace`.

---

### Task 1: `db.update_note` returns the SQLite row id

**Files:**
- Modify: `src/db.py:510-529`
- Test: `tests/unit/test_db_notes_id.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_db_notes_id.py`:

```python
import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_update_note_returns_int_id(tmp_path):
    """db.update_note should return the SQLite row id (int > 0)."""
    db_path = str(tmp_path / "test.db")
    # Bootstrap schema via init_db
    from src.db import init_db
    await init_db(db_path)

    # Create a boss row so the FK constraint passes
    import aiosqlite as _sq
    async with _sq.connect(db_path) as conn:
        conn.row_factory = _sq.Row
        await conn.execute(
            "INSERT OR IGNORE INTO bosses (chat_id, name, company, lark_base_token, "
            "lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas) "
            "VALUES (1, 'Boss', 'Co', 'tok', 'ppl', 'tsk', 'prj', 'idea')"
        )
        await conn.commit()

    from src.db import update_note
    note_id = await update_note(
        boss_chat_id=1,
        note_type="personal",
        ref_id="Alice",
        content="On leave next week",
        db_path=db_path,
    )
    assert isinstance(note_id, int)
    assert note_id > 0


@pytest.mark.asyncio
async def test_update_note_returns_same_id_on_upsert(tmp_path):
    """Second write to same (boss_chat_id, type, ref_id) returns the same id."""
    db_path = str(tmp_path / "test.db")
    from src.db import init_db
    await init_db(db_path)

    import aiosqlite as _sq
    async with _sq.connect(db_path) as conn:
        conn.row_factory = _sq.Row
        await conn.execute(
            "INSERT OR IGNORE INTO bosses (chat_id, name, company, lark_base_token, "
            "lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas) "
            "VALUES (1, 'Boss', 'Co', 'tok', 'ppl', 'tsk', 'prj', 'idea')"
        )
        await conn.commit()

    from src.db import update_note
    id1 = await update_note(1, "personal", "Alice", "first write", db_path=db_path)
    id2 = await update_note(1, "personal", "Alice", "updated write", db_path=db_path)
    assert id1 == id2
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd "/Users/dat_macbook/Documents/2025/ý tưởng mới/Dự án hỗ trợ thứ ký giám đốc ảo"
python -m pytest tests/unit/test_db_notes_id.py -v
```

Expected: FAIL — `update_note` returns `None`, `assert isinstance(None, int)` fails.

- [ ] **Step 3: Update `db.update_note` to return the row id**

In `src/db.py`, replace `update_note` (currently lines ~510-529):

```python
async def update_note(
    boss_chat_id: int,
    note_type: str,
    ref_id: str,
    content: str,
    db_path: str = "data/history.db",
) -> int:
    """Insert or update a note. Returns the SQLite row id."""
    db = await get_db(db_path)
    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    await db.execute(
        """
        INSERT INTO notes (boss_chat_id, type, ref_id, content, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(boss_chat_id, type, ref_id) DO UPDATE SET
            content    = excluded.content,
            updated_at = excluded.updated_at
        """,
        (boss_chat_id, note_type, ref_id, content, now),
    )
    async with db.execute(
        "SELECT id FROM notes WHERE boss_chat_id = ? AND type = ? AND ref_id = ?",
        (boss_chat_id, note_type, ref_id),
    ) as cur:
        row = await cur.fetchone()
    await db.commit()
    return row["id"] if row else 0
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/test_db_notes_id.py -v
```

Expected: PASS both tests.

- [ ] **Step 5: Run full unit suite to check no regressions**

```bash
python -m pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/unit/test_db_notes_id.py
git commit -m "feat: db.update_note returns SQLite row id for Lark sync"
```

---

### Task 2: `_sync_note_lark` helper + wire into note tools

**Files:**
- Modify: `src/tools/note.py` (full file)
- Test: `tests/unit/test_note_lark_sync.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_note_lark_sync.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _ctx(has_notes_table=True):
    ctx = MagicMock()
    ctx.boss_chat_id = 100
    ctx.lark_base_token = "tok"
    ctx.lark_table_notes = "ntbl" if has_notes_table else ""
    return ctx


@pytest.mark.asyncio
async def test_sync_note_lark_calls_service():
    """_sync_note_lark calls lark.sync_note_to_lark with correct args."""
    from src.tools import note as note_mod
    ctx = _ctx()

    with patch("src.tools.note.lark.sync_note_to_lark", new_callable=AsyncMock) as mock_sync:
        await note_mod._sync_note_lark(ctx, "personal", "Alice", "on leave", 42)

    mock_sync.assert_awaited_once_with(
        "tok", "ntbl",
        {"type": "personal", "ref_id": "Alice", "content": "on leave"},
        42,
    )


@pytest.mark.asyncio
async def test_sync_note_lark_noop_when_no_table():
    """_sync_note_lark silently returns when lark_table_notes is empty."""
    from src.tools import note as note_mod
    ctx = _ctx(has_notes_table=False)

    with patch("src.tools.note.lark.sync_note_to_lark", new_callable=AsyncMock) as mock_sync:
        await note_mod._sync_note_lark(ctx, "personal", "Alice", "on leave", 42)

    mock_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_note_triggers_lark_sync():
    """update_note fires _sync_note_lark as background task."""
    from src.tools import note as note_mod
    ctx = _ctx()
    synced = {}

    async def fake_sync(c, nt, rid, content, sid):
        synced["called"] = True
        synced["sqlite_id"] = sid

    with patch("src.tools.note.db.update_note", new_callable=AsyncMock, return_value=7), \
         patch("src.tools.note._embed_note", new_callable=AsyncMock), \
         patch("src.tools.note._sync_note_lark", side_effect=fake_sync) as mock_sync, \
         patch("asyncio.create_task", side_effect=lambda coro: coro):
        await note_mod.update_note(ctx, "personal", "Alice", "on leave")

    mock_sync.assert_called_once()
    call_args = mock_sync.call_args
    assert call_args.args[4] == 7  # sqlite_id passed correctly


@pytest.mark.asyncio
async def test_append_note_triggers_lark_sync_with_merged_content():
    """append_note fires _sync_note_lark with the full merged content."""
    from src.tools import note as note_mod
    ctx = _ctx()
    existing = {"content": "existing note"}
    captured = {}

    async def fake_sync(c, nt, rid, content, sid):
        captured["content"] = content

    with patch("src.tools.note.db.get_note", new_callable=AsyncMock, return_value=existing), \
         patch("src.tools.note.db.update_note", new_callable=AsyncMock, return_value=5), \
         patch("src.tools.note._embed_note", new_callable=AsyncMock), \
         patch("src.tools.note._sync_note_lark", side_effect=fake_sync), \
         patch("asyncio.create_task", side_effect=lambda coro: coro):
        await note_mod.append_note(ctx, "personal", "Alice", "new info")

    assert "existing note" in captured["content"]
    assert "new info" in captured["content"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/unit/test_note_lark_sync.py -v
```

Expected: FAIL — `_sync_note_lark` doesn't exist yet.

- [ ] **Step 3: Rewrite `src/tools/note.py`**

```python
"""
Note read/write tools. Takes ChatContext as first argument.
"""
import asyncio
import logging

from src import db
from src.context import ChatContext
from src.services import lark

logger = logging.getLogger("tools.note")


async def _embed_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> None:
    """Async background: embed note to Qdrant notes_{boss_chat_id} collection."""
    try:
        from src.services import qdrant, openai_client
        collection = f"notes_{ctx.boss_chat_id}"
        await qdrant.ensure_collection(collection)
        vector = await openai_client.embed(content)
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
        pass  # Qdrant embedding is best-effort


async def _sync_note_lark(
    ctx: ChatContext,
    note_type: str,
    ref_id: str,
    content: str,
    sqlite_id: int,
) -> None:
    """Mirror note to Lark Notes table. Fire-and-forget — never raises."""
    if not getattr(ctx, "lark_table_notes", None):
        return
    try:
        await lark.sync_note_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_notes,
            {"type": note_type, "ref_id": ref_id, "content": content},
            sqlite_id,
        )
    except Exception:
        logger.warning("Lark note sync failed for %s/%s", note_type, ref_id, exc_info=True)


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    sqlite_id = await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, content))
    asyncio.create_task(_sync_note_lark(ctx, note_type, ref_id, content, sqlite_id))
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
    asyncio.create_task(_sync_note_lark(ctx, note_type, ref_id, new_content, sqlite_id))
    return f"Đã cập nhật note ({note_type}/{ref_id})."
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/test_note_lark_sync.py -v
```

Expected: PASS all 4 tests.

- [ ] **Step 5: Run full unit suite**

```bash
python -m pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tools/note.py tests/unit/test_note_lark_sync.py
git commit -m "feat: sync notes to Lark on update/append (fire-and-forget)"
```

---

### Task 3: Update tool description

**Files:**
- Modify: `src/tools/__init__.py:360-365` (update_note description)

- [ ] **Step 1: Update the `update_note` description in `TOOL_DEFINITIONS`**

In `src/tools/__init__.py`, find the `update_note` tool definition (around line 357) and change its description from:

```python
"description": "Lưu ghi chú nội bộ (chỉ bot dùng, user không thấy). Gọi khi biết thêm thông tin quan trọng cần nhớ lâu dài, ví dụ: 'Bách nghỉ phép tuần sau', 'dự án X bị delay vì khách chưa duyệt'.",
```

to:

```python
"description": "Lưu ghi chú nội bộ — hiển thị trong Lark Base để boss tham khảo. Gọi khi biết thêm thông tin quan trọng cần nhớ lâu dài, ví dụ: 'Bách nghỉ phép tuần sau', 'dự án X bị delay vì khách chưa duyệt'.",
```

- [ ] **Step 2: Run full unit suite one final time**

```bash
python -m pytest tests/unit/ -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tools/__init__.py
git commit -m "docs: update_note description — notes visible in Lark Base"
```
