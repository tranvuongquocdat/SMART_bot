# Onboarding LLM Collector Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-step state machine in `onboarding.py` and 3-step machine in `group_onboarding.py` with a single LLM collector that accumulates fields per turn and completes in as few messages as possible.

**Architecture:** Each turn, one LLM call both extracts fields AND generates the natural reply. Fields accumulate in the DB-persisted state dict. The LLM is told which fields are already collected and only asks for what's missing. Completion logic (Lark provisioning, membership creation) is extracted into `_complete_boss` and `_complete_member` — identical code to what's already in `_step_boss_confirm` and `_step_member_name`.

**Tech Stack:** Python 3.12, aiosqlite (onboarding state), Claude/OpenAI API (via openai_client), python-telegram-bot

---

## File Map

| File | What changes |
|------|-------------|
| `src/onboarding.py` | Replace `_CLASSIFY_*`/`_EXTRACT_*` prompts + `_ai_classify`/`_ai_reply` + 7 step handlers with `_COLLECTOR_PROMPT` + `_collector()` + `_greeting()`; extract `_complete_boss` + `_complete_member`; rewrite `handle_onboard_message` |
| `src/group_onboarding.py` | Replace `_classify` + 3 step handlers with `_GROUP_COLLECTOR_PROMPT` + `_group_collector()`; extract `_complete_group`; update `start()` initial state; rewrite `handle()` |

No changes to `agent.py`, `db.py`, or any other file.

---

### Task 1: Rewrite `onboarding.py` with LLM collector

**Files:**
- Modify: `src/onboarding.py` (full rewrite of the collect/step section; keep completion + join flow)
- Test: `tests/unit/test_onboarding_collector.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_onboarding_collector.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _llm_response(extracted: dict, reply: str):
    """Build a fake openai_client response returning the given JSON."""
    import json
    resp = MagicMock()
    resp.content = json.dumps({"extracted": extracted, "reply": reply})
    return resp, {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_first_message_shows_greeting():
    from src import onboarding
    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value={"first": True}), \
         patch("src.onboarding.db.save_onboarding_state", new_callable=AsyncMock), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response({}, "Xin chào!")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock) as mock_send:
        await onboarding.handle_onboard_message("hi", 999)
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_extracts_all_boss_fields_in_one_message():
    """If LLM extracts type+name+company+language in one shot, state becomes complete."""
    from src import onboarding
    extracted = {"type": "boss", "name": "Đạt", "company": "ABC Corp", "language": "vi", "confirmed": None, "target_boss_id": None}
    state_saved = {}

    async def fake_save(chat_id, state):
        state_saved.update(state)

    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value={"first": False}), \
         patch("src.onboarding.db.save_onboarding_state", new_callable=AsyncMock,
               side_effect=fake_save), \
         patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock, return_value=[]), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response(extracted, "Tuyệt! Xác nhận tạo workspace?")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock):
        await onboarding.handle_onboard_message("tôi là sếp tên Đạt công ty ABC Corp", 999)

    assert state_saved.get("type") == "boss"
    assert state_saved.get("name") == "Đạt"
    assert state_saved.get("company") == "ABC Corp"


@pytest.mark.asyncio
async def test_confirmation_triggers_complete_boss():
    """When confirmed=True and all boss fields present, _complete_boss is called."""
    from src import onboarding
    extracted = {"type": None, "name": None, "company": None, "language": None, "confirmed": True, "target_boss_id": None}
    existing_state = {"type": "boss", "name": "Đạt", "company": "ABC", "language": "vi", "confirmed": None}

    with patch("src.onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=existing_state), \
         patch("src.onboarding.db.get_all_bosses", new_callable=AsyncMock, return_value=[]), \
         patch("src.onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_response(extracted, "Đang tạo workspace...")), \
         patch("src.onboarding.telegram.send", new_callable=AsyncMock), \
         patch("src.onboarding._complete_boss", new_callable=AsyncMock) as mock_complete:
        await onboarding.handle_onboard_message("ok tạo đi", 999)

    mock_complete.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/dat_macbook/Documents/2025/ý tưởng mới/Dự án hỗ trợ thứ ký giám đốc ảo"
python -m pytest tests/unit/test_onboarding_collector.py -v
```
Expected: FAIL with AttributeError or AssertionError (no `_complete_boss`, old step machine runs)

- [ ] **Step 3: Extract `_complete_boss` from `_step_boss_confirm`**

In `src/onboarding.py`, the current `_step_boss_confirm` function (lines 319-425) contains two things: (1) parsing the confirmation answer, and (2) doing the actual Lark provisioning. We need to extract part 2 into `_complete_boss`.

Add this new function **before** `_step_boss_confirm` (the step handler stays temporarily; we'll delete it in Step 4):
```python
async def _complete_boss(chat_id: int, state: dict) -> None:
    """Provision Lark workspace and persist boss record. Called after confirmation."""
    name = state["name"]
    company = state["company"]
    language = state.get("language", "vi")

    wait_reply = await _greeting()  # simple "đang tạo" message — reuse greeting LLM
    # Actually generate a specific "creating" message:
    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": f"Người dùng xác nhận tạo workspace cho {name} - {company}. Nói đang tạo, chờ vài giây."},
    ]
    resp, _ = await openai_client.chat_with_tools(messages, [])
    await telegram.send(chat_id, (resp.content or "Đang tạo workspace...").strip())

    try:
        ws = await lark.provision_workspace(company)
        base_token = ws["base_token"]
        table_people = ws["table_people"]
        table_tasks = ws["table_tasks"]
        table_projects = ws["table_projects"]
        table_ideas = ws["table_ideas"]
        table_reminders = ws["table_reminders"]
        table_notes = ws["table_notes"]
        logger.info("[onboarding] Lark workspace provisioned for chat_id=%s", chat_id)

        await db.create_boss(
            chat_id, name, company,
            base_token, table_people, table_tasks, table_projects, table_ideas,
            lark_table_reminders=table_reminders,
            lark_table_notes=table_notes,
        )
        logger.info("[onboarding] boss created in DB for chat_id=%s", chat_id)

        _db = await db.get_db()
        await _db.execute(
            "UPDATE bosses SET language = ? WHERE chat_id = ?",
            (language, chat_id),
        )
        await _db.commit()
        logger.info("[onboarding] boss language='%s' saved for chat_id=%s", language, chat_id)

        await db.add_person(chat_id, chat_id, "boss", name)
        await qdrant.provision_collections(chat_id)
        logger.info("[onboarding] Qdrant collections provisioned for chat_id=%s", chat_id)

        await lark.create_record(base_token, table_people, {
            "Tên": name,
            "Chat ID": chat_id,
            "Type": "boss",
        })
        logger.info("[onboarding] boss record added to Lark People table for chat_id=%s", chat_id)

        lark_base_url = f"https://larksuite.com/base/{base_token}"
        messages2 = [
            {"role": "system", "content": _PERSONA},
            {"role": "user", "content": (
                f"Workspace đã tạo xong cho {name} - {company}. "
                "Thông báo thành công, hướng dẫn nhanh: giao task bằng ngôn ngữ tự nhiên, "
                "xem tóm tắt ngày, đặt nhắc nhở, gửi tin nhắn team. "
                "Chúc anh/chị làm việc hiệu quả."
            )},
        ]
        resp2, _ = await openai_client.chat_with_tools(messages2, [])
        success_reply = (resp2.content or "").strip()
        await telegram.send(
            chat_id,
            f"{success_reply}\n\nLark Base: {lark_base_url}\n"
            "(Mở link để xem dữ liệu trực tiếp trên Lark)",
        )

    except Exception:
        logger.exception("[onboarding] provision failed for chat_id=%s", chat_id)
        messages3 = [
            {"role": "system", "content": _PERSONA},
            {"role": "user", "content": "Có lỗi khi tạo workspace. Xin lỗi và đề nghị thử lại sau."},
        ]
        resp3, _ = await openai_client.chat_with_tools(messages3, [])
        await telegram.send(chat_id, (resp3.content or "Có lỗi. Vui lòng thử lại.").strip())
        return

    await db.clear_onboarding_state(chat_id)
    logger.info("[onboarding] completed (boss) for chat_id=%s", chat_id)
```

- [ ] **Step 4: Extract `_complete_member` from `_step_member_name`**

Add this function after `_complete_boss`:
```python
async def _complete_member(chat_id: int, state: dict) -> None:
    """Create pending membership and notify boss. Called once all member fields collected."""
    name = state["name"]
    person_type = state["type"]
    language = state.get("language", "vi")
    target_boss_id = state["target_boss_id"]

    all_bosses = await db.get_all_bosses()
    boss = next((b for b in all_bosses if b["chat_id"] == target_boss_id or str(b["chat_id"]) == str(target_boss_id)), None)
    if not boss:
        await telegram.send(chat_id, "Không tìm thấy workspace. Vui lòng thử lại.")
        return

    try:
        _db = await db.get_db()
        await db.upsert_membership(
            _db,
            chat_id=str(chat_id),
            boss_chat_id=str(boss["chat_id"]),
            person_type=person_type,
            name=name,
            status="pending",
            request_info=f"Đăng ký qua onboarding. Ngôn ngữ: {language}",
        )
        await _db.execute(
            "UPDATE memberships SET language = ? WHERE chat_id = ? AND boss_chat_id = ?",
            (language, str(chat_id), str(boss["chat_id"])),
        )
        await _db.commit()
        logger.info(
            "[onboarding] pending membership: %s %s (chat_id=%s) → boss chat_id=%s",
            person_type, name, chat_id, boss["chat_id"],
        )

        type_label = "thành viên" if person_type == "member" else "đối tác"
        company = boss.get("company") or boss["name"]
        notify_msg = (
            f"Yêu cầu tham gia từ *{name}* (chat_id={chat_id}):\n"
            f"Vai trò: {type_label}\n\n"
            f"Trả lời tự nhiên để duyệt hoặc từ chối."
        )
        await telegram.send(boss["chat_id"], notify_msg)

        messages = [
            {"role": "system", "content": _PERSONA},
            {"role": "user", "content": (
                f"{name} vừa gửi yêu cầu tham gia *{company}* với vai trò {type_label}. "
                "Nói yêu cầu đã gửi tới sếp, sẽ nhận thông báo khi được duyệt."
            )},
        ]
        resp, _ = await openai_client.chat_with_tools(messages, [])
        await telegram.send(chat_id, (resp.content or "Đã gửi yêu cầu.").strip())

    except Exception:
        logger.exception("[onboarding] failed to create membership for %s chat_id=%s",
                         person_type, chat_id)
        await telegram.send(chat_id, "Có lỗi khi gửi yêu cầu tham gia. Vui lòng thử lại sau.")
        return

    await db.clear_onboarding_state(chat_id)
    logger.info("[onboarding] join request sent (%s) for chat_id=%s", person_type, chat_id)
```

- [ ] **Step 5: Add `_COLLECTOR_PROMPT`, `_collector`, `_greeting`, and helper predicates**

Add these after the existing `_PERSONA` constant (before the old `_ai_classify` function):
```python
_COLLECTOR_PROMPT = """\
You are a smart onboarding assistant for an AI secretary app.
Extract structured fields from the user's message and generate a natural reply.

## Current collected state
{state_json}

## Available workspaces (for member/partner to join)
{boss_list}

## Extraction rules
- "type": sếp/giám đốc/chủ → "boss"; nhân viên/thành viên → "member"; đối tác/partner/freelancer → "partner"
- "language": infer from the user's own writing style if not stated — Vietnamese → "vi", English → "en". Default "vi".
- "target_boss_id": if user mentions a boss name or company, match against available workspaces; return their chat_id (integer). Return null if no match or ambiguous.
- "confirmed": set to true if the user is explicitly confirming ("ok", "đúng rồi", "tạo đi", "xác nhận"); false if cancelling ("không", "sai", "hủy", "làm lại"). null otherwise.
- Never overwrite an existing non-null field with null.

## Reply rules
- Write naturally in the user's inferred language.
- Ask ONLY for fields still missing. Priority: type → name → company (boss) or target workspace (member/partner).
- If all required fields for the detected type are present and confirmed is null: summarize and ask for confirmation.
- If confirmed is true: acknowledge and say you are creating the workspace / sending the request.

Return ONLY valid JSON:
{
  "extracted": {
    "type": "boss" | "member" | "partner" | null,
    "name": "..." | null,
    "company": "..." | null,
    "language": "vi" | "en" | "..." | null,
    "target_boss_id": 123 | null,
    "confirmed": true | false | null
  },
  "reply": "..."
}
"""


async def _collector(state: dict, text: str, boss_list: str) -> dict:
    import json as _json
    state_copy = {k: v for k, v in state.items() if k != "first"}
    prompt = _COLLECTOR_PROMPT.format(
        state_json=_json.dumps(state_copy, ensure_ascii=False),
        boss_list=boss_list or "Chưa có workspace nào.",
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    content = (response.content or "").strip()
    try:
        return _json.loads(content)
    except _json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return _json.loads(content[start:end])
            except _json.JSONDecodeError:
                pass
    return {"extracted": {}, "reply": ""}


async def _greeting() -> str:
    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": (
            "Tình huống: Người dùng mới vừa nhắn lần đầu. "
            "Chào, giới thiệu ngắn gọn em là trợ lý thư ký AI. "
            "Hỏi họ là: (1) Sếp/Giám đốc muốn tạo workspace mới, "
            "(2) Thành viên/Nhân viên, hoặc (3) Đối tác. Tối đa 3-4 câu."
        )},
    ]
    resp, _ = await openai_client.chat_with_tools(messages, [])
    return (resp.content or "").strip()


def _boss_fields_complete(state: dict) -> bool:
    return all(state.get(f) for f in ("type", "name", "company", "language"))


def _member_fields_complete(state: dict) -> bool:
    return (
        all(state.get(f) for f in ("type", "name", "language"))
        and state.get("target_boss_id") is not None
    )
```

- [ ] **Step 6: Replace `handle_onboard_message` with the new collector-based version**

In `src/onboarding.py`, replace the entire `handle_onboard_message` function and all step handlers below it (lines 156-590, up to but NOT including `handle_join_inquiry`):

```python
async def handle_onboard_message(text: str, chat_id: int) -> None:
    """Route onboarding message through the LLM collector."""
    state = await db.get_onboarding_state(chat_id) or {}
    is_first = state.pop("first", False)

    if is_first:
        await db.save_onboarding_state(chat_id, state)
        greeting = await _greeting()
        await telegram.send(chat_id, greeting)
        return

    all_bosses = await db.get_all_bosses()
    boss_list = "\n".join(
        f"chat_id={b['chat_id']}: {b['name']} — {b.get('company', '')}"
        for b in all_bosses
    )

    result = await _collector(state, text, boss_list)
    extracted = result.get("extracted", {})
    reply = result.get("reply", "")

    # Merge non-null extracted fields
    for key, val in extracted.items():
        if val is not None:
            state[key] = val

    user_type = state.get("type")

    # Boss path completion
    if user_type == "boss" and _boss_fields_complete(state):
        confirmed = state.get("confirmed")
        if confirmed is True:
            await telegram.send(chat_id, reply)
            await _complete_boss(chat_id, state)
            return
        elif confirmed is False:
            # User wants to restart — clear collected fields
            await db.save_onboarding_state(chat_id, {
                "type": None, "name": None, "company": None,
                "language": None, "confirmed": None,
            })
            await telegram.send(chat_id, reply)
            return
        # confirmed is None — reply already contains confirmation prompt

    # Member/partner path completion
    if user_type in ("member", "partner") and _member_fields_complete(state):
        await telegram.send(chat_id, reply)
        await _complete_member(chat_id, state)
        return

    await db.save_onboarding_state(chat_id, state)
    await telegram.send(chat_id, reply)
```

- [ ] **Step 7: Remove old step handlers and classify prompts**

Delete the following from `src/onboarding.py`:
- `_CLASSIFY_TYPE_PROMPT` constant
- `_CLASSIFY_CONFIRM_PROMPT` constant  
- `_CLASSIFY_BOSS_SEARCH_PROMPT` constant
- `_EXTRACT_NAME_PROMPT` constant
- `_EXTRACT_COMPANY_PROMPT` constant
- `_CLASSIFY_BOSS_PICK_PROMPT` constant
- `_CLASSIFY_LANGUAGE_PROMPT` constant
- `_ai_classify()` function
- `_ai_reply()` function
- `_step_ask_type()` function
- `_step_ask_language()` function
- `_step_boss_name()` function
- `_step_boss_company()` function
- `_step_boss_confirm()` function
- `_step_member_boss()` function
- `_step_member_name()` function

Keep: `_PERSONA`, `is_onboarding`, `start_onboarding`, `handle_join_inquiry`, `is_join_session`, `handle_join_message`, `handle_boss_join_decision`, `_join_sessions`

- [ ] **Step 8: Run tests**

```bash
python -m pytest tests/unit/test_onboarding_collector.py -v
```
Expected: PASS all 3 tests

- [ ] **Step 9: Run all unit tests**

```bash
python -m pytest tests/unit/ -v
```
Expected: all PASS. Note: `test_onboarding_join.py` tests the join flow (unchanged) — those should still pass.

- [ ] **Step 10: Commit**

```bash
git add src/onboarding.py tests/unit/test_onboarding_collector.py
git commit -m "feat: replace onboarding step machine with single LLM collector"
```

---

### Task 2: Rewrite `group_onboarding.py` with LLM collector

**Files:**
- Modify: `src/group_onboarding.py` (full rewrite of collect/step section; keep admin check and `_complete_group`)
- Test: `tests/unit/test_group_onboarding_collector.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_group_onboarding_collector.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def _llm_json(extracted: dict, reply: str):
    resp = MagicMock()
    resp.content = json.dumps({"extracted": extracted, "reply": reply})
    return resp, {}


_BOSSES = [{"chat_id": 100, "name": "Boss A", "company": "Alpha Corp",
            "lark_base_token": "tok", "lark_table_projects": "proj"}]


@pytest.mark.asyncio
async def test_workspace_selection_sets_boss_chat_id():
    from src import group_onboarding
    session = {
        "step": "collecting",
        "boss_chat_id": None,
        "project_id": None,
        "confirmed": None,
        "bosses": _BOSSES,
        "projects": [],
        "group_name": "Dev Group",
        "sender_id": 1,
    }
    extracted = {"boss_chat_id": 100, "project_id": None, "confirmed": None, "load_projects": True}
    saved = {}

    async def fake_save(gid, s):
        saved.update(s)

    with patch("src.group_onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=session), \
         patch("src.group_onboarding.db.save_onboarding_state", new_callable=AsyncMock,
               side_effect=fake_save), \
         patch("src.group_onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_json(extracted, "Chọn dự án nào?")), \
         patch("src.group_onboarding.lark.search_records", new_callable=AsyncMock,
               return_value=[{"Tên dự án": "Dự án X", "record_id": "rec1"}]), \
         patch("src.group_onboarding.telegram.send", new_callable=AsyncMock):
        await group_onboarding.handle("1", -100, "Dev Group")

    assert saved.get("boss_chat_id") == 100
    assert len(saved.get("projects", [])) == 1


@pytest.mark.asyncio
async def test_confirmation_triggers_complete_group():
    from src import group_onboarding
    session = {
        "step": "collecting",
        "boss_chat_id": 100,
        "project_id": "rec1",
        "confirmed": None,
        "bosses": _BOSSES,
        "projects": [{"name": "Dự án X", "record_id": "rec1"}],
        "group_name": "Dev Group",
        "sender_id": 1,
    }
    extracted = {"boss_chat_id": None, "project_id": None, "confirmed": True, "load_projects": False}

    with patch("src.group_onboarding.db.get_onboarding_state", new_callable=AsyncMock,
               return_value=session), \
         patch("src.group_onboarding.openai_client.chat_with_tools", new_callable=AsyncMock,
               return_value=_llm_json(extracted, "Đang setup...")), \
         patch("src.group_onboarding.telegram.send", new_callable=AsyncMock), \
         patch("src.group_onboarding._complete_group", new_callable=AsyncMock) as mock_cg:
        await group_onboarding.handle("có", -100, "Dev Group")

    mock_cg.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_group_onboarding_collector.py -v
```
Expected: FAIL

- [ ] **Step 3: Extract `_complete_group` from `_step_confirm`**

In `src/group_onboarding.py`, add this function before `_step_confirm`:
```python
async def _complete_group(group_chat_id: int, group_name: str, session: dict) -> None:
    """Persist group registration and send intro message."""
    boss = next(
        (b for b in session.get("bosses", []) if b["chat_id"] == session["boss_chat_id"]),
        None,
    )
    if not boss:
        await telegram.send(group_chat_id, "Lỗi: không tìm được workspace. Tag em lại nhé.")
        return

    raw_project_id = session.get("project_id")
    project_id = None if raw_project_id == "none" else raw_project_id

    await db.add_group(group_chat_id, boss["chat_id"], group_name, project_id)

    initial_note = (
        f"Nhóm: {group_name}\n"
        f"Workspace: {boss['company']}\n"
        f"Setup: {date.today().isoformat()}"
    )
    await db.update_note(boss["chat_id"], "group", str(group_chat_id), initial_note)
    await db.clear_onboarding_state(group_chat_id)

    await telegram.send(
        group_chat_id,
        f"Xong! Em đã được link vào *{boss['company']}*.\n\n"
        "Các bạn chưa đăng ký với em, nhắn */start* để em nhận ra trong nhóm nhé. "
        "Tag em bất cứ lúc nào cần hỗ trợ!",
    )
    logger.info("[group_onboarding] group %d linked to boss %s", group_chat_id, boss["chat_id"])
```

- [ ] **Step 4: Add `_GROUP_COLLECTOR_PROMPT` and `_group_collector`**

Add after the existing `logger = ...` line, before the existing `is_group_onboarding` function:
```python
_GROUP_COLLECTOR_PROMPT = """\
You are helping set up a Telegram group for an AI secretary system.
Extract fields from the user's message and generate a natural Vietnamese reply.

## Current state
{state_json}

## Available workspaces
{boss_list}

## Available projects (empty = not loaded yet)
{project_list}

## Rules
- "boss_chat_id": if user selects a workspace by number or name, return that workspace's chat_id (integer).
- "project_id": if user selects a project by number or name, return its record_id (string). If user says no specific project → return "none".
- "load_projects": return true if boss_chat_id was just set and projects list is empty — tells caller to load projects before next turn.
- "confirmed": true if user explicitly confirms; false if cancels.
- If boss_chat_id and project_id are both set and confirmed is null: ask for confirmation.
- Write reply in Vietnamese, concisely.

Return ONLY valid JSON:
{
  "extracted": {
    "boss_chat_id": 123 | null,
    "project_id": "recXXX" | "none" | null,
    "load_projects": true | false,
    "confirmed": true | false | null
  },
  "reply": "..."
}
"""


async def _group_collector(session: dict, text: str, boss_list: str, project_list: str) -> dict:
    import json as _json
    state_copy = {
        k: v for k, v in session.items()
        if k not in ("bosses", "projects", "sender_id")
    }
    prompt = _GROUP_COLLECTOR_PROMPT.format(
        state_json=_json.dumps(state_copy, ensure_ascii=False),
        boss_list=boss_list,
        project_list=project_list or "Chưa load.",
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    content = (response.content or "").strip()
    try:
        return _json.loads(content)
    except _json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return _json.loads(content[start:end])
            except _json.JSONDecodeError:
                pass
    return {"extracted": {}, "reply": ""}
```

- [ ] **Step 5: Rewrite `handle` and update `start`**

Replace the existing `handle` function (currently lines 61-72) with:
```python
async def handle(text: str, group_chat_id: int, group_name: str = "") -> None:
    session = await db.get_onboarding_state(group_chat_id)
    if not session:
        return

    bosses = session.get("bosses", [])
    projects = session.get("projects", [])

    boss_list = "\n".join(
        f"chat_id={b['chat_id']}: {b['company']} (sếp: {b['name']})"
        for b in bosses
    ) or "Không có workspace."

    project_list = (
        "\n".join(
            f"{i+1}. {p['name']} (id={p['record_id']})"
            for i, p in enumerate(projects)
        ) + f"\n{len(projects)+1}. Không thuộc dự án cụ thể"
    ) if projects else ""

    result = await _group_collector(session, text, boss_list, project_list)
    extracted = result.get("extracted", {})
    reply = result.get("reply", "")

    # Merge non-null fields
    for key in ("boss_chat_id", "project_id", "confirmed"):
        val = extracted.get(key)
        if val is not None:
            session[key] = val

    # Load projects lazily when boss just selected
    if extracted.get("load_projects") and session.get("boss_chat_id") and not projects:
        boss = next((b for b in bosses if b["chat_id"] == session["boss_chat_id"]), None)
        if boss and boss.get("lark_table_projects"):
            try:
                records = await lark.search_records(
                    boss["lark_base_token"], boss["lark_table_projects"]
                )
                session["projects"] = [
                    {"name": r.get("Tên dự án", ""), "record_id": r["record_id"]}
                    for r in records if r.get("Tên dự án")
                ]
            except Exception:
                logger.exception("Failed to load projects for boss %s", boss["chat_id"])

    boss_set = session.get("boss_chat_id") is not None
    project_set = session.get("project_id") is not None
    confirmed = session.get("confirmed")

    if boss_set and project_set and confirmed is True:
        await telegram.send(group_chat_id, reply)
        await _complete_group(group_chat_id, group_name, session)
        return
    elif confirmed is False:
        await db.clear_onboarding_state(group_chat_id)
        await telegram.send(group_chat_id, "Đã huỷ. Tag em lại khi muốn setup nhé.")
        return

    await db.save_onboarding_state(group_chat_id, session)
    await telegram.send(group_chat_id, reply)
```

Update `start()` to use the new state schema (replace the `await db.save_onboarding_state(...)` call in `start()`):
```python
    await db.save_onboarding_state(group_chat_id, {
        "step": "collecting",
        "boss_chat_id": None,
        "project_id": None,
        "confirmed": None,
        "bosses": bosses,
        "projects": [],
        "group_name": "",
        "sender_id": sender_id,
    })
```

And remove the lines that built and sent the workspace list from `start()` (since `handle()` will do this on the first user reply). Instead, send a simpler opening:
```python
    lines = ["Nhóm này thuộc workspace nào?\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} (sếp: {b['name']})")
    await telegram.send(group_chat_id, "\n".join(lines))
```
(This stays in `start()` — it asks the first question so the user knows what to reply.)

- [ ] **Step 6: Remove old step handlers and `_classify`**

Delete from `src/group_onboarding.py`:
- `_step_pick_workspace()` function
- `_step_pick_project()` function
- `_step_confirm()` function
- `_classify()` function

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/unit/test_group_onboarding_collector.py -v
```
Expected: PASS both tests

- [ ] **Step 8: Run all unit tests**

```bash
python -m pytest tests/unit/ -v
```
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/group_onboarding.py tests/unit/test_group_onboarding_collector.py
git commit -m "feat: replace group onboarding step machine with single LLM collector"
```
