# Onboarding LLM Collector Redesign — Design Spec

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Replace the step-by-step state machines in `onboarding.py` and `group_onboarding.py` with a single LLM collector that accumulates fields across turns, asks only for what's missing, and completes in as few messages as possible.

**Date:** 2026-04-16

---

## Problem

The current implementation uses a step machine: each step asks one question, waits for the answer, then moves to the next step. A user who says "Tôi là sếp công ty ABC tên Đạt" in their first message gets asked for their name again because the machine is stuck on the `ask_type` step.

The desired design is a **single LLM collector pass**: extract whatever fields are present in any message, accumulate them in state, and only prompt for what's still missing. Language is inferred from the user's own writing style — no need to ask explicitly unless ambiguous.

---

## Scope

Two files only — no new DB tables, no new services:

1. `src/onboarding.py` — personal onboarding collector
2. `src/group_onboarding.py` — group onboarding collector

---

## 1. Personal Onboarding (`onboarding.py`)

### State schema

```python
{
    "type": "boss" | "member" | "partner" | None,
    "name": str | None,
    "company": str | None,          # boss only
    "language": str | None,         # "vi", "en", etc.
    "target_boss_id": int | None,   # member/partner only
    "confirmed": bool | None,       # boss only — True once user confirms workspace creation
    "first": bool,                  # True on very first message — triggers greeting
}
```

### Required fields per type

| Type | Required to complete |
|------|---------------------|
| boss | `type`, `name`, `company`, `language` → then `confirmed=True` |
| member | `type`, `name`, `language`, `target_boss_id` |
| partner | `type`, `name`, `language`, `target_boss_id` |

### Collector prompt

The single LLM call extracts fields AND generates the reply in one shot:

```python
_COLLECTOR_PROMPT = """\
You are a smart onboarding assistant for a Vietnamese AI secretary app.
Extract structured fields from the user's message and generate a natural reply.

## Current collected state
{state_json}

## Available workspaces (for member/partner to join)
{boss_list}

## Extraction rules
- "type": sếp/giám đốc/chủ → "boss"; nhân viên/thành viên → "member"; đối tác/partner/freelancer → "partner"
- "language": infer from the user's own writing style if not stated — Vietnamese → "vi", English → "en". Default "vi".
- "target_boss_id": if user mentions a boss name or company, match against available workspaces; return their chat_id (integer). Return null if no match or ambiguous.
- "confirmed": set to true if the user is explicitly confirming ("ok", "đúng rồi", "tạo đi", "xác nhận"); false if cancelling ("không", "sai", "hủy", "làm lại").
- Never overwrite an existing non-null field with null.

## Reply rules
- Write naturally in the user's inferred language.
- Ask ONLY for fields still missing. Priority: type → name → company (boss) or target workspace (member/partner) → language only if truly ambiguous.
- If all required fields for the detected type are present and confirmed is null: summarize and ask for confirmation.
- If confirmed is true: acknowledge and say you're creating the workspace / sending the request.

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
```

### `_collector(state, text, boss_list) -> dict`

```python
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
```

### New `handle_onboard_message` flow

```python
async def handle_onboard_message(text: str, chat_id: int) -> None:
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

    # Merge non-null fields
    for key, val in extracted.items():
        if val is not None:
            state[key] = val

    user_type = state.get("type")

    # Boss path completion
    if user_type == "boss" and _boss_fields_complete(state):
        confirmed = state.get("confirmed")
        if confirmed is True:
            await telegram.send(chat_id, reply)  # "đang tạo workspace..."
            await _complete_boss(chat_id, state)
            return
        elif confirmed is False:
            # User wants to restart — clear collected fields but stay in onboarding
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

### Helper predicates

```python
def _boss_fields_complete(state: dict) -> bool:
    return all(state.get(f) for f in ("type", "name", "company", "language"))

def _member_fields_complete(state: dict) -> bool:
    return all(state.get(f) for f in ("type", "name", "language")) and state.get("target_boss_id") is not None
```

### `_greeting()` — replaces first-contact message

```python
async def _greeting() -> str:
    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": (
            "Tình huống: Người dùng mới vừa nhắn tin lần đầu. "
            "Chào họ, giới thiệu ngắn gọn em là trợ lý thư ký AI giúp quản lý công việc. "
            "Hỏi họ thuộc nhóm nào: (1) Sếp/Giám đốc muốn tạo workspace mới, "
            "(2) Thành viên/Nhân viên tham gia team có sẵn, "
            "(3) Đối tác tham gia team có sẵn. Tối đa 3-4 câu."
        )},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    return (response.content or "").strip()
```

### `_complete_boss` and `_complete_member`

These extract the completion logic from the current `_step_boss_confirm` and `_step_member_name`. No logic changes — same Lark provisioning, DB writes, Qdrant init, telegram notifications. Move the code, don't change it.

### Remove

- All `_step_*` handlers (7 functions)
- All `_CLASSIFY_*` and `_EXTRACT_*` prompt constants (7 constants)
- `_ai_classify`, `_ai_reply` functions

### Keep unchanged

- `is_onboarding`, `start_onboarding` — public API unchanged
- `_PERSONA` constant
- `handle_join_inquiry`, `is_join_session`, `handle_join_message`, `handle_boss_join_decision` — separate join flow, untouched

---

## 2. Group Onboarding (`group_onboarding.py`)

### State schema

```python
{
    "step": "collecting",           # single collecting phase
    "boss_chat_id": int | None,
    "project_id": str | None,       # record_id, or "none" if user says no project
    "confirmed": bool | None,
    "bosses": [...],                # list of boss dicts, loaded at start
    "projects": [...],              # loaded lazily once boss_chat_id is known
    "group_name": str,
    "sender_id": int,
}
```

### Collector prompt

```python
_GROUP_COLLECTOR_PROMPT = """\
You are helping set up a Telegram group for an AI secretary system.
Extract fields from the user's message and generate a natural reply.

## Current state
{state_json}

## Available workspaces
{boss_list}

## Available projects (empty list means not loaded yet)
{project_list}

## Rules
- "boss_chat_id": if user selects a workspace by number or name, return that workspace's chat_id (integer).
- "project_id": if user selects a project by number or name, return its record_id (string). If user says no specific project → return "none".
- "load_projects": return true if boss_chat_id was just set but projects list is empty — signals caller to load projects before next turn.
- "confirmed": true if user explicitly confirms; false if user cancels.
- If boss_chat_id is set AND project_id is set AND confirmed is null → ask for confirmation.
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
```

### `_group_collector(session, text, boss_list, project_list) -> dict`

```python
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

### New `handle` flow

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

    # Load projects lazily if boss just selected and projects not yet loaded
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

    # Check completion
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

### `_complete_group`

Extract logic from current `_step_confirm` (the part after `if not result.get("confirmed"): return`):
- `await db.add_group(group_chat_id, boss["chat_id"], group_name, project_id)` where `project_id = None if session["project_id"] == "none" else session["project_id"]`
- Write initial note
- `await db.clear_onboarding_state(group_chat_id)`
- Send intro message

### `start()` — update initial state

```python
async def start(group_chat_id: int, sender_id: int) -> None:
    # ... existing admin check unchanged ...

    bosses = await db.get_all_bosses()
    if not bosses:
        await telegram.send(group_chat_id, "Chưa có workspace nào...")
        return

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

    lines = ["Nhóm này thuộc workspace nào?\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} (sếp: {b['name']})")
    await telegram.send(group_chat_id, "\n".join(lines))
```

### Remove

- `_step_pick_workspace`, `_step_pick_project`, `_step_confirm`
- `_classify` helper

### Keep unchanged

- `is_group_onboarding`, `start` signature — public API unchanged
- Admin check logic in `start()`

---

## 3. File Map

| File | Change |
|------|--------|
| `src/onboarding.py` | Replace 7 step handlers + 7 classify prompts + `_ai_classify` + `_ai_reply` with `_COLLECTOR_PROMPT` + `_collector()` + `_greeting()`; extract `_complete_boss` and `_complete_member` from existing step handlers |
| `src/group_onboarding.py` | Replace 3 step handlers + `_classify` with `_GROUP_COLLECTOR_PROMPT` + `_group_collector()`; extract `_complete_group`; update `start()` state schema |

---

## Non-goals

- No DB schema changes
- No changes to `agent.py` (already calls `handle_onboard_message` and `handle`)
- No changes to the join flow (`handle_join_inquiry`, `handle_join_message`, `handle_boss_join_decision`)
- No changes to what information is collected — same fields, same completion actions
