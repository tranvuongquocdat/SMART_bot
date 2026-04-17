"""Onboarding for new users.

Uses a single LLM collector: each turn extracts any available fields and
generates the reply in one shot. State accumulates in DB until all required
fields are present, then completion runs.

Three paths:
  boss    — create a new workspace
  member  — join an existing team as member
  partner — join an existing team as partner
"""

import json
import logging

from src import db
from src.services import lark, openai_client, qdrant
from src.services import telegram
from src.services import telegram as tg

logger = logging.getLogger("onboarding")

# join flow state: {chat_id: {"step": str, ...}} — short-lived, in-memory is fine
_join_sessions: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

_PERSONA = """\
Bạn là trợ lý thư ký giám đốc AI — lịch sự, chuyên nghiệp, ấm áp như thư ký thật sự.
- Xưng "em", gọi sếp/giám đốc là "anh/chị", thành viên/đối tác là "bạn"
- Ngắn gọn, tự nhiên, thân thiện — không sáo rỗng, không khách sáo quá
- Có thể dùng *in đậm* cho thông tin quan trọng
- KHÔNG dùng emoji
- Trả lời tối đa 3-4 câu, đi thẳng vào vấn đề\
"""

# ---------------------------------------------------------------------------
# LLM collector (replaces 7 step handlers + 7 classify prompts)
# ---------------------------------------------------------------------------

_COLLECTOR_PROMPT = """\
You are a smart onboarding assistant for an AI secretary app.
Extract structured fields from the user's message and generate a natural reply.

## Current collected state (GROUND TRUTH — do not contradict)
{state_json}

## Available workspaces (for member/partner to join)
{boss_list}

## State-aware rules (STRICT — follow before any other rule)
- If a field in state is NOT null, NEVER ask for it again. Move to the next missing field.
- Step order for boss path: type → name → company → language → confirm
- Step order for member/partner path: type → name → language → target_boss_id → confirm
- When all required fields are set and confirmed is null: SUMMARIZE collected info and ASK FOR CONFIRMATION once.

## Extraction rules
- "type": sếp/giám đốc/chủ → "boss"; nhân viên/thành viên → "member"; đối tác/partner/freelancer → "partner"
- "language": infer from the user's own writing style if not stated — Vietnamese → "vi", English → "en". Default "vi".
- "target_boss_id": if user mentions a boss name or company, match against available workspaces; return their chat_id (integer). Return null if no match or ambiguous.
- "confirmed":
    - true: explicit yes ("ok", "uh", "đúng", "đúng rồi", "tạo đi", "xác nhận", "yes", "được", "ừ", "đồng ý", "confirm")
    - false: explicit no ("không", "sai", "hủy", "làm lại", "cancel")
    - null: otherwise
- NEVER overwrite an existing non-null state field with null.

## Reply rules
- Write naturally in the user's inferred language.
- Ask ONLY for the NEXT missing field (see step order). Do not re-ask fields already set.
- If confirmed is true: acknowledge and say you are creating the workspace / sending the request.
- If user's message is off-topic (not about onboarding), briefly acknowledge and steer back to the pending step.

Return ONLY valid JSON:
{{
  "extracted": {{
    "type": "boss" | "member" | "partner" | null,
    "name": "..." | null,
    "company": "..." | null,
    "language": "vi" | "en" | "..." | null,
    "target_boss_id": 123 | null,
    "confirmed": true | false | null
  }},
  "reply": "..."
}}
"""


async def _collector(state: dict, text: str, boss_list: str, chat_id: int) -> dict:
    state_copy = {k: v for k, v in state.items() if k != "first"}
    prompt = _COLLECTOR_PROMPT.format(
        state_json=json.dumps(state_copy, ensure_ascii=False),
        boss_list=boss_list or "Chưa có workspace nào.",
    )
    # Load last 10 messages of this DM so LLM sees onboarding dialogue flow
    recent = await db.get_recent(chat_id, limit=10)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in recent if m.get("content")
    ]
    messages = [
        {"role": "system", "content": prompt},
        *history,
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


async def _greeting() -> str:
    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": (
            "Tình huống: Người dùng mới vừa nhắn lần đầu. "
            "Chào, giới thiệu ngắn gọn em là trợ lý thư ký AI giúp quản lý công việc. "
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


# ---------------------------------------------------------------------------
# Completion actions
# ---------------------------------------------------------------------------

async def _complete_boss(chat_id: int, state: dict) -> None:
    """Provision Lark workspace and persist boss record. Called after confirmation."""
    name = state["name"]
    company = state["company"]
    language = state.get("language", "vi")

    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": (
            f"Người dùng xác nhận tạo workspace cho {name} - {company}. "
            "Nói đang tạo, chờ vài giây."
        )},
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


async def _complete_member(chat_id: int, state: dict) -> None:
    """Create pending membership and notify boss."""
    name = state["name"]
    person_type = state["type"]
    language = state.get("language", "vi")
    target_boss_id = state["target_boss_id"]

    all_bosses = await db.get_all_bosses()
    boss = next(
        (b for b in all_bosses
         if b["chat_id"] == target_boss_id or str(b["chat_id"]) == str(target_boss_id)),
        None,
    )
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
        logger.exception(
            "[onboarding] failed to create membership for %s chat_id=%s", person_type, chat_id
        )
        await telegram.send(chat_id, "Có lỗi khi gửi yêu cầu tham gia. Vui lòng thử lại sau.")
        return

    await db.clear_onboarding_state(chat_id)
    logger.info("[onboarding] join request sent (%s) for chat_id=%s", person_type, chat_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def is_onboarding(chat_id: int) -> bool:
    """Return True if chat_id is currently in the onboarding flow."""
    state = await db.get_onboarding_state(chat_id)
    return bool(state)


async def start_onboarding(chat_id: int) -> None:
    """Begin onboarding for a new user."""
    await db.save_onboarding_state(chat_id, {"first": True})
    logger.info("[onboarding] started for chat_id=%s", chat_id)


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

    result = await _collector(state, text, boss_list, chat_id)
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


# ---------------------------------------------------------------------------
# Join flow (discover companies and request to join)
# Keep unchanged — short-lived in-memory sessions
# ---------------------------------------------------------------------------

# Minimal classify helper for join flow only
_CLASSIFY_BOSS_PICK_PROMPT = """
Người dùng đang chọn công ty trong danh sách. Trả về JSON {{"index": N}} với N là index (0-based) của công ty được chọn, hoặc {{"index": -1}} nếu không rõ.
Danh sách công ty: {boss_list}
"""

_EXTRACT_NAME_PROMPT = """\
Trích xuất TÊN NGƯỜI từ tin nhắn. Loại bỏ mọi từ đệm, trợ từ.
Trả về JSON duy nhất: {"name": "..."} hoặc {"name": ""} nếu không tìm thấy tên.\
"""


async def _ai_classify(system_prompt: str, user_text: str) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    content = response.content or ""
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


async def handle_join_inquiry(chat_id: int) -> str:
    """Called when user wants to see available companies. Returns listing message."""
    bosses = await db.get_all_bosses()
    if not bosses:
        return "Hiện chưa có tổ chức nào được đăng ký trên hệ thống."

    lines = ["Các tổ chức hiện đang hoạt động:\n"]
    for i, b in enumerate(bosses, 1):
        lines.append(f"{i}. {b['company']} — sếp: {b['name']}")
    lines.append("\nBạn muốn join tổ chức nào với tư cách nào (nhân viên/đối tác)?")

    _join_sessions[chat_id] = {"step": "pick_company", "bosses": bosses}
    return "\n".join(lines)


def is_join_session(chat_id: int) -> bool:
    return chat_id in _join_sessions


async def handle_join_message(text: str, chat_id: int) -> str:
    session = _join_sessions.get(chat_id)
    if not session:
        return ""

    step = session["step"]

    if step == "pick_company":
        bosses = session["bosses"]
        boss_list = [f"{i}: {b['company']}" for i, b in enumerate(bosses)]
        result = await _ai_classify(
            _CLASSIFY_BOSS_PICK_PROMPT.format(boss_list="\n".join(boss_list)), text
        )
        idx = result.get("index", -1)
        if not isinstance(idx, int) or idx < 0 or idx >= len(bosses):
            return "Tôi chưa rõ bạn muốn join tổ chức nào. Bạn có thể nói lại không?"
        session["target_boss"] = bosses[idx]
        session["step"] = "pick_role"
        return f"Bạn muốn join {bosses[idx]['company']} với tư cách nhân viên hay đối tác?"

    if step == "pick_role":
        lower = text.lower()
        if "đối tác" in lower or "partner" in lower:
            session["role"] = "partner"
        elif "nhân viên" in lower or "member" in lower:
            session["role"] = "member"
        else:
            return "Bạn muốn join với tư cách nhân viên hay đối tác?"
        session["step"] = "get_info"
        return "Bạn có thể giới thiệu về bản thân không? (tên, vai trò, lý do muốn join...)"

    if step == "get_info":
        boss = session["target_boss"]
        role = session["role"]

        name_result = await _ai_classify(_EXTRACT_NAME_PROMPT, text)
        name = name_result.get("name", "Không rõ")

        _db = await db.get_db()
        await db.upsert_membership(
            _db,
            chat_id=str(chat_id),
            boss_chat_id=str(boss["chat_id"]),
            person_type=role,
            name=name,
            status="pending",
            request_info=text,
        )

        request_msg = (
            f"Yêu cầu join tổ chức mới!\n\n"
            f"Người dùng chat_id={chat_id} ({name}) muốn join với tư cách {role}.\n"
            f"Thông tin: {text}\n\n"
            f"Reply: 'approve {chat_id}' hoặc 'reject {chat_id}'\n"
            f"Hoặc điều chỉnh: 'approve {chat_id} nhân viên nhóm Marketing'"
        )
        await tg.send_message(boss["chat_id"], request_msg)

        del _join_sessions[chat_id]
        return (f"Yêu cầu của bạn đã được gửi đến {boss['company']}. "
                f"Bạn sẽ được thông báo khi sếp xử lý.")

    return ""


async def handle_boss_join_decision(text: str, boss_chat_id: str) -> str | None:
    """
    Process boss reply to a join request.
    Patterns: 'approve <chat_id>', 'reject <chat_id>', 'approve <chat_id> <adjustments>'
    Returns response string if handled, None if not a join decision.
    """
    import re
    m = re.match(r'(approve|reject)\s+(\d+)(.*)?', text.strip().lower())
    if not m:
        return None

    action = m.group(1)
    target_id = m.group(2)
    adjustments = (m.group(3) or "").strip()

    _db = await db.get_db()
    membership = await db.get_membership(_db, target_id, boss_chat_id)
    if not membership or membership["status"] != "pending":
        return None

    boss = await db.get_boss(_db, boss_chat_id)

    if action == "reject":
        await db.upsert_membership(_db, target_id, boss_chat_id,
                                   membership["person_type"], membership["name"], "rejected")
        await tg.send_message(int(target_id),
            f"Yêu cầu join {boss['company']} của bạn đã bị từ chối.")
        return f"Đã từ chối yêu cầu của user {target_id}."

    # Approve — parse role adjustments
    person_type = membership["person_type"]
    if adjustments:
        if "đối tác" in adjustments or "partner" in adjustments:
            person_type = "partner"
        elif "nhân viên" in adjustments or "member" in adjustments:
            person_type = "member"

    fields = {
        "Tên": membership["name"],
        "Chat ID": int(target_id),
        "Type": person_type,
        "Ghi chú": membership.get("request_info", ""),
    }
    rec = await lark.create_record(boss["lark_base_token"], boss["lark_table_people"], fields)

    await db.upsert_membership(_db, target_id, boss_chat_id, person_type,
                               membership["name"], "active",
                               lark_record_id=rec.get("record_id"))

    await tg.send_message(int(target_id),
        f"Yêu cầu join {boss['company']} của bạn đã được chấp nhận với tư cách {person_type}. "
        f"Hãy bắt đầu trò chuyện với thư ký AI nhé!")

    return f"Đã approve user {target_id} với tư cách {person_type}."
