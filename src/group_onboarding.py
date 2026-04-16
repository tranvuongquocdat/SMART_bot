"""
group_onboarding.py — Group registration flow.

Uses a single LLM collector: each turn extracts workspace/project/confirmation
fields and generates the reply in one shot. State accumulates in DB until
boss_chat_id + project_id + confirmed are all set.
"""
import json
import logging
from datetime import date

from src import db
from src.services import lark, openai_client, telegram

logger = logging.getLogger("group_onboarding")

# ---------------------------------------------------------------------------
# LLM collector
# ---------------------------------------------------------------------------

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
{{
  "extracted": {{
    "boss_chat_id": 123 | null,
    "project_id": "recXXX" | "none" | null,
    "load_projects": true | false,
    "confirmed": true | false | null
  }},
  "reply": "..."
}}
"""


async def _group_collector(session: dict, text: str, boss_list: str, project_list: str) -> dict:
    state_copy = {
        k: v for k, v in session.items()
        if k not in ("bosses", "projects", "sender_id")
    }
    prompt = _GROUP_COLLECTOR_PROMPT.format(
        state_json=json.dumps(state_copy, ensure_ascii=False),
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
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
    return {"extracted": {}, "reply": ""}


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def is_group_onboarding(group_chat_id: int) -> bool:
    state = await db.get_onboarding_state(group_chat_id)
    return bool(state)


async def start(group_chat_id: int, sender_id: int) -> None:
    """Entry point — check admin rights first, then begin workspace selection."""
    bot_id = await telegram.get_bot_id()
    if bot_id:
        member = await telegram.get_chat_member(group_chat_id, bot_id)
        status = member.get("status", "")
        if status not in ("administrator", "creator"):
            await telegram.send(
                group_chat_id,
                "Để em hoạt động đầy đủ trong nhóm, nhờ admin promote em lên làm *Administrator*:\n"
                "Settings → Administrators → Add Administrator → chọn @bot\n\n"
                "Sau khi xong, tag em lại để tiếp tục nhé.",
            )
            return

    bosses = await db.get_all_bosses()
    if not bosses:
        await telegram.send(
            group_chat_id,
            "Chưa có workspace nào được đăng ký. Nhờ sếp đăng ký với bot trước nhé.",
        )
        return

    lines = ["Nhóm này thuộc workspace nào?\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} (sếp: {b['name']})")
    await telegram.send(group_chat_id, "\n".join(lines))

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
