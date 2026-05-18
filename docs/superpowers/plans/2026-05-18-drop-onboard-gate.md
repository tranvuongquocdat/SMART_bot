# Drop Onboard-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the secretary handle people who have never DM'd the bot — assign tasks, set reminders, query workload for stub Persons (no Chat ID) just like onboarded members.

**Architecture:** Single rule block added to the secretary system prompt teaches the LLM the unified flow (list_people → confirm → add_people if missing → continue). Four tool descriptions get small edits to stop contradicting the new rule. Service / DB / schema layers stay untouched — `add_people`, `_resolve_task_targets`, and Lark Person table already support `chat_id = NULL`.

**Tech Stack:** Python 3.12, pytest (asyncio_mode = auto), no new deps.

**Spec:** `docs/superpowers/specs/2026-05-18-drop-onboard-gate-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `src/agent/secretary_agent.py:71-133` | Insert "Người chưa onboard" rule block in `SECRETARY_PROMPT` |
| Modify | `src/agent/tool_definitions.py:23, 131, 527` (+ scan for similar) | Strip gating phrases from `create_task.assignee`, `add_people.chat_id`, `create_reminder` description |
| Create | `tests/unit/test_secretary_prompt_stub_rule.py` | Assert prompt contains the rule block + both disambiguation cases |
| Create | `tests/unit/test_tool_desc_no_chatid_gate.py` | Assert removed gating phrases are gone from descriptions |
| Create | `tests/unit/test_add_people_stub.py` | Regression: `add_people(name="Tân")` (no chat_id) creates Lark row, skips `membership.activate` |
| Create | `tests/unit/test_create_task_stub_assignee.py` | Regression: `create_task` with stub assignee → Lark record + group announce + no DM attempt |
| Modify (if needed) | `src/services/people_service.py` | Add Unicode/diacritic normalization to `get_people` fuzzy match if missing |
| Modify (if needed) | `src/services/membership_service.py` | Add stub-Person name-match fallback to `activate()` if missing |

---

## Task 1: Add "Người chưa onboard" rule block to system prompt

**Files:**
- Test: `tests/unit/test_secretary_prompt_stub_rule.py` (create)
- Modify: `src/agent/secretary_agent.py:71-133`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_secretary_prompt_stub_rule.py`:

```python
"""Regression: secretary prompt must teach the LLM how to handle people
who have never DM'd the bot (no Chat ID). Without this rule the LLM
refuses or routes around assignment for unknown names."""
from src.agent.secretary_agent import SECRETARY_PROMPT


def test_prompt_contains_stub_section_heading():
    assert "## Người chưa onboard" in SECRETARY_PROMPT


def test_prompt_states_chat_id_is_optional():
    # The core claim: a Person row without Chat ID is still a valid Person.
    text = SECRETARY_PROMPT
    assert "không nhất thiết" in text and "Chat ID" in text


def test_prompt_has_four_step_resolution_flow():
    # The rule must enumerate the lookup → confirm → add_people → action flow.
    # We assert by looking for the four numbered markers within a window of
    # the section heading.
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 1200]
    for marker in ("1.", "2.", "3.", "4."):
        assert marker in block, f"missing step marker {marker!r} in rule block"


def test_prompt_covers_duplicate_name_disambiguation():
    # When multiple people share a name, the LLM must confirm which one.
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 1200]
    assert "Trùng nhiều người" in block or "trùng nhiều" in block.lower()


def test_prompt_covers_fuzzy_match_confirmation():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 1200]
    assert "fuzzy" in block.lower() or "gần đúng" in block


def test_prompt_covers_bulk_team_add():
    idx = SECRETARY_PROMPT.index("## Người chưa onboard")
    block = SECRETARY_PROMPT[idx : idx + 1200]
    assert "danh sách" in block.lower() and "add_people" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_secretary_prompt_stub_rule.py -v`
Expected: All 6 tests FAIL because `"## Người chưa onboard"` does not yet exist in the prompt.

- [ ] **Step 3: Insert rule block into `SECRETARY_PROMPT`**

In `src/agent/secretary_agent.py`, locate the closing line of the prompt (currently line 132 ending with `Telegram giới hạn).`, followed by line 133 `"""`). Insert the new section between the last bullet of `## Identity rules` and the closing `"""`:

```python
## Identity rules
- chat_id là nguồn duy nhất xác định 1 người; tên có thể trùng/nhập nhằng/typo.
- Khi cần nhắn/nhắc/check ai đó mà Lark record thiếu Chat ID, GỌI resolve_person trước — hệ thống có thể đã biết chat_id qua bosses/memberships/seen_contacts.
- get_communication_log trả 2 section: outbound_messages (bot gửi qua send_dm/reminder) VÀ messages DM thread. Đọc cả 2 rồi mới kết luận.
- Khi resolve_person trả cùng 1 chat_id ở nhiều dòng khác source, và 1 dòng là lark_people chưa có Chat ID — đề xuất link_contact_to_person. Nếu boss chưa xác nhận rõ, hỏi confirm trước khi gắn.
- Nếu link_contact_to_person trả [CONFLICT] — KHÔNG tự overwrite; báo boss và chờ xác nhận.
- Trong group mà cần danh sách admin, gọi get_group_admins. Không list được non-admin (Telegram giới hạn).

## Người chưa onboard
- Một Person trong Lark không nhất thiết phải có Chat ID. Người chưa từng DM bot vẫn lưu là Person bình thường — chỉ là bot không DM riêng được; mọi tin gửi cho họ sẽ fallback vào group nguồn hoặc báo sếp.
- Trước khi giao task / đặt nhắc / cập nhật cho ai đó, làm theo thứ tự:
  1. Dùng list_people hoặc get_people để tra cứu tên.
  2. Trùng nhiều người cùng tên → confirm sếp muốn người nào, liệt kê kèm group/role để phân biệt, KHÔNG tự đoán.
  3. Chỉ fuzzy gần đúng (vd "Tân" → có "Tân Nguyễn") → confirm "ý sếp là Tân Nguyễn ạ, hay một người Tân khác?".
  4. Không thấy → add_people(name=..., để trống Chat ID, kèm group/role nếu sếp nói rõ) rồi tiếp tục action gốc.
- Khi sếp đưa danh sách (vd "team gồm A, B, C") → gọi add_people mỗi người một lần trong cùng turn.
- Stub Person (chưa có Chat ID) xuất hiện bình thường trong list_people, get_workload, get_project_report — không bỏ qua họ.
"""
```

The change is purely additive: do not touch the Identity rules block above it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_secretary_prompt_stub_rule.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent/secretary_agent.py tests/unit/test_secretary_prompt_stub_rule.py
git commit -m "feat(prompt): teach secretary to handle stub Person (no Chat ID)

Add 'Người chưa onboard' rule block: list_people → confirm
duplicates/fuzzy → add_people stub → continue action. Covers bulk
team-add and assignment-to-unknown paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Strip onboard-gate phrases from tool descriptions

**Files:**
- Test: `tests/unit/test_tool_desc_no_chatid_gate.py` (create)
- Modify: `src/agent/tool_definitions.py:23, 131, 527`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_tool_desc_no_chatid_gate.py`:

```python
"""Regression: tool descriptions must not contradict the secretary
prompt's stub-Person rule. Phrases that imply Chat ID is required, or
that the assignee must already exist, are forbidden."""
from src.agent.tool_definitions import TOOL_DEFINITIONS


def _tool(name: str) -> dict:
    for t in TOOL_DEFINITIONS:
        if t["function"]["name"] == name:
            return t["function"]
    raise AssertionError(f"tool {name!r} not found")


def test_create_task_assignee_does_not_require_existing_person():
    desc = _tool("create_task")["parameters"]["properties"]["assignee"]["description"]
    assert "dùng đúng tên trong danh sách nhân sự" not in desc


def test_create_task_assignee_mentions_add_people_fallback():
    desc = _tool("create_task")["parameters"]["properties"]["assignee"]["description"]
    assert "add_people" in desc


def test_create_reminder_does_not_require_chat_id():
    desc = _tool("create_reminder")["description"]
    assert "danh sách tên có Chat ID" not in desc


def test_create_reminder_mentions_add_people_fallback():
    desc = _tool("create_reminder")["description"]
    assert "add_people" in desc


def test_add_people_chat_id_is_channel_agnostic():
    desc = _tool("add_people")["parameters"]["properties"]["chat_id"]["description"]
    # Must not single out Telegram as the only channel.
    assert "Chat ID Telegram (nếu biết)" not in desc
    # Should still mention that it can be left blank.
    assert "bỏ trống" in desc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tool_desc_no_chatid_gate.py -v`
Expected: All 5 tests FAIL on the current descriptions.

- [ ] **Step 3: Edit tool descriptions**

In `src/agent/tool_definitions.py`:

**Edit at line 23** — `create_task.assignee.description`:
```python
# Before:
"assignee": {"type": "string", "description": "Tên người được giao (dùng đúng tên trong danh sách nhân sự)"},
# After:
"assignee": {"type": "string", "description": "Tên người được giao. Nếu chưa có trong Lark, gọi add_people thêm trước (Chat ID không bắt buộc)."},
```

**Edit at line 131** — `add_people.chat_id.description`:
```python
# Before:
"chat_id": {"type": "integer", "description": "Chat ID Telegram (nếu biết). Thường chưa có, bỏ trống"},
# After:
"chat_id": {"type": "integer", "description": "Chat ID kênh đã DM bot (Telegram/Zalo/...). Khi sếp thêm thủ công thường chưa có, bỏ trống."},
```

**Edit at line 527** — `create_reminder.description`:
```python
# Before:
"description": "Tạo nhắc nhở vào một thời điểm cụ thể. Khi giờ tới, bot tự gửi tin cho người nhận (DM riêng). Mỗi call tạo 1 reminder cho 1 đích (1 người hoặc sếp nếu target trống). Cần nhắc NHIỀU NGƯỜI (vd 'nhắc cả nhóm', 'nhắc team'): gọi tool này NHIỀU LẦN trong 1 turn — mỗi người một call, cùng `remind_at`. Trước khi gọi, dùng list_people / check_team_engagement để lấy danh sách tên có Chat ID.",
# After:
"description": "Tạo nhắc nhở vào một thời điểm cụ thể. Khi giờ tới, bot gửi cho người nhận (DM riêng nếu có Chat ID; fallback group nguồn hoặc báo sếp nếu chưa). Mỗi call tạo 1 reminder cho 1 đích (1 người hoặc sếp nếu target trống). Cần nhắc NHIỀU NGƯỜI: gọi tool này NHIỀU LẦN trong 1 turn — mỗi người một call, cùng `remind_at`. Nếu target chưa có Person row, gọi add_people trước (Chat ID không bắt buộc).",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_tool_desc_no_chatid_gate.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent/tool_definitions.py tests/unit/test_tool_desc_no_chatid_gate.py
git commit -m "feat(tools): drop chat-id / known-name gating in tool descriptions

Stop telling the LLM that assignees must be in the existing people
list or that reminder targets need a Chat ID. Direct it to add_people
(stub) instead. Aligns with the new secretary prompt rule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Regression test — add_people without Chat ID creates stub

**Files:**
- Test: `tests/unit/test_add_people_stub.py` (create)

This task adds a regression guard. The current code already supports stub creation (line 69 `if chat_id:` and line 85 `if chat_id and ctx.boss_chat_id:` in `src/services/people_service.py`). The test locks in that behavior so a future refactor can't silently reintroduce the gate.

- [ ] **Step 1: Write the test**

Create `tests/unit/test_add_people_stub.py`:

```python
"""Regression: add_people(name=...) without Chat ID must:
  - write a Person row in Lark
  - NOT call membership_service.activate (no chat_id to bind)
  - NOT raise
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.context import ChatContext
from src.services import people_service


def _ctx() -> ChatContext:
    return ChatContext(
        chat_id="boss-1",
        boss_chat_id="boss-1",
        boss_name="Sếp",
        sender_name="Sếp",
        sender_type="boss",
        is_group=False,
        lark_base_token="base-tok",
        lark_table_people="tblPeople",
        lark_table_tasks="tblTasks",
        lark_table_projects="tblProjects",
        lark_table_reminders="tblReminders",
        lark_table_notes="tblNotes",
        lark_table_workload="tblWorkload",
    )


@pytest.mark.asyncio
async def test_add_people_stub_creates_lark_row_without_chat_id():
    with patch("src.services.people_service.lark.create_record",
               new=AsyncMock(return_value={"record_id": "recABC"})) as mock_create, \
         patch("src.services.people_service.membership_service.activate",
               new=AsyncMock()) as mock_activate:
        result = await people_service.add_people(
            _ctx(),
            name="Tân",
            group="Media",
            person_type="member",
        )

    # Lark row was written
    mock_create.assert_awaited_once()
    fields = mock_create.await_args.args[2]
    assert fields["Tên"] == "Tân"
    assert fields["Type"] == "member"
    assert fields["Nhóm"] == "Media"
    # Chat ID field MUST NOT be present (stub)
    assert "Chat ID" not in fields

    # membership.activate must NOT be called (no chat_id)
    mock_activate.assert_not_awaited()

    assert "Tân" in result
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/unit/test_add_people_stub.py -v`
Expected: PASS (current code already supports this; the test pins the behavior).

If the test FAILS, do not modify the test — fix `src/services/people_service.py:54-101` to match the assertions. Most likely failure: `ChatContext` constructor signature has shifted; in that case update the `_ctx()` helper to match real construction (check `src/context.py` for the dataclass / TypedDict definition).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_add_people_stub.py
git commit -m "test(people): pin add_people stub behaviour (no Chat ID)

Lock in that add_people without chat_id writes a Lark Person row,
skips membership.activate, and does not raise. Guards against the
onboard-gate sneaking back in via refactor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Regression test — create_task with stub assignee

**Files:**
- Test: `tests/unit/test_create_task_stub_assignee.py` (create)

Verifies the end-to-end claim from the spec: `create_task` with an assignee that has no Chat ID should still write the Lark task record, post the group announce (when `ctx.is_group`), and skip the DM attempt silently. Behavior is already in `src/services/tasks_service.py:150-229` (commit `fd0a320` silenced the warning).

- [ ] **Step 1: Write the test**

Create `tests/unit/test_create_task_stub_assignee.py`:

```python
"""Regression: create_task(assignee=<stub name>) must:
  - write a Lark task record with Assignee filled
  - announce in the source group (when called from group context)
  - NOT attempt a DM (no Chat ID to send to)
  - NOT raise
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.context import ChatContext
from src.services import tasks_service


def _group_ctx() -> ChatContext:
    return ChatContext(
        chat_id="group-42",
        boss_chat_id="boss-1",
        boss_name="Sếp",
        sender_name="Sếp",
        sender_type="boss",
        is_group=True,
        lark_base_token="base-tok",
        lark_table_people="tblPeople",
        lark_table_tasks="tblTasks",
        lark_table_projects="tblProjects",
        lark_table_reminders="tblReminders",
        lark_table_notes="tblNotes",
        lark_table_workload="tblWorkload",
    )


@pytest.mark.asyncio
async def test_create_task_with_stub_assignee_announces_in_group_and_skips_dm():
    with patch("src.services.tasks_service.lark.create_record",
               new=AsyncMock(return_value={"record_id": "recT1"})), \
         patch("src.services.tasks_service._embed_and_upsert",
               new=AsyncMock()), \
         patch("src.services.tasks_service._find_assignee_chat_id",
               new=AsyncMock(return_value=(None, False))) as mock_find, \
         patch("src.services.tasks_service._notify_assignee_task",
               new=AsyncMock()) as mock_notify, \
         patch("src.services.tasks_service.telegram.send",
               new=AsyncMock()) as mock_send:
        result = await tasks_service.create_task(
            _group_ctx(),
            name="design banner",
            assignee="Tân",
            deadline="2026-05-22",
        )

    # Resolver was called for the stub name
    mock_find.assert_awaited()
    # DM notify NEVER scheduled — no chat_id resolved
    mock_notify.assert_not_awaited()
    # Group announce DID fire
    mock_send.assert_awaited()
    posted_chat_id, posted_text = mock_send.await_args.args[0], mock_send.await_args.args[1]
    assert posted_chat_id == "group-42"
    assert "design banner" in posted_text
    assert "Tân" in posted_text

    assert isinstance(result, str)
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/unit/test_create_task_stub_assignee.py -v`
Expected: PASS. If it fails, inspect the actual failure:

- If `_find_assignee_chat_id` signature differs: read `src/services/tasks_service.py` near line 220, adjust the patch return shape to match.
- If `telegram.send` signature differs: read the call at `src/services/tasks_service.py:209` and adjust the assertion args index.
- DO NOT relax assertions to make a real regression pass — if the production code is genuinely attempting a DM for a stub, fix `tasks_service` instead.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_create_task_stub_assignee.py
git commit -m "test(tasks): pin stub-assignee path — group announce + silent DM skip

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Verify `get_people` normalizes diacritics / whitespace; fix if missing

**Files:**
- Investigate: `src/services/people_service.py` (look for the `get_people` function around the file)
- Modify (only if missing): same file
- Test: `tests/unit/test_get_people_fuzzy_diacritic.py` (create if fix applied)

The spec assumes `get_people` can match "Tan" → "Tân" → "Tân Nguyễn". If normalization is absent the LLM will create duplicate stubs from typos.

- [ ] **Step 1: Read the current `get_people` implementation**

Run: `grep -n "def get_people\|def _normalize\|unicodedata\|lower()" src/services/people_service.py`

Open the function. Determine: does it call `unicodedata.normalize("NFD", ...)` (or equivalent) and strip combining marks before comparing names? Does it lowercase and trim?

- [ ] **Step 2: Decision point**

- If diacritic + whitespace + case normalization is already in place → **skip steps 3-5, mark this task complete with a one-line commit note**:
  ```bash
  git commit --allow-empty -m "chore: verify get_people already normalizes diacritics — no change needed"
  ```
  Then move to Task 6.

- If normalization is missing or partial → continue with steps 3-5 below.

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_get_people_fuzzy_diacritic.py`:

```python
"""Fuzzy match must be diacritic- and case-insensitive so that stubs
created from a typo ('Tan') still surface the canonical row ('Tân
Nguyễn'), avoiding duplicate stubs."""
from unittest.mock import AsyncMock, patch

import pytest

from src.context import ChatContext
from src.services import people_service


def _ctx() -> ChatContext:
    return ChatContext(
        chat_id="boss-1",
        boss_chat_id="boss-1",
        boss_name="Sếp",
        sender_name="Sếp",
        sender_type="boss",
        is_group=False,
        lark_base_token="base-tok",
        lark_table_people="tblPeople",
        lark_table_tasks="tblTasks",
        lark_table_projects="tblProjects",
        lark_table_reminders="tblReminders",
        lark_table_notes="tblNotes",
        lark_table_workload="tblWorkload",
    )


_LARK_ROWS = [
    {"record_id": "recA", "fields": {"Tên": "Tân Nguyễn", "Type": "member"}},
    {"record_id": "recB", "fields": {"Tên": "Minh Lê",     "Type": "member"}},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["tan", "Tan", "TÂN", " tân "])
async def test_get_people_matches_across_diacritics_case_whitespace(query):
    with patch("src.services.people_service.lark.list_records",
               new=AsyncMock(return_value=_LARK_ROWS)):
        result = await people_service.get_people(_ctx(), search_name=query)

    # Must mention Tân Nguyễn regardless of query form.
    assert "Tân Nguyễn" in result, f"failed for query={query!r}: {result}"
```

- [ ] **Step 4: Run test to confirm failure, then add normalization**

Run: `uv run pytest tests/unit/test_get_people_fuzzy_diacritic.py -v`
Expected: fails for at least one parametrized input.

Add a helper to `src/services/people_service.py` (above `get_people`):

```python
import unicodedata


def _normalize_name(s: str) -> str:
    """Lowercase + strip combining marks + collapse whitespace.
    Used for fuzzy match so 'Tan', 'TÂN', ' tân ' all hit 'Tân'."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())
```

Then, inside `get_people`, normalize both the query and each candidate name before substring/equality comparison. The exact insertion line depends on the function body — make the change at every place a name is compared, not just one.

- [ ] **Step 5: Run test to verify pass, commit**

Run: `uv run pytest tests/unit/test_get_people_fuzzy_diacritic.py -v`
Expected: PASS for all four query forms.

```bash
git add src/services/people_service.py tests/unit/test_get_people_fuzzy_diacritic.py
git commit -m "fix(people): normalize diacritics + case in get_people fuzzy match

Prevents stub duplicates when boss types 'Tan' but the canonical row
is 'Tân Nguyễn'. Required by the stub-Person rule in the secretary
prompt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Verify `membership_service.activate` can resolve an existing stub Person by name; fix if missing

**Files:**
- Investigate: `src/services/membership_service.py`
- Modify (only if missing): same file
- Test: `tests/unit/test_activate_links_stub_by_name.py` (create if fix applied)

When stub Tân (created by boss while Tân had not DM'd yet) later messages the bot on Zalo, `activate()` is the chokepoint that writes the new `chat_id`. If it doesn't try to match an existing stub Person by name first, it will create a *second* Person row — splitting Tân's tasks across two records.

- [ ] **Step 1: Read the current `activate` implementation**

Run: `grep -n "def activate\|name=\|name_lower\|lark.*People\|search.*by.*name" src/services/membership_service.py`

Open `activate`. Determine: when a new `chat_id` arrives with a `name`, does the function look up an existing Lark Person row by name (normalized) before creating a new one?

- [ ] **Step 2: Decision point**

- If activate already matches by name (or routes through a resolver that does) → **skip steps 3-5**:
  ```bash
  git commit --allow-empty -m "chore: verify membership.activate already matches stub by name — no change needed"
  ```
  Then proceed to the final review.

- If activate does NOT match → continue.

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_activate_links_stub_by_name.py`:

```python
"""When activate() runs for a person whose name already exists as a
stub Person row (no Chat ID), it must link to that row instead of
creating a new one. Otherwise stub Tân's old tasks get orphaned."""
from unittest.mock import AsyncMock, patch

import pytest

from src.services import membership_service


_STUB_ROW = {"record_id": "recStub", "fields": {"Tên": "Tân", "Type": "member"}}


@pytest.mark.asyncio
async def test_activate_links_existing_stub_row_by_name():
    with patch("src.services.membership_service.lark.list_records",
               new=AsyncMock(return_value=[_STUB_ROW])), \
         patch("src.services.membership_service.lark.update_record",
               new=AsyncMock()) as mock_update, \
         patch("src.services.membership_service.lark.create_record",
               new=AsyncMock()) as mock_create, \
         patch("src.services.membership_service._write_membership_row",
               new=AsyncMock()):
        await membership_service.activate(
            chat_id="zalo-uid-123",
            boss_chat_id="boss-1",
            person_type="member",
            name="Tân",
            source="first_dm",
            lark_record_id=None,
        )

    # The stub row should be UPDATED (Chat ID added), not duplicated.
    mock_update.assert_awaited()
    update_args = mock_update.await_args.args
    assert update_args[1] == "recStub"  # target record_id
    updated_fields = update_args[2]
    assert "Chat ID" in updated_fields

    mock_create.assert_not_awaited()
```

NOTE: the exact `_write_membership_row` / signature names in the patch may differ in the live file. Open `membership_service.py`, read the actual function names being called inside `activate`, and adjust the `patch` targets accordingly. The shape of the assertion (update vs create) stays the same.

- [ ] **Step 4: Run test, then implement fallback**

Run: `uv run pytest tests/unit/test_activate_links_stub_by_name.py -v`
Expected: FAIL (activate currently doesn't search by name).

In `src/services/membership_service.py`, in `activate`, before creating a new Lark Person row, add:

```python
# Stub-Person fallback: if a row with the same name (normalized) and no
# Chat ID exists in this workspace, reuse it instead of creating a
# duplicate. Lets boss-created stubs auto-link when the person finally
# DMs the bot.
if lark_record_id is None:
    from src.services.people_service import _normalize_name
    rows = await lark.list_records(base_token, table_people)
    target_norm = _normalize_name(name)
    for row in rows:
        f = row.get("fields", {})
        if not f.get("Chat ID") and _normalize_name(f.get("Tên", "")) == target_norm:
            lark_record_id = row["record_id"]
            await lark.update_record(base_token, lark_record_id, {"Chat ID": chat_id})
            break
```

Replace `base_token` / `table_people` with whatever variables `activate` already has (or fetch via the same workspace-helper it uses). DO NOT introduce a new arg.

- [ ] **Step 5: Run test to verify pass, commit**

Run: `uv run pytest tests/unit/test_activate_links_stub_by_name.py -v`
Expected: PASS.

```bash
git add src/services/membership_service.py tests/unit/test_activate_links_stub_by_name.py
git commit -m "fix(membership): activate links stub Person by name instead of dup

When a boss-created stub Person (no Chat ID) later DMs the bot,
activate() now reuses the existing row and writes the Chat ID into
it, instead of creating a parallel row that would orphan the stub's
tasks/reminders.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Final regression run + memory update

- [ ] **Step 1: Run the full unit suite**

Run: `uv run pytest tests/unit -q`
Expected: all green. If anything unrelated is broken (e.g. the pre-existing `tests/integration/*` `_migrate_schema` import error we already noted), do not fix in this plan — leave it for the slimming pass (subsystem #3).

- [ ] **Step 2: Smoke test in real chat (manual, by user)**

Hand off to the user with this checklist:

1. In a registered group, send "@bot giao task X cho Tân deadline thứ 6" (Tân not in people list).
   - Expected: bot asks "Tân nào ạ?" or "Em chưa có Tân, thêm mới nhé?". After confirmation, task created + announce in group.
2. In boss DM: "thêm vào team: A, B, C".
   - Expected: 3 `add_people` calls, summary reply.
3. Ask "tổng workload team tuần này".
   - Expected: stubs appear in the list like normal members.

- [ ] **Step 3: Mark spec + plan complete**

Move the spec frontmatter status from `approved` to `implemented` if your team uses that convention. Otherwise, no doc update needed.

```bash
git log --oneline -10   # sanity check the commit graph
```

---

## Self-Review Notes

- Spec section "Components touched" → covered by Tasks 1, 2.
- Spec section "Data flow examples" Case 1-3 → covered by prompt rule (Task 1).
- Spec section "Data flow examples" Case 4 (reminder fire for stub) → relies on existing `_resolve_task_targets` fallback; no new code needed, locked in by Task 4's group-announce assertion.
- Spec section "Data flow examples" Case 5 (stub later onboards) → covered by Task 6.
- Spec assumption "get_people normalizes" → Task 5.
- Spec assumption "activate matches stub by name" → Task 6.
- Spec testing matrix (5 tests) → mapped: `test_secretary_prompt_stub_rule.py` (T1), `test_tool_desc_no_chatid_gate.py` (T2), `test_add_people_stub.py` (T3), `test_create_task_stub_assignee.py` (T4), plus the conditional T5/T6 tests.

No placeholders. No "TBD". Tests show real assertions. Code blocks contain exact text to insert.
