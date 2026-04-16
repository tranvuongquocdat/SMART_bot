"""Onboarding state machine for new users.

Uses AI for everything — understanding intent, extracting info, generating responses.
No hardcoded messages, no keyword matching.

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

# in-memory state: {chat_id: {"step": str, ...}}
_onboarding: dict[int, dict] = {}

# join flow state: {chat_id: {"step": str, ...}}
_join_sessions: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# AI core
# ---------------------------------------------------------------------------

_PERSONA = """\
Bạn là trợ lý thư ký giám đốc AI — lịch sự, chuyên nghiệp, ấm áp như thư ký thật sự.
- Xưng "em", gọi sếp/giám đốc là "anh/chị", thành viên/đối tác là "bạn"
- Ngắn gọn, tự nhiên, thân thiện — không sáo rỗng, không khách sáo quá
- Có thể dùng *in đậm* cho thông tin quan trọng
- KHÔNG dùng emoji
- Trả lời tối đa 3-4 câu, đi thẳng vào vấn đề\
"""


async def _ai_classify(system_prompt: str, user_text: str) -> dict:
    """Send a classification/extraction request to the LLM. Returns parsed JSON."""
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
            return json.loads(content[start:end])
        return {}


async def _ai_reply(situation: str) -> str:
    """Generate a natural response for the given situation."""
    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": f"Tình huống: {situation}\n\nViết câu trả lời:"},
    ]
    response, _ = await openai_client.chat_with_tools(messages, [])
    return (response.content or "").strip()


# ---------------------------------------------------------------------------
# Classification & extraction prompts
# ---------------------------------------------------------------------------

_CLASSIFY_TYPE_PROMPT = """\
Bạn phân loại tin nhắn của người dùng mới. Họ đang cho biết vai trò của mình.

Có 3 loại:
- "boss" = sếp, giám đốc, quản lý, chủ doanh nghiệp, người muốn tạo workspace mới
- "member" = nhân viên, thành viên, người làm trong team
- "partner" = đối tác, cộng tác viên, freelancer, khách hàng

Trả về JSON duy nhất, không giải thích:
{"type": "boss"} hoặc {"type": "member"} hoặc {"type": "partner"} hoặc {"type": "unclear"}

Nếu không rõ → {"type": "unclear"}\
"""

_CLASSIFY_CONFIRM_PROMPT = """\
Người dùng đang được hỏi xác nhận tạo workspace. Họ cần đồng ý hoặc từ chối.

Trả về JSON duy nhất, không giải thích:
{"confirm": true} nếu họ đồng ý (ok, ừ, được, oke, yes, tạo đi, đồng ý, v.v.)
{"confirm": false} nếu họ từ chối hoặc muốn sửa (không, chờ, sai rồi, hủy, v.v.)
{"confirm": null} nếu không liên quan\
"""

_CLASSIFY_BOSS_SEARCH_PROMPT = """\
Người dùng đang chọn team để tham gia. Có danh sách sau:
{boss_list}

Người dùng nói: "{user_text}"

Nếu họ chọn bằng số hoặc nêu tên/công ty khớp 1 kết quả → trả về index (bắt đầu từ 0).
Nếu không rõ hoặc không khớp → trả về -1.

Trả về JSON duy nhất: {{"index": 0}} hoặc {{"index": -1}}\
"""

_EXTRACT_NAME_PROMPT = """\
Trích xuất TÊN NGƯỜI từ tin nhắn. Loại bỏ mọi từ đệm, trợ từ \
(nhé, nha, ạ, à, nè, đây, luôn, hen, ha, nhen, v.v.).

Ví dụ:
- "Đạt nhé" → {"name": "Đạt"}
- "Tôi là Nguyễn Văn Bách" → {"name": "Nguyễn Văn Bách"}
- "Minh đây" → {"name": "Minh"}
- "em tên Linh ạ" → {"name": "Linh"}
- "Trần Văn A nha anh" → {"name": "Trần Văn A"}
- "mình là Hương nè" → {"name": "Hương"}

Trả về JSON duy nhất: {"name": "..."} hoặc {"name": ""} nếu không tìm thấy tên.\
"""

_EXTRACT_COMPANY_PROMPT = """\
Trích xuất TÊN CÔNG TY hoặc TỔ CHỨC từ tin nhắn. Loại bỏ từ đệm, giữ tên chính thức.

Ví dụ:
- "Công ty ABC" → {"company": "ABC"}
- "FPT Software" → {"company": "FPT Software"}
- "bên em là Nova Group nha" → {"company": "Nova Group"}
- "Tập đoàn Vingroup ạ" → {"company": "Vingroup"}
- "Solar Creative nhé anh" → {"company": "Solar Creative"}

Trả về JSON duy nhất: {"company": "..."} hoặc {"company": ""} nếu không tìm thấy.\
"""

_CLASSIFY_BOSS_PICK_PROMPT = """
Người dùng đang chọn công ty trong danh sách. Trả về JSON {{"index": N}} với N là index (0-based) của công ty được chọn, hoặc {{"index": -1}} nếu không rõ.
Danh sách công ty: {boss_list}
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_onboarding(chat_id: int) -> bool:
    """Return True if chat_id is currently in the onboarding flow."""
    return chat_id in _onboarding


def start_onboarding(chat_id: int) -> None:
    """Begin onboarding for a new user."""
    _onboarding[chat_id] = {"step": "ask_type", "first": True}
    logger.info("[onboarding] started for chat_id=%s", chat_id)


async def handle_onboard_message(text: str, chat_id: int) -> None:
    """Route message to the correct handler based on current step."""
    state = _onboarding.get(chat_id)
    if state is None:
        return

    step = state["step"]

    if step == "ask_type":
        await _step_ask_type(text, chat_id, state)
    elif step == "ask_language":
        await _step_ask_language(text, chat_id, state)
    elif step == "boss_name":
        await _step_boss_name(text, chat_id, state)
    elif step == "boss_company":
        await _step_boss_company(text, chat_id, state)
    elif step == "boss_confirm":
        await _step_boss_confirm(text, chat_id, state)
    elif step == "member_boss":
        await _step_member_boss(text, chat_id, state)
    elif step == "member_name":
        await _step_member_name(text, chat_id, state)
    else:
        logger.warning("[onboarding] unknown step=%s for chat_id=%s", step, chat_id)


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------


async def _step_ask_type(text: str, chat_id: int, state: dict) -> None:
    # First contact → greet and ask role
    if state.pop("first", False):
        reply = await _ai_reply(
            "Người dùng mới vừa nhắn tin lần đầu. "
            "Chào họ, giới thiệu ngắn gọn em là trợ lý thư ký AI giúp quản lý công việc. "
            "Hỏi họ thuộc nhóm nào: "
            "(1) Sếp / Giám đốc — muốn tạo workspace mới, "
            "(2) Thành viên / Nhân viên — tham gia team có sẵn, "
            "(3) Đối tác / Partner — tham gia team có sẵn."
        )
        await telegram.send(chat_id, reply)
        return

    result = await _ai_classify(_CLASSIFY_TYPE_PROMPT, text)
    user_type = result.get("type", "unclear")

    if user_type == "boss":
        state["step"] = "ask_language"
        state["type"] = "boss"
        reply = await _ai_reply(
            "Người dùng cho biết họ là sếp/giám đốc. Phản hồi tích cực ngắn gọn. "
            "Sau đó hỏi ngôn ngữ ưa thích: (1) English, (2) Tiếng Việt — "
            "hoặc nhập mã ngôn ngữ khác (ví dụ: fr, ja)."
        )
        await telegram.send(chat_id, reply)

    elif user_type in ("member", "partner"):
        state["step"] = "ask_language"
        state["type"] = user_type
        label = "thành viên" if user_type == "member" else "đối tác"
        reply = await _ai_reply(
            f"Người dùng cho biết họ là {label}. Phản hồi tích cực ngắn gọn. "
            "Sau đó hỏi ngôn ngữ ưa thích: (1) English, (2) Tiếng Việt — "
            "hoặc nhập mã ngôn ngữ khác (ví dụ: fr, ja)."
        )
        await telegram.send(chat_id, reply)

    else:
        reply = await _ai_reply(
            "Người dùng trả lời không rõ vai trò. "
            "Hỏi lại nhẹ nhàng: anh/chị là sếp muốn tạo workspace mới, "
            "hay thành viên/đối tác muốn tham gia team có sẵn?"
        )
        await telegram.send(chat_id, reply)


# ---- Language step -------------------------------------------------------

_CLASSIFY_LANGUAGE_PROMPT = """\
Người dùng đang chọn ngôn ngữ ưa thích.

Quy tắc:
- "1" hoặc "english" hoặc "tiếng anh" → trả về "en"
- "2" hoặc "tiếng việt" hoặc "vietnamese" hoặc "viet" → trả về "vi"
- Mã BCP-47 hợp lệ khác (ví dụ: "fr", "ja", "zh") → trả về nguyên mã đó (chữ thường)
- Nếu không nhận ra → trả về "vi" (mặc định)

Trả về JSON duy nhất, không giải thích: {"language": "vi"}\
"""


async def _step_ask_language(text: str, chat_id: int, state: dict) -> None:
    result = await _ai_classify(_CLASSIFY_LANGUAGE_PROMPT, text)
    language = result.get("language", "vi").strip().lower() or "vi"
    state["language"] = language

    user_type = state.get("type", "boss")
    if user_type == "boss":
        state["step"] = "boss_name"
        reply = await _ai_reply(
            f"Người dùng chọn ngôn ngữ '{language}'. "
            "Xác nhận ngắn gọn và hỏi tên anh/chị."
        )
    else:
        state["step"] = "member_boss"
        label = "thành viên" if user_type == "member" else "đối tác"
        reply = await _ai_reply(
            f"Người dùng ({label}) chọn ngôn ngữ '{language}'. "
            "Xác nhận ngắn gọn và hỏi họ thuộc team của ai — "
            "cho biết tên sếp hoặc tên công ty để em tìm."
        )
    await telegram.send(chat_id, reply)


# ---- Boss path -----------------------------------------------------------

async def _step_boss_name(text: str, chat_id: int, state: dict) -> None:
    result = await _ai_classify(_EXTRACT_NAME_PROMPT, text)
    name = result.get("name", "").strip()
    if not name:
        reply = await _ai_reply(
            "Không trích xuất được tên từ tin nhắn. "
            "Hỏi lại tên anh/chị một cách tự nhiên."
        )
        await telegram.send(chat_id, reply)
        return
    state["name"] = name
    state["step"] = "boss_company"
    reply = await _ai_reply(
        f"Sếp tên là {name}. Chào bằng tên và hỏi tên công ty/tổ chức của anh/chị."
    )
    await telegram.send(chat_id, reply)


async def _step_boss_company(text: str, chat_id: int, state: dict) -> None:
    result = await _ai_classify(_EXTRACT_COMPANY_PROMPT, text)
    company = result.get("company", "").strip()
    if not company:
        reply = await _ai_reply(
            "Không trích xuất được tên công ty. Hỏi lại một cách tự nhiên."
        )
        await telegram.send(chat_id, reply)
        return
    state["company"] = company
    state["step"] = "boss_confirm"
    name = state["name"]
    reply = await _ai_reply(
        f"Sếp tên {name}, công ty {company}. "
        f"Xác nhận lại thông tin: tạo workspace cho *{name}* — *{company}*, "
        "hỏi anh/chị xác nhận để em bắt đầu tạo, hoặc cần sửa gì không."
    )
    await telegram.send(chat_id, reply)


async def _step_boss_confirm(text: str, chat_id: int, state: dict) -> None:
    result = await _ai_classify(_CLASSIFY_CONFIRM_PROMPT, text)
    confirm = result.get("confirm")

    name, company = state["name"], state["company"]

    if confirm is None:
        reply = await _ai_reply(
            f"Người dùng trả lời không liên quan đến xác nhận. "
            f"Nhắc lại: tạo workspace cho {name} - {company}, "
            "hỏi anh/chị xác nhận hoặc cần sửa gì."
        )
        await telegram.send(chat_id, reply)
        return

    if not confirm:
        state["step"] = "boss_name"
        reply = await _ai_reply(
            "Người dùng muốn sửa thông tin. "
            "Nói dạ, em bắt đầu lại nhé, và hỏi lại tên."
        )
        await telegram.send(chat_id, reply)
        return

    wait_reply = await _ai_reply(
        f"Người dùng xác nhận tạo workspace cho {name} - {company}. "
        "Nói em đang tạo workspace, vui lòng chờ vài giây."
    )
    await telegram.send(chat_id, wait_reply)

    try:
        # 1. Provision Lark workspace
        ws = await lark.provision_workspace(company)
        base_token = ws["base_token"]
        table_people = ws["table_people"]
        table_tasks = ws["table_tasks"]
        table_projects = ws["table_projects"]
        table_ideas = ws["table_ideas"]
        table_reminders = ws["table_reminders"]
        table_notes = ws["table_notes"]
        logger.info("[onboarding] Lark workspace provisioned for chat_id=%s", chat_id)

        # 2. Persist boss record
        await db.create_boss(
            chat_id, name, company,
            base_token, table_people, table_tasks, table_projects, table_ideas,
            lark_table_reminders=table_reminders,
            lark_table_notes=table_notes,
        )
        logger.info("[onboarding] boss created in DB for chat_id=%s", chat_id)

        # 2b. Persist language preference (create_boss doesn't accept language param)
        language = state.get("language", "vi")
        _db = await db.get_db()
        await _db.execute(
            "UPDATE bosses SET language = ? WHERE chat_id = ?",
            (language, chat_id),
        )
        await _db.commit()
        logger.info("[onboarding] boss language='%s' saved for chat_id=%s", language, chat_id)

        # 3. Add boss to people_map
        await db.add_person(chat_id, chat_id, "boss", name)

        # 4. Provision Qdrant collections
        await qdrant.provision_collections(chat_id)
        logger.info("[onboarding] Qdrant collections provisioned for chat_id=%s", chat_id)

        # 5. Add boss to People table on Lark
        await lark.create_record(base_token, table_people, {
            "Tên": name,
            "Chat ID": chat_id,
            "Type": "boss",
        })
        logger.info("[onboarding] boss record added to Lark People table for chat_id=%s", chat_id)

        # 6. AI generates success message
        lark_base_url = f"https://larksuite.com/base/{base_token}"
        success_reply = await _ai_reply(
            f"Workspace đã tạo xong cho {name} - {company}. "
            "Thông báo thành công, hướng dẫn nhanh vài tính năng chính: "
            "giao task bằng ngôn ngữ tự nhiên (ví dụ: giao Bách thiết kế logo deadline thứ 6), "
            "xem tóm tắt ngày (hôm nay có gì?), "
            "đặt nhắc nhở (nhắc tôi 3h chiều họp), "
            "gửi tin nhắn cho team member. "
            "Chúc anh/chị làm việc hiệu quả."
        )
        # Append Lark link separately to ensure it's always correct
        await telegram.send(
            chat_id,
            f"{success_reply}\n\nLark Base: {lark_base_url}\n"
            "(Mở link để xem dữ liệu trực tiếp trên Lark)",
        )

    except Exception:
        logger.exception("[onboarding] provision failed for chat_id=%s", chat_id)
        error_reply = await _ai_reply(
            "Có lỗi xảy ra khi tạo workspace. "
            "Xin lỗi anh/chị và đề nghị thử lại sau hoặc liên hệ hỗ trợ."
        )
        await telegram.send(chat_id, error_reply)
        return

    # 7. Remove from onboarding state
    _onboarding.pop(chat_id, None)
    logger.info("[onboarding] completed (boss) for chat_id=%s", chat_id)


# ---- Member / Partner path -----------------------------------------------

async def _step_member_boss(text: str, chat_id: int, state: dict) -> None:
    query = text.strip()
    if not query:
        reply = await _ai_reply(
            "Người dùng gửi tin rỗng. Hỏi lại tên sếp hoặc tên công ty để em tìm team."
        )
        await telegram.send(chat_id, reply)
        return

    all_bosses = await db.get_all_bosses()
    if not all_bosses:
        reply = await _ai_reply(
            "Chưa có workspace nào trong hệ thống. "
            "Giải thích sếp của bạn cần đăng ký trước, bạn quay lại sau nhé."
        )
        await telegram.send(chat_id, reply)
        return

    # If pending list from previous turn, use AI to parse selection
    pending = state.get("pending_matches")
    if pending:
        boss_list = "\n".join(
            f"{i}. {b['name']} — {b.get('company', '')}"
            for i, b in enumerate(pending)
        )
        prompt = _CLASSIFY_BOSS_SEARCH_PROMPT.format(boss_list=boss_list, user_text=query)
        result = await _ai_classify(prompt, query)
        idx = result.get("index", -1)
        if 0 <= idx < len(pending):
            chosen = pending[idx]
            state["boss"] = chosen
            state.pop("pending_matches", None)
            state["step"] = "member_name"
            reply = await _ai_reply(
                f"Người dùng chọn team {chosen['name']} — {chosen.get('company', '')}. "
                "Xác nhận và hỏi tên bạn."
            )
            await telegram.send(chat_id, reply)
            return

    # Text match in boss name / company name
    query_lower = query.lower()
    matches = [
        b for b in all_bosses
        if query_lower in b["name"].lower() or query_lower in b.get("company", "").lower()
    ]

    # AI fallback search if text match fails
    if not matches and len(all_bosses) > 0:
        boss_list = "\n".join(
            f"{i}. {b['name']} — {b.get('company', '')}"
            for i, b in enumerate(all_bosses)
        )
        prompt = _CLASSIFY_BOSS_SEARCH_PROMPT.format(boss_list=boss_list, user_text=query)
        result = await _ai_classify(prompt, query)
        idx = result.get("index", -1)
        if 0 <= idx < len(all_bosses):
            matches = [all_bosses[idx]]

    if len(matches) == 0:
        reply = await _ai_reply(
            "Không tìm thấy team nào phù hợp. "
            "Hỏi lại tên sếp hoặc tên công ty."
        )
        await telegram.send(chat_id, reply)
        return

    if len(matches) > 1:
        state["pending_matches"] = matches
        lines = "\n".join(
            f"{i + 1}. {b['name']} — {b.get('company', '')}"
            for i, b in enumerate(matches)
        )
        # AI writes intro, list is appended verbatim to ensure accuracy
        intro = await _ai_reply(
            "Tìm thấy nhiều team phù hợp. "
            "Viết một câu ngắn dẫn vào danh sách và hỏi bạn thuộc team nào."
        )
        await telegram.send(chat_id, f"{intro}\n\n{lines}")
        return

    # Exactly 1 match
    state.pop("pending_matches", None)
    boss = matches[0]
    state["boss"] = boss
    state["step"] = "member_name"
    reply = await _ai_reply(
        f"Tìm thấy team *{boss['name']}* — *{boss.get('company', '')}*. "
        "Xác nhận team và hỏi tên bạn là gì."
    )
    await telegram.send(chat_id, reply)


async def _step_member_name(text: str, chat_id: int, state: dict) -> None:
    result = await _ai_classify(_EXTRACT_NAME_PROMPT, text)
    name = result.get("name", "").strip()
    if not name:
        reply = await _ai_reply(
            "Không trích xuất được tên. Hỏi lại tên bạn."
        )
        await telegram.send(chat_id, reply)
        return

    boss = state["boss"]
    person_type = state["type"]

    try:
        # Add to people_map
        await db.add_person(chat_id, boss["chat_id"], person_type, name)
        logger.info(
            "[onboarding] %s %s (chat_id=%s) joined boss chat_id=%s",
            person_type, name, chat_id, boss["chat_id"],
        )

        # Persist language preference to memberships
        language = state.get("language", "vi")
        _db = await db.get_db()
        await _db.execute(
            "UPDATE memberships SET language = ? WHERE chat_id = ? AND boss_chat_id = ?",
            (language, str(chat_id), str(boss["chat_id"])),
        )
        await _db.commit()
        logger.info(
            "[onboarding] member language='%s' saved for chat_id=%s", language, chat_id
        )

        # Add to Lark People table
        await lark.create_record(
            boss["lark_base_token"],
            boss["lark_table_people"],
            {"Tên": name, "Chat ID": chat_id, "Type": person_type},
        )
        logger.info("[onboarding] Lark People record created for chat_id=%s", chat_id)

        type_label = "thành viên" if person_type == "member" else "đối tác"
        company = boss.get("company") or boss["name"]
        reply = await _ai_reply(
            f"Bạn tên {name} đã tham gia team *{company}* với vai trò {type_label}. "
            "Chào mừng và nói từ giờ bạn nhắn tin để em hỗ trợ nhé."
        )
        await telegram.send(chat_id, reply)

    except Exception:
        logger.exception("[onboarding] failed to add %s chat_id=%s to boss chat_id=%s",
                         person_type, chat_id, boss["chat_id"])
        error_reply = await _ai_reply(
            "Có lỗi khi tham gia team. Xin lỗi bạn và đề nghị thử lại sau."
        )
        await telegram.send(chat_id, error_reply)
        return

    _onboarding.pop(chat_id, None)
    logger.info("[onboarding] completed (%s) for chat_id=%s", person_type, chat_id)


# ---------------------------------------------------------------------------
# Join flow (discover companies and request to join)
# ---------------------------------------------------------------------------

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

    # Add to Lark People table
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
