# Phase 1 — Utils + Infrastructure Carve-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract pure helper functions into `src/utils/` and rename external clients (`lark`, `qdrant`, `openai_client`, `cohere`) from `src/services/` to `src/infrastructure/`. No behavior change; eliminate three copies of `_date_to_ms` along the way.

**Architecture:** Two new packages — `utils/` for pure functions (no I/O, no state) and `infrastructure/` for thin HTTP / SDK wrappers. `src/services/telegram.py` stays untouched (Phase 5 deletes it). All callers update their imports. Existing tests update to point at the new paths so the test suite stays green during the rename.

**Tech Stack:** Python 3.11+, pytest with `asyncio_mode = auto`, httpx, qdrant-client, openai SDK.

**Spec reference:** [docs/superpowers/specs/2026-04-28-platform-channel-and-layered-architecture-design.md](../specs/2026-04-28-platform-channel-and-layered-architecture-design.md), Phase 1.

---

## Scope Notes

**Out of scope for this phase (deferred per spec):**

- `src/utils/markdown.py` — spec lists it as part of the end-state, but no caller needs it until Phase 6 (Zalo / Messenger plain-text fallback). Skipping here per YAGNI; create when first caller exists.
- `src/identity.py` helpers — spec mentions extracting pure helpers from this file. On inspection, the only candidate (`_name_match`) is a closure inside `resolve_candidates` that captures local state and is not extractable as a pure function. The whole `identity.py` module moves to `services/identity_service.py` in Phase 4 — no Phase 1 work needed.
- `src/services/telegram.py` is **not** moved or renamed in this phase. It is the legacy shim, removed in Phase 5.
- No new tests for `infrastructure/` clients. They are pure renames + import path updates; behavior is unchanged. Tests for the layer come in Phase 4 against services that wrap them.

## File Structure After This Phase

```
src/
├── utils/                       # NEW — pure helpers, no I/O
│   ├── __init__.py
│   ├── dates.py                 # date_to_ms, ms_to_date
│   ├── validation.py            # validate_status, validate_priority, TASK_STATUS_VALUES, TASK_PRIORITY_VALUES
│   └── text.py                  # full_name
│
├── infrastructure/              # NEW — external system clients
│   ├── __init__.py
│   ├── lark_client.py           # was src/services/lark.py
│   ├── qdrant_client.py         # was src/services/qdrant.py
│   ├── openai_client.py         # was src/services/openai_client.py
│   └── cohere_client.py         # was src/services/cohere.py
│
├── services/
│   ├── __init__.py
│   └── telegram.py              # UNCHANGED — Phase 5 deletes
│
└── tools/                       # UNCHANGED — uses utils + infrastructure
```

---

## Task 1 — Create `src/utils/` package + `dates.py`

**Files:**
- Create: `src/utils/__init__.py`
- Create: `src/utils/dates.py`
- Create: `tests/unit/test_utils_dates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_utils_dates.py`:

```python
"""Tests for src.utils.dates — pure date conversion helpers."""
from datetime import datetime

import pytest

from src.utils.dates import date_to_ms, ms_to_date


def test_date_to_ms_returns_millisecond_timestamp():
    # 2026-01-01 00:00:00 in local tz — we don't pin tz here because the
    # current implementation uses datetime.strptime + .timestamp() which
    # interprets as local time. The round-trip test below is the real check.
    ms = date_to_ms("2026-01-01")
    assert isinstance(ms, int)
    assert ms > 0


def test_ms_to_date_round_trip():
    ms = date_to_ms("2026-04-28")
    assert ms_to_date(ms) == "2026-04-28"


def test_date_to_ms_invalid_raises():
    with pytest.raises(ValueError):
        date_to_ms("28/04/2026")  # wrong format
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_utils_dates.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils'`.

- [ ] **Step 3: Create the package**

Create `src/utils/__init__.py` (empty file):

```python
```

Create `src/utils/dates.py`:

```python
"""Pure date / time conversion helpers — no I/O, no state."""
from datetime import datetime


def date_to_ms(date_str: str) -> int:
    """Convert YYYY-MM-DD to millisecond timestamp (Lark uses ms)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def ms_to_date(ms: int) -> str:
    """Convert millisecond timestamp to YYYY-MM-DD string."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_utils_dates.py -v
```

Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/utils/__init__.py src/utils/dates.py tests/unit/test_utils_dates.py
git commit -m "feat(utils): add dates module with date_to_ms / ms_to_date"
```

---

## Task 2 — Add `src/utils/validation.py`

**Files:**
- Create: `src/utils/validation.py`
- Create: `tests/unit/test_utils_validation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_utils_validation.py`:

```python
"""Tests for src.utils.validation — pure enum validation helpers."""
import pytest

from src.utils.validation import (
    TASK_PRIORITY_VALUES,
    TASK_STATUS_VALUES,
    validate_priority,
    validate_status,
)


def test_task_status_values_canonical():
    assert TASK_STATUS_VALUES == ("Mới", "Đang làm", "Hoàn thành", "Huỷ")


def test_task_priority_values_canonical():
    assert TASK_PRIORITY_VALUES == ("Cao", "Trung bình", "Thấp")


def test_validate_status_case_insensitive():
    assert validate_status("mới") == "Mới"
    assert validate_status("ĐANG LÀM") == "Đang làm"


def test_validate_status_returns_canonical_form():
    assert validate_status("Hoàn thành") == "Hoàn thành"


def test_validate_status_invalid_raises():
    with pytest.raises(ValueError, match="Status 'foo' không hợp lệ"):
        validate_status("foo")


def test_validate_priority_case_insensitive():
    assert validate_priority("cao") == "Cao"
    assert validate_priority("TRUNG BÌNH") == "Trung bình"


def test_validate_priority_invalid_raises():
    with pytest.raises(ValueError, match="Priority 'urgent' không hợp lệ"):
        validate_priority("urgent")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_utils_validation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.validation'`.

- [ ] **Step 3: Implement `src/utils/validation.py`**

```python
"""Enum validation helpers — pure, no I/O."""

# Canonical values — must match Lark field options exactly.
TASK_STATUS_VALUES: tuple[str, ...] = ("Mới", "Đang làm", "Hoàn thành", "Huỷ")
TASK_PRIORITY_VALUES: tuple[str, ...] = ("Cao", "Trung bình", "Thấp")


def validate_status(status: str) -> str:
    """Return the canonical status string, case-insensitive. Raises ValueError if unknown."""
    for v in TASK_STATUS_VALUES:
        if status.lower() == v.lower():
            return v
    raise ValueError(
        f"Status '{status}' không hợp lệ. Chỉ dùng: {', '.join(TASK_STATUS_VALUES)}"
    )


def validate_priority(priority: str) -> str:
    """Return the canonical priority string, case-insensitive. Raises ValueError if unknown."""
    for v in TASK_PRIORITY_VALUES:
        if priority.lower() == v.lower():
            return v
    raise ValueError(
        f"Priority '{priority}' không hợp lệ. Chỉ dùng: {', '.join(TASK_PRIORITY_VALUES)}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_utils_validation.py -v
```

Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add src/utils/validation.py tests/unit/test_utils_validation.py
git commit -m "feat(utils): add validation module with task status/priority enums"
```

---

## Task 3 — Add `src/utils/text.py`

**Files:**
- Create: `src/utils/text.py`
- Create: `tests/unit/test_utils_text.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_utils_text.py`:

```python
"""Tests for src.utils.text — pure string helpers."""
from src.utils.text import full_name


def test_full_name_first_and_last():
    assert full_name({"first_name": "Đạt", "last_name": "Trần"}) == "Đạt Trần"


def test_full_name_first_only():
    assert full_name({"first_name": "Đạt"}) == "Đạt"


def test_full_name_last_only():
    assert full_name({"last_name": "Trần"}) == "Trần"


def test_full_name_empty():
    assert full_name({}) == ""


def test_full_name_strips_whitespace():
    assert full_name({"first_name": "  Đạt  ", "last_name": ""}) == "Đạt"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_utils_text.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.utils.text'`.

- [ ] **Step 3: Implement `src/utils/text.py`**

This is a behavior-preserving extraction — the body matches the original `_full_name` in [src/channels/telegram.py:32-33](../../src/channels/telegram.py#L32) exactly. Do not "improve" the implementation in this phase.

```python
"""Pure text helpers — no I/O."""


def full_name(user: dict) -> str:
    """Compose 'first_name last_name' from a provider-supplied user dict.

    Handles missing fields. Used by any channel that exposes split
    first/last name fields (Telegram today; other providers may use it later).
    """
    return (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_utils_text.py -v
```

Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/utils/text.py tests/unit/test_utils_text.py
git commit -m "feat(utils): add text module with full_name helper"
```

---

## Task 4 — Update `tools/tasks.py` to use `utils`

**Files:**
- Modify: `src/tools/tasks.py:11-30, 33-41`

- [ ] **Step 1: Replace local helpers with imports**

Open `src/tools/tasks.py`. Find lines 10-13:

```python
# Canonical enum values — must match Lark field options exactly
TASK_STATUS_VALUES = ("Mới", "Đang làm", "Hoàn thành", "Huỷ")
TASK_PRIORITY_VALUES = ("Cao", "Trung bình", "Thấp")
```

Replace with:

```python
from src.utils.validation import (
    TASK_PRIORITY_VALUES,
    TASK_STATUS_VALUES,
    validate_priority,
    validate_status,
)
from src.utils.dates import date_to_ms, ms_to_date
```

(Keep this import block right after the other `from src.*` imports near the top of the file.)

- [ ] **Step 2: Delete the now-duplicated local definitions**

Delete lines that defined the old local helpers (currently at `src/tools/tasks.py:15-41`):

```python
def _validate_status(status: str) -> str: ...
def _validate_priority(priority: str) -> str: ...
def _date_to_ms(date_str: str) -> int: ...
def _ms_to_date(ms: int) -> str: ...
```

- [ ] **Step 3: Rename callers — drop the leading underscore**

Inside `src/tools/tasks.py`, replace each call site:

| Old | New |
|---|---|
| `_validate_status(...)` | `validate_status(...)` |
| `_validate_priority(...)` | `validate_priority(...)` |
| `_date_to_ms(...)` | `date_to_ms(...)` |
| `_ms_to_date(...)` | `ms_to_date(...)` |

Use editor "Replace All" within the file. Verify with:

```bash
grep -n "_validate_status\|_validate_priority\|_date_to_ms\|_ms_to_date" src/tools/tasks.py
```

Expected: no matches.

- [ ] **Step 4: Boot-check — import the module**

```bash
python -c "from src.tools import tasks; print('OK')"
```

Expected: `OK` printed, no ImportError.

- [ ] **Step 5: Run the existing tasks test if any**

```bash
pytest tests/unit/test_task_completion.py -v 2>&1 | tail -20
```

Expected: tests run (pass or skip — anything other than ImportError on `src.tools.tasks` is acceptable here; some tests may still fail on unrelated reasons).

- [ ] **Step 6: Commit**

```bash
git add src/tools/tasks.py
git commit -m "refactor(tools/tasks): use src.utils for date/validation helpers"
```

---

## Task 5 — Update `tools/people.py` and `tools/projects.py` to use `utils`

**Files:**
- Modify: `src/tools/people.py:14-19`
- Modify: `src/tools/projects.py:25-32`

- [ ] **Step 1: `tools/people.py` — replace local `_date_to_ms`**

Open `src/tools/people.py`. Near line 14, find:

```python
def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)
```

Delete those lines. At the top of the file (with other `from src.*` imports), add:

```python
from src.utils.dates import date_to_ms
```

- [ ] **Step 2: `tools/people.py` — rename caller**

Find:

```python
deadline_ms = _date_to_ms(deadline) if deadline else None
```

Replace with:

```python
deadline_ms = date_to_ms(deadline) if deadline else None
```

Verify:

```bash
grep -n "_date_to_ms" src/tools/people.py
```

Expected: no matches.

- [ ] **Step 3: `tools/projects.py` — same treatment**

Open `src/tools/projects.py`. Delete the local `_date_to_ms` function. Add `from src.utils.dates import date_to_ms` near the top. Replace `_date_to_ms(deadline)` with `date_to_ms(deadline)` at both call sites.

Verify:

```bash
grep -n "_date_to_ms" src/tools/projects.py
```

Expected: no matches.

- [ ] **Step 4: Boot-check both modules**

```bash
python -c "from src.tools import people, projects; print('OK')"
```

Expected: `OK` printed.

- [ ] **Step 5: Commit**

```bash
git add src/tools/people.py src/tools/projects.py
git commit -m "refactor(tools): use src.utils.dates instead of local _date_to_ms duplicates"
```

---

## Task 6 — Update `channels/telegram.py` to use `utils.text.full_name`

**Files:**
- Modify: `src/channels/telegram.py:32-33` and 4 call sites

- [ ] **Step 1: Add the import + delete the local helper**

Open `src/channels/telegram.py`. Near the top, with other `from src.*` imports, add:

```python
from src.utils.text import full_name
```

Delete the local helper at lines 32-33:

```python
def _full_name(user: dict) -> str:
    return (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip()
```

- [ ] **Step 2: Rename callers**

In `src/channels/telegram.py`, replace every call to `_full_name(...)` with `full_name(...)`. There are 4 sites (around lines 145, 173, 197, 441). Use editor "Replace All" within the file.

Verify:

```bash
grep -n "_full_name" src/channels/telegram.py
```

Expected: no matches.

- [ ] **Step 3: Boot-check**

```bash
python -c "from src.channels.telegram import TelegramMessenger; print('OK')"
```

Expected: `OK` printed.

- [ ] **Step 4: Commit**

```bash
git add src/channels/telegram.py
git commit -m "refactor(channels/telegram): use src.utils.text.full_name"
```

---

## Task 7 — Create `src/infrastructure/` package + move `openai_client.py`

**Why first:** `services/qdrant.py` imports `services.openai_client`. Moving openai first means qdrant only needs one import-rewrite later.

**Files:**
- Create: `src/infrastructure/__init__.py`
- Move: `src/services/openai_client.py` → `src/infrastructure/openai_client.py`

- [ ] **Step 1: Create the package**

Create `src/infrastructure/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Move the file**

```bash
git mv src/services/openai_client.py src/infrastructure/openai_client.py
```

- [ ] **Step 3: Update every caller**

Find all callers:

```bash
grep -rln "from src.services import.*openai_client\|from src.services.openai_client" src/ tests/
```

Expected files (verify the list before editing):
- `src/advisor.py`
- `src/agent.py`
- `src/context_builder.py`
- `src/group_onboarding.py`
- `src/main.py`
- `src/onboarding.py`
- `src/scheduler.py`
- `src/services/qdrant.py`
- `src/tools/group.py`
- `src/tools/ideas.py`
- `src/tools/note.py`
- `src/tools/summary.py`
- `src/tools/tasks.py`

In each file, rewrite the import. Two patterns to handle:

Pattern A — `from src.services import openai_client` (or with other names):

```python
# OLD
from src.services import openai_client
from src.services import lark, openai_client, qdrant
# NEW
from src.infrastructure import openai_client
from src.services import lark, qdrant       # leave non-moved imports in place for now
from src.infrastructure import openai_client
```

(For combined imports, split into two lines: one for `src.services` (still has `lark`, `qdrant`, `cohere`, `telegram` for now) and one for `src.infrastructure` with just `openai_client`.)

Pattern B — local `from src.services import openai_client as _oai` inside a function:

```python
# OLD
from src.services import openai_client as _oai
# NEW
from src.infrastructure import openai_client as _oai
```

- [ ] **Step 4: Update existing tests**

```bash
grep -rln "src.services.openai_client\|from src.services import.*openai_client" tests/
```

If any test file matches, update its imports the same way.

- [ ] **Step 5: Verify no stale references**

```bash
grep -rn "src.services.openai_client\|from src.services import.*openai_client" src/ tests/
```

Expected: no matches.

- [ ] **Step 6: Boot-check**

```bash
python -c "from src.infrastructure import openai_client; print('OK')"
python -c "import src.main; print('OK')"
```

Expected: both print `OK`. The `src.main` import is the strongest check — it transitively imports nearly everything.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(infrastructure): move openai_client from services to infrastructure"
```

---

## Task 8 — Move `lark.py` → `infrastructure/lark_client.py`

**Files:**
- Move: `src/services/lark.py` → `src/infrastructure/lark_client.py`
- Update existing test: `tests/unit/test_lark_provision.py:3`

- [ ] **Step 1: Move the file**

```bash
git mv src/services/lark.py src/infrastructure/lark_client.py
```

- [ ] **Step 2: Find all callers**

```bash
grep -rln "from src.services import.*\\blark\\b\|from src.services.lark\|from src.services import lark as" src/ tests/
```

Expected callers:
- `src/agent.py`
- `src/context_builder.py`
- `src/group_onboarding.py`
- `src/identity.py`
- `src/main.py`
- `src/onboarding.py`
- `src/scheduler.py`
- `src/tools/communication.py`
- `src/tools/group.py`
- `src/tools/ideas.py`
- `src/tools/join.py`
- `src/tools/people.py`
- `src/tools/projects.py`
- `src/tools/reminder.py`
- `src/tools/reset.py`
- `src/tools/summary.py`
- `src/tools/tasks.py`
- `tests/unit/test_lark_provision.py`

- [ ] **Step 3: Rewrite imports — keep `lark` as the local name**

The module is renamed `lark_client.py` but callers should keep using `lark.search_records(...)` etc. for minimal churn. Use the import-as-alias pattern:

| Old | New |
|---|---|
| `from src.services import lark` | `from src.infrastructure import lark_client as lark` |
| `from src.services import lark as _lark` | `from src.infrastructure import lark_client as _lark` |
| `from src.services import lark, telegram` | Split into two lines: `from src.infrastructure import lark_client as lark` and `from src.services import telegram` |
| `from src.services import lark, openai_client` (already touched in Task 7) | `from src.infrastructure import lark_client as lark, openai_client` |

In `tests/unit/test_lark_provision.py:3`:

```python
# OLD
import src.services.lark as lark_svc
# NEW
import src.infrastructure.lark_client as lark_svc
```

- [ ] **Step 4: Verify no stale references**

```bash
grep -rn "src.services.lark\|from src.services import.*\\blark\\b" src/ tests/
```

Expected: no matches (other than `lark_svc` alias mentions inside test files — those are fine).

- [ ] **Step 5: Boot-check**

```bash
python -c "from src.infrastructure import lark_client; print('OK')"
python -c "import src.main; print('OK')"
```

Expected: both print `OK`.

- [ ] **Step 6: Run the lark provision test**

```bash
pytest tests/unit/test_lark_provision.py -v
```

Expected: tests run (pass or fail on unrelated logic — but no ImportError).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(infrastructure): move lark client; rename to lark_client"
```

---

## Task 9 — Move `qdrant.py` → `infrastructure/qdrant_client.py`

**Files:**
- Move: `src/services/qdrant.py` → `src/infrastructure/qdrant_client.py`

- [ ] **Step 1: Move the file**

```bash
git mv src/services/qdrant.py src/infrastructure/qdrant_client.py
```

- [ ] **Step 2: Update qdrant_client.py's own internal openai import**

After moving, edit `src/infrastructure/qdrant_client.py` line ~21:

```python
# OLD
from src.services import openai_client
# NEW
from src.infrastructure import openai_client
```

(Verify by `grep -n "from src" src/infrastructure/qdrant_client.py` — should reference only `src.infrastructure`.)

- [ ] **Step 3: Find all callers**

```bash
grep -rln "from src.services import.*qdrant\|from src.services.qdrant\|from src.services import qdrant as" src/ tests/
```

Expected callers:
- `src/agent.py`
- `src/main.py`
- `src/onboarding.py`
- `src/tools/ideas.py`
- `src/tools/note.py`
- `src/tools/reset.py`
- `src/tools/search.py`
- `src/tools/tasks.py`

- [ ] **Step 4: Rewrite imports — keep `qdrant` as the local name**

| Old | New |
|---|---|
| `from src.services import qdrant` | `from src.infrastructure import qdrant_client as qdrant` |
| `from src.services import qdrant as _qdrant_mod` | `from src.infrastructure import qdrant_client as _qdrant_mod` |
| `from src.services import lark, qdrant, telegram` | `from src.infrastructure import lark_client as lark, qdrant_client as qdrant` then `from src.services import telegram` |
| `from src.services import qdrant, openai_client` | `from src.infrastructure import qdrant_client as qdrant, openai_client` |

- [ ] **Step 5: Verify no stale references**

```bash
grep -rn "src.services.qdrant\|from src.services import.*qdrant" src/ tests/
```

Expected: no matches.

- [ ] **Step 6: Boot-check**

```bash
python -c "from src.infrastructure import qdrant_client; print('OK')"
python -c "import src.main; print('OK')"
```

Expected: both print `OK`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(infrastructure): move qdrant client; rename to qdrant_client"
```

---

## Task 10 — Move `cohere.py` → `infrastructure/cohere_client.py`

**Files:**
- Move: `src/services/cohere.py` → `src/infrastructure/cohere_client.py`

- [ ] **Step 1: Move the file**

```bash
git mv src/services/cohere.py src/infrastructure/cohere_client.py
```

- [ ] **Step 2: Find all callers**

```bash
grep -rln "from src.services import.*cohere\|from src.services.cohere" src/ tests/
```

Expected callers:
- `src/main.py` (only one based on current grep — verify the list before editing)

- [ ] **Step 3: Rewrite imports — keep `cohere` as the local name**

| Old | New |
|---|---|
| `from src.services import cohere` | `from src.infrastructure import cohere_client as cohere` |
| `from src.services import cohere, lark, openai_client, qdrant, telegram` | Split: `from src.infrastructure import cohere_client as cohere, lark_client as lark, openai_client, qdrant_client as qdrant` and `from src.services import telegram` |

- [ ] **Step 4: Verify no stale references**

```bash
grep -rn "src.services.cohere\|from src.services import.*cohere" src/ tests/
```

Expected: no matches.

- [ ] **Step 5: Boot-check**

```bash
python -c "from src.infrastructure import cohere_client; print('OK')"
python -c "import src.main; print('OK')"
```

Expected: both print `OK`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(infrastructure): move cohere client; rename to cohere_client"
```

---

## Task 11 — Verify `src/services/` only contains `telegram.py`

**Files:**
- Read: `src/services/`

- [ ] **Step 1: Confirm directory contents**

```bash
ls src/services/
```

Expected output (exactly):

```
__init__.py
telegram.py
```

If anything else is present, find out why before continuing.

- [ ] **Step 2: Confirm no caller still imports anything from `src.services` other than `telegram`**

```bash
grep -rn "from src.services import" src/ tests/ | grep -v "telegram"
```

Expected: no matches.

If a caller still imports something else from `src.services`, fix it now (it should be a non-telegram leftover from Tasks 7-10).

- [ ] **Step 3: Run the full unit test suite**

```bash
pytest tests/unit/ -v 2>&1 | tail -40
```

Expected: tests collect and run without `ModuleNotFoundError` from `src.services.<not-telegram>`. Test failures unrelated to imports (existing logic-failing tests) are acceptable for this phase — we are not fixing tests in Phase 1.

- [ ] **Step 4: Smoke-test boot**

```bash
python -c "import src.main; print('OK')"
```

Expected: `OK` printed.

- [ ] **Step 5: Commit (no-op commit if everything was already clean)**

If `git status` shows any residual changes (e.g., a missed import fix), commit:

```bash
git add -A
git commit -m "refactor(services): finalize phase 1 — only telegram remains in services/"
```

If `git status` is clean, skip this step.

---

## Task 12 — Manual smoke test

**Files:** None (runtime smoke test)

- [ ] **Step 1: Start the bot locally**

```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Expected: Logs show:

```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

And one of:

```
telegram | INFO  | Polling started as @<bot_username>
```

If startup throws, copy the traceback and fix the missed import. Common cause: a `src.services.X` import inside a string / `noqa` comment / function-local import that the grep missed.

- [ ] **Step 2: Send a DM to the bot in Telegram**

Send: `hello`

Expected: bot replies with the normal secretary response (depends on onboarding state for your test account, but **must not crash** with ImportError).

Watch the server log for any traceback containing `src.services.<not-telegram>`. If you see one, kill the server, fix the import, and restart.

- [ ] **Step 3: Send a basic tool-using message**

If your account is already onboarded and has a Lark workspace, send: `tạo task test giao Đạt deadline 2026-12-31`

Expected: bot creates the task in Lark and replies. If this fails, it indicates a logic regression — check the date-helper rename at the call site.

- [ ] **Step 4: Stop the server**

`Ctrl-C` in the terminal.

- [ ] **Step 5: Final state check**

```bash
git log --oneline | head -15
```

Expected: ~10 commits prefixed with `feat(utils):` or `refactor(...)` from this phase.

```bash
git status
```

Expected: clean working tree.

- [ ] **Step 6: Optional commit if smoke test surfaced a bug-fix commit**

If Step 1-3 surfaced a missed import that you committed during Step 1, that is fine — it's part of the phase. No additional action needed.

---

## Done Criteria

- [ ] `src/utils/` exists with `dates.py`, `validation.py`, `text.py`, all unit-tested.
- [ ] `src/infrastructure/` exists with `lark_client.py`, `qdrant_client.py`, `openai_client.py`, `cohere_client.py`.
- [ ] `src/services/` contains only `__init__.py` and `telegram.py`.
- [ ] No file in `src/` or `tests/` imports `src.services.lark`, `src.services.qdrant`, `src.services.openai_client`, or `src.services.cohere`.
- [ ] No file defines a local `_date_to_ms` / `_ms_to_date` / `_validate_status` / `_validate_priority` / `_full_name` (utility duplicates eliminated).
- [ ] `python -c "import src.main"` succeeds.
- [ ] `pytest tests/unit/test_utils_dates.py tests/unit/test_utils_validation.py tests/unit/test_utils_text.py -v` is fully green.
- [ ] Manual smoke test in Task 12 passes.

When all checked, Phase 1 is done. Next: come back to writing-plans skill to draft Phase 2 (schema migration).
