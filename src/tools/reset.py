"""
Reset workspace: 2-step safety flow (boss only).
  Step 1 — bot asks boss to retype company name in UPPERCASE
  Step 2 — bot asks boss to type "tôi chắc chắn"
  Step 3 — delete all Lark records (People, Tasks, Projects, Ideas, Reminders, Notes)
           SQLite data is NOT touched.
"""
import asyncio
import logging
from typing import Optional

from src import db
from src.context import ChatContext
from src.services import lark

logger = logging.getLogger("reset")

# In-memory session: {boss_chat_id: {"step": 1|2, "company": str}}
_reset_sessions: dict[int, dict] = {}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def is_reset_session(boss_chat_id: int) -> bool:
    return boss_chat_id in _reset_sessions


def _clear(boss_chat_id: int):
    _reset_sessions.pop(boss_chat_id, None)


# ---------------------------------------------------------------------------
# Entry point — called from agent when boss sends trigger phrase
# ---------------------------------------------------------------------------

TRIGGER_PHRASES = ["reset workspace", "/reset", "xóa toàn bộ dữ liệu workspace"]


def is_reset_trigger(text: str) -> bool:
    lower = text.lower().strip()
    return any(p in lower for p in TRIGGER_PHRASES)


async def start_reset(ctx: ChatContext) -> str:
    """Begin reset flow — ask boss to confirm by typing company name in UPPERCASE."""
    boss = await db.get_boss(ctx.boss_chat_id)
    company = boss.get("company", "") if boss else ""
    if not company:
        company = str(ctx.boss_chat_id)

    _reset_sessions[ctx.boss_chat_id] = {"step": 1, "company": company}
    upper = company.upper()
    return (
        f"⚠️ Bạn đang yêu cầu XÓA TOÀN BỘ dữ liệu Lark của workspace *{company}*.\n\n"
        f"Thao tác này sẽ xóa tất cả dữ liệu trong các bảng People, Tasks, Projects, Ideas, "
        f"Reminders, Notes trên Lark Base. Dữ liệu SQLite sẽ được giữ nguyên.\n\n"
        f"Để xác nhận, hãy gõ chính xác tên công ty bằng CHỮ HOA:\n"
        f"`{upper}`"
    )


async def handle_reset_message(text: str, ctx: ChatContext) -> Optional[str]:
    """
    Process reset confirmation steps.
    Returns reply string if handled, None if message doesn't match.
    """
    session = _reset_sessions.get(ctx.boss_chat_id)
    if not session:
        return None

    if session["step"] == 1:
        expected = session["company"].upper()
        if text.strip() == expected:
            session["step"] = 2
            return (
                f"Xác nhận lần cuối: gõ đúng cụm từ sau để tiến hành xóa:\n"
                f"`tôi chắc chắn`"
            )
        else:
            _clear(ctx.boss_chat_id)
            return "Tên không khớp. Đã huỷ thao tác reset."

    if session["step"] == 2:
        if text.strip().lower() == "tôi chắc chắn":
            _clear(ctx.boss_chat_id)
            return await _execute_reset(ctx)
        else:
            _clear(ctx.boss_chat_id)
            return "Xác nhận không đúng. Đã huỷ thao tác reset."

    _clear(ctx.boss_chat_id)
    return None


# ---------------------------------------------------------------------------
# Actual reset logic
# ---------------------------------------------------------------------------

async def _delete_all_records(base_token: str, table_id: str) -> int:
    """Delete all records in a Lark table. Returns count deleted."""
    if not table_id:
        return 0
    try:
        records = await lark.search_records(base_token, table_id)
        tasks = [lark.delete_record(base_token, table_id, r["record_id"]) for r in records]
        await asyncio.gather(*tasks, return_exceptions=True)
        return len(records)
    except Exception:
        logger.exception("Failed to delete records from table %s", table_id)
        return 0


async def _execute_reset(ctx: ChatContext) -> str:
    """Delete all Lark records across all workspace tables."""
    boss = await db.get_boss(ctx.boss_chat_id)
    if not boss:
        return "Không tìm thấy thông tin workspace."

    base_token = boss.get("lark_base_token", "")
    if not base_token:
        return "Workspace chưa được kết nối Lark Base."

    table_ids = {
        "People": boss.get("lark_table_people", ""),
        "Tasks": boss.get("lark_table_tasks", ""),
        "Projects": boss.get("lark_table_projects", ""),
        "Ideas": boss.get("lark_table_ideas", ""),
        "Reminders": boss.get("lark_table_reminders", ""),
        "Notes": boss.get("lark_table_notes", ""),
    }

    results = await asyncio.gather(
        *(_delete_all_records(base_token, tid) for tid in table_ids.values()),
        return_exceptions=True,
    )

    lines = ["Reset hoàn tất. Kết quả:"]
    for (name, _), result in zip(table_ids.items(), results):
        count = result if isinstance(result, int) else 0
        lines.append(f"  • {name}: đã xóa {count} bản ghi")

    logger.info(
        "[reset] Workspace %s (%s) reset by boss %d",
        boss.get("company"), base_token, ctx.boss_chat_id
    )
    return "\n".join(lines)
