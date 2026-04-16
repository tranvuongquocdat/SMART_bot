"""
group_onboarding.py — Group registration flow.

Steps:
  1. Check bot is admin
  2. Ask which workspace this group belongs to
  3. Ask which project (or none)
  4. Confirm → db.add_group() → introduce bot
"""
import json
import logging
from datetime import date

from src import db
from src.services import lark, openai_client, telegram

logger = logging.getLogger("group_onboarding")

# In-memory state: {group_chat_id: {"step": str, ...}}
_sessions: dict[int, dict] = {}


def is_group_onboarding(group_chat_id: int) -> bool:
    return group_chat_id in _sessions


async def start(group_chat_id: int, sender_id: int) -> None:
    """Entry point — check admin rights first."""
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

    # Admin confirmed — start workspace selection
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
    _sessions[group_chat_id] = {"step": "pick_workspace", "bosses": bosses, "sender_id": sender_id}


async def handle(text: str, group_chat_id: int, group_name: str = "") -> None:
    session = _sessions.get(group_chat_id)
    if not session:
        return

    step = session["step"]
    if step == "pick_workspace":
        await _step_pick_workspace(text, group_chat_id, group_name, session)
    elif step == "pick_project":
        await _step_pick_project(text, group_chat_id, session)
    elif step == "confirm":
        await _step_confirm(text, group_chat_id, session)


async def _step_pick_workspace(text: str, group_chat_id: int, group_name: str, session: dict) -> None:
    bosses = session["bosses"]
    boss_list = "\n".join(f"{i}: {b['company']}" for i, b in enumerate(bosses, 1))

    result = await _classify(
        f"User chọn workspace từ danh sách sau:\n{boss_list}\n\n"
        "Trả về JSON: {\"index\": <số thứ tự trừ 1, bắt đầu từ 0>, hoặc -1 nếu không rõ}",
        text,
    )
    idx = result.get("index", -1)
    if not isinstance(idx, int) or idx < 0 or idx >= len(bosses):
        await telegram.send(group_chat_id, "Chưa rõ bạn chọn workspace nào. Bạn có thể nói lại không?")
        return

    boss = bosses[idx]
    session["boss"] = boss
    session["group_name"] = group_name

    # Fetch projects from Lark
    projects = []
    table_projects = boss.get("lark_table_projects", "")
    if table_projects:
        try:
            records = await lark.search_records(boss["lark_base_token"], table_projects)
            projects = [
                {"name": r.get("Tên dự án", r.get("Name", "")), "record_id": r.get("record_id", "")}
                for r in records
                if r.get("Tên dự án") or r.get("Name")
            ]
        except Exception:
            logger.exception("Failed to fetch projects for boss %s", boss["chat_id"])

    session["projects"] = projects

    if not projects:
        session["step"] = "confirm"
        session["project_id"] = None
        await telegram.send(
            group_chat_id,
            f"Đã chọn workspace *{boss['company']}*.\n"
            "Workspace này không có dự án nào để link. Xác nhận setup không? (có/không)",
        )
        return

    lines = [f"Đã chọn *{boss['company']}*. Nhóm này phục vụ dự án nào?\n"]
    for i, p in enumerate(projects, 1):
        lines.append(f"{i}. {p['name']}")
    lines.append(f"{len(projects) + 1}. Không thuộc dự án cụ thể")
    await telegram.send(group_chat_id, "\n".join(lines))
    session["step"] = "pick_project"


async def _step_pick_project(text: str, group_chat_id: int, session: dict) -> None:
    projects = session["projects"]
    project_list = "\n".join(f"{i}: {p['name']}" for i, p in enumerate(projects, 1))
    project_list += f"\n{len(projects) + 1}: Không thuộc dự án cụ thể"

    result = await _classify(
        f"User chọn dự án từ danh sách:\n{project_list}\n\n"
        "Trả về JSON: {\"index\": <số thứ tự trừ 1, bắt đầu từ 0>, hoặc -1 nếu không rõ, "
        "hoặc \"none\" nếu không thuộc dự án}",
        text,
    )
    idx = result.get("index")
    if idx == "none" or idx == len(projects):
        session["project_id"] = None
        project_name = "không thuộc dự án cụ thể"
    elif isinstance(idx, int) and 0 <= idx < len(projects):
        session["project_id"] = projects[idx]["record_id"]
        project_name = projects[idx]["name"]
    else:
        await telegram.send(group_chat_id, "Chưa rõ bạn chọn dự án nào. Bạn có thể nói lại không?")
        return

    boss = session["boss"]
    session["step"] = "confirm"
    await telegram.send(
        group_chat_id,
        f"Sẽ link nhóm này vào:\n"
        f"- Workspace: *{boss['company']}*\n"
        f"- Dự án: *{project_name}*\n\n"
        "Xác nhận không? (có/không)",
    )


async def _step_confirm(text: str, group_chat_id: int, session: dict) -> None:
    result = await _classify(
        "User xác nhận hay từ chối. Trả về JSON: {\"confirmed\": true} hoặc {\"confirmed\": false}",
        text,
    )
    if not result.get("confirmed"):
        _sessions.pop(group_chat_id, None)
        await telegram.send(group_chat_id, "Đã huỷ. Tag em lại khi muốn setup nhé.")
        return

    boss = session["boss"]
    project_id = session.get("project_id")
    group_name = session.get("group_name", "")

    await db.add_group(group_chat_id, boss["chat_id"], group_name, project_id)

    # Write initial group note
    initial_note = (
        f"Nhóm: {group_name}\n"
        f"Workspace: {boss['company']}\n"
        f"Setup: {date.today().isoformat()}"
    )
    await db.update_note(boss["chat_id"], "group", str(group_chat_id), initial_note)

    _sessions.pop(group_chat_id, None)

    await telegram.send(
        group_chat_id,
        f"Xong! Em đã được link vào *{boss['company']}*.\n\n"
        "Các bạn chưa đăng ký với em, nhắn */start* để em nhận ra trong nhóm nhé. "
        "Tag em bất cứ lúc nào cần hỗ trợ!",
    )
    logger.info("[group_onboarding] group %d linked to boss %s", group_chat_id, boss["chat_id"])


async def _classify(system_prompt: str, text: str) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
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
        return {}
