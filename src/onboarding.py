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
from src.infrastructure import qdrant_client as qdrant
from src.infrastructure import lark_client as lark
from src.agent.llm_for_ctx import get_default_llm
from src.agent.onboarding_agent import (
    PERSONA as _PERSONA,
    COLLECTOR_PROMPT as _COLLECTOR_PROMPT,  # noqa: F401  (kept for backward compat)
    collector as _collector,
    greeting as _greeting,
    ai_classify as _ai_classify,
)
from src.channels import telegram_singleton as telegram
from src.channels import telegram_singleton as tg

logger = logging.getLogger("onboarding")


async def _send_and_save(chat_id: str, text: str) -> None:
    """Send reply to DM. telegram.send auto-persists as assistant message so next turn has history."""
    await telegram.send(chat_id, text)

# join flow state: {chat_id: {"step": str, ...}} — short-lived, in-memory is fine
_join_sessions: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------






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

async def _complete_boss(chat_id: str, state: dict) -> None:
    """Provision Lark workspace and persist boss record. Called after confirmation."""
    name = state["name"]
    company = state["company"]
    language = state.get("language", "vi")
    email = (state.get("email") or "").strip()  # optional, reserved for future private-share

    messages = [
        {"role": "system", "content": _PERSONA},
        {"role": "user", "content": (
            f"Người dùng xác nhận tạo workspace cho {name} - {company}. "
            "Nói đang tạo, chờ vài giây."
        )},
    ]
    resp, _ = await get_default_llm().chat_with_tools(messages, [])
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
            email=email,
        )
        logger.info("[onboarding] boss created in DB for chat_id=%s", chat_id)

        public_ok = False
        try:
            await lark.make_base_public(base_token, link_share_entity="anyone_editable")
            public_ok = True
            logger.info("[onboarding] Lark base made public (anyone_editable) for chat_id=%s", chat_id)
        except Exception:
            logger.exception(
                "[onboarding] failed to make Lark base public for chat_id=%s", chat_id,
            )

        _db = await db.get_db()
        await _db.execute(
            "UPDATE bosses SET language = ? WHERE chat_id = ?",
            (language, chat_id),
        )
        await _db.commit()
        logger.info("[onboarding] boss language='%s' saved for chat_id=%s", language, chat_id)

        # Membership-of-self: must be keyed by the person UUID (sender_id),
        # not the workspace UUID (chat_id). Phase 1 had sender_id == chat_id
        # so add_person(chat_id, chat_id, ...) worked by coincidence; after
        # the Phase 2 ID split, that creates a workspace→workspace row that
        # context.resolve() can never find via get_memberships(sender_id).
        person_id = str(state.get("sender_id") or chat_id)
        from src.services import membership_service
        await membership_service.activate(
            chat_id=person_id,
            boss_chat_id=chat_id,
            person_type="boss",
            name=name,
            source="self_boss",
        )
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
        resp2, _ = await get_default_llm().chat_with_tools(messages2, [])
        success_reply = (resp2.content or "").strip()

        if public_ok:
            access_hint = "Bấm link để mở Base — không cần đăng nhập, xem và chỉnh sửa trực tiếp."
        else:
            access_hint = (
                "Em chưa mở được chế độ chia sẻ công khai. Anh/chị thử mở link; "
                "nếu không vào được, liên hệ admin hệ thống để được cấp quyền."
            )
        await telegram.send(
            chat_id,
            f"{success_reply}\n\nLark Base: {lark_base_url}\n{access_hint}",
        )

    except Exception:
        logger.exception("[onboarding] provision failed for chat_id=%s", chat_id)
        messages3 = [
            {"role": "system", "content": _PERSONA},
            {"role": "user", "content": "Có lỗi khi tạo workspace. Xin lỗi và đề nghị thử lại sau."},
        ]
        resp3, _ = await get_default_llm().chat_with_tools(messages3, [])
        await telegram.send(chat_id, (resp3.content or "Có lỗi. Vui lòng thử lại.").strip())
        return

    await db.clear_onboarding_state(chat_id)
    logger.info("[onboarding] completed (boss) for chat_id=%s", chat_id)


async def _complete_member(chat_id: str, state: dict) -> None:
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
        # See _complete_boss for why we key the membership by sender_id, not chat_id.
        person_id = str(state.get("sender_id") or chat_id)
        await db.upsert_membership(
            _db,
            chat_id=person_id,
            boss_chat_id=str(boss["chat_id"]),
            person_type=person_type,
            name=name,
            status="pending",
            request_info=f"Đăng ký qua onboarding. Ngôn ngữ: {language}",
        )
        await _db.execute(
            "UPDATE memberships SET language = ? WHERE chat_id = ? AND boss_chat_id = ?",
            (language, person_id, str(boss["chat_id"])),
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
        resp, _ = await get_default_llm().chat_with_tools(messages, [])
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

async def is_onboarding(chat_id: str) -> bool:
    """Return True if chat_id is currently in the onboarding flow."""
    return await db.has_onboarding_state(chat_id)


async def start_onboarding(chat_id: str, sender_id: str | None = None) -> None:
    """Begin onboarding for a new user."""
    state: dict = {"first": True}
    if sender_id:
        state["sender_id"] = str(sender_id)
    await db.save_onboarding_state(chat_id, state)
    logger.info("[onboarding] started for chat_id=%s sender_id=%s", chat_id, sender_id)


async def handle_onboard_message(text: str, chat_id: str, sender_id: str | None = None) -> None:
    """Route onboarding message through the LLM collector."""
    state = await db.get_onboarding_state(chat_id) or {}
    if sender_id and not state.get("sender_id"):
        state["sender_id"] = str(sender_id)
    is_first = state.pop("first", False)

    if is_first:
        await db.save_onboarding_state(chat_id, state)
        greeting = await _greeting()
        await _send_and_save(chat_id, greeting)
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
            await _send_and_save(chat_id, reply)
            await _complete_boss(chat_id, state)
            return
        elif confirmed is False:
            # User wants to restart — clear collected fields
            await db.save_onboarding_state(chat_id, {
                "type": None, "name": None, "company": None,
                "language": None, "confirmed": None,
            })
            await _send_and_save(chat_id, reply)
            return
        # confirmed is None — reply already contains confirmation prompt

    # Member/partner path completion
    if user_type in ("member", "partner") and _member_fields_complete(state):
        await _send_and_save(chat_id, reply)
        await _complete_member(chat_id, state)
        return

    await db.save_onboarding_state(chat_id, state)
    await _send_and_save(chat_id, reply)


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




async def handle_join_inquiry(chat_id: str) -> str:
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


def is_join_session(chat_id: str) -> bool:
    return chat_id in _join_sessions


async def handle_join_message(text: str, chat_id: str) -> str:
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
