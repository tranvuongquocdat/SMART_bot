"""Onboarding state machine for new users.

Three paths:
  boss    — create a new workspace
  member  — join an existing team as member
  partner — join an existing team as partner
"""

import logging

from src import db
from src.services import lark, qdrant
from src.services import telegram

logger = logging.getLogger("onboarding")

# in-memory state: {chat_id: {"step": str, ...}}
_onboarding: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_onboarding(chat_id: int) -> bool:
    """Return True if chat_id is currently in the onboarding flow."""
    return chat_id in _onboarding


def start_onboarding(chat_id: int) -> None:
    """Begin onboarding for a new user."""
    _onboarding[chat_id] = {"step": "ask_type"}
    logger.info("[onboarding] started for chat_id=%s", chat_id)


async def handle_onboard_message(text: str, chat_id: int) -> None:
    """Route message to the correct handler based on current step."""
    state = _onboarding.get(chat_id)
    if state is None:
        return

    step = state["step"]

    if step == "ask_type":
        await _step_ask_type(text, chat_id, state)
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

_BOSS_KEYWORDS = {"1", "sếp", "quản lý", "giám đốc"}
_MEMBER_KEYWORDS = {"2", "thành viên", "member", "nhân viên"}
_PARTNER_KEYWORDS = {"3", "đối tác", "partner"}

_WELCOME = (
    "Chào mừng! Bạn là:\n"
    "1. Sếp / Giám đốc — tạo workspace mới\n"
    "2. Thành viên / Nhân viên — tham gia team\n"
    "3. Đối tác / Partner — tham gia team\n\n"
    "Trả lời 1, 2 hoặc 3 nhé!"
)


async def _send_welcome(chat_id: int) -> None:
    await telegram.send(chat_id, _WELCOME)


async def _step_ask_type(text: str, chat_id: int, state: dict) -> None:
    normalized = text.strip().lower()

    if normalized in _BOSS_KEYWORDS:
        state["step"] = "boss_name"
        state["type"] = "boss"
        await telegram.send(chat_id, "Tên anh/chị là gì ạ?")

    elif normalized in _MEMBER_KEYWORDS:
        state["step"] = "member_boss"
        state["type"] = "member"
        await telegram.send(chat_id, "Thuộc team của ai? Nhập tên sếp hoặc tên công ty nhé!")

    elif normalized in _PARTNER_KEYWORDS:
        state["step"] = "member_boss"
        state["type"] = "partner"
        await telegram.send(chat_id, "Thuộc team của ai? Nhập tên sếp hoặc tên công ty nhé!")

    else:
        await telegram.send(chat_id, "Trả lời 1, 2 hoặc 3 nhé!")


# ---- Boss path -----------------------------------------------------------

async def _step_boss_name(text: str, chat_id: int, state: dict) -> None:
    name = text.strip()
    if not name:
        await telegram.send(chat_id, "Tên anh/chị là gì ạ?")
        return
    state["name"] = name
    state["step"] = "boss_company"
    await telegram.send(chat_id, "Công ty/tổ chức tên gì ạ?")


async def _step_boss_company(text: str, chat_id: int, state: dict) -> None:
    company = text.strip()
    if not company:
        await telegram.send(chat_id, "Công ty/tổ chức tên gì ạ?")
        return
    state["company"] = company
    state["step"] = "boss_confirm"
    name = state["name"]
    await telegram.send(
        chat_id,
        f"Tạo workspace cho *{name}* - *{company}* nhé? Trả lời OK",
    )


async def _step_boss_confirm(text: str, chat_id: int, state: dict) -> None:
    if text.strip().upper() != "OK":
        await telegram.send(
            chat_id,
            f"Tạo workspace cho *{state['name']}* - *{state['company']}* nhé? Trả lời OK",
        )
        return

    name = state["name"]
    company = state["company"]
    await telegram.send(chat_id, "Đang tạo workspace, vui lòng chờ vài giây...")

    try:
        # 1. Provision Lark workspace
        ws = await lark.provision_workspace(company)
        base_token = ws["base_token"]
        table_people = ws["table_people"]
        table_tasks = ws["table_tasks"]
        table_projects = ws["table_projects"]
        table_ideas = ws["table_ideas"]
        logger.info("[onboarding] Lark workspace provisioned for chat_id=%s", chat_id)

        # 2. Persist boss record
        await db.create_boss(
            chat_id, name, company,
            base_token, table_people, table_tasks, table_projects, table_ideas,
        )
        logger.info("[onboarding] boss created in DB for chat_id=%s", chat_id)

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

        # 6. Send success message
        await telegram.send(
            chat_id,
            (
                f"Workspace đã tạo xong cho *{name}* - *{company}*!\n\n"
                "Hướng dẫn nhanh:\n"
                "- Nhắn tin bình thường để tôi ghi nhận và trả lời\n"
                "- `/task [nội dung]` — tạo task mới\n"
                "- `/summary` — tóm tắt công việc\n"
                "- `/remind [thời gian] [nội dung]` — đặt nhắc nhở\n\n"
                "Chúc anh/chị làm việc hiệu quả!"
            ),
        )

    except Exception:
        logger.exception("[onboarding] provision failed for chat_id=%s", chat_id)
        await telegram.send(
            chat_id,
            "Có lỗi xảy ra khi tạo workspace. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.",
        )
        return

    # 7. Remove from onboarding state
    _onboarding.pop(chat_id, None)
    logger.info("[onboarding] completed (boss) for chat_id=%s", chat_id)


# ---- Member / Partner path -----------------------------------------------

async def _step_member_boss(text: str, chat_id: int, state: dict) -> None:
    query = text.strip().lower()
    if not query:
        await telegram.send(chat_id, "Thuộc team của ai? Nhập tên sếp hoặc tên công ty nhé!")
        return

    all_bosses = await db.get_all_bosses()
    matches = [
        b for b in all_bosses
        if query in b["name"].lower() or query in b.get("company", "").lower()
    ]

    if len(matches) == 0:
        await telegram.send(chat_id, "Không tìm thấy, thử lại?")
        return

    if len(matches) > 1:
        lines = "\n".join(
            f"{i + 1}. {b['name']} — {b.get('company', '')}"
            for i, b in enumerate(matches)
        )
        await telegram.send(
            chat_id,
            f"Tìm thấy nhiều kết quả:\n{lines}\n\nBạn thuộc team nào? Nhập cụ thể hơn nhé!",
        )
        return

    # Exactly 1 match
    boss = matches[0]
    state["boss"] = boss
    state["step"] = "member_name"
    await telegram.send(chat_id, "Tên bạn là gì?")


async def _step_member_name(text: str, chat_id: int, state: dict) -> None:
    name = text.strip()
    if not name:
        await telegram.send(chat_id, "Tên bạn là gì?")
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

        # Add to Lark People table
        await lark.create_record(
            boss["lark_base_token"],
            boss["lark_table_people"],
            {"Tên": name, "Chat ID": chat_id, "Type": person_type},
        )
        logger.info("[onboarding] Lark People record created for chat_id=%s", chat_id)

        type_label = "thành viên" if person_type == "member" else "đối tác"
        await telegram.send(
            chat_id,
            (
                f"Chào *{name}*! Bạn đã tham gia team *{boss.get('company') or boss['name']}* "
                f"với vai trò {type_label}.\n\n"
                "Từ giờ hãy nhắn tin để tôi hỗ trợ bạn nhé!"
            ),
        )

    except Exception:
        logger.exception("[onboarding] failed to add %s chat_id=%s to boss chat_id=%s",
                         person_type, chat_id, boss["chat_id"])
        await telegram.send(
            chat_id,
            "Có lỗi xảy ra khi tham gia team. Vui lòng thử lại sau.",
        )
        return

    _onboarding.pop(chat_id, None)
    logger.info("[onboarding] completed (%s) for chat_id=%s", person_type, chat_id)
