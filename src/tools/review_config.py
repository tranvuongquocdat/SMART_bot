"""Review schedule config tools."""
import re

from src import db as db_mod
from src.context import ChatContext

_CONTENT_LABELS = {
    "morning_brief": "Briefing sáng",
    "evening_summary": "Tổng kết chiều",
    "custom": "Tuỳ chỉnh",
}


def _valid_time(t: str) -> bool:
    return bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t))


async def add_review_schedule(
    ctx: ChatContext,
    cron_time: str,
    content_type: str = "morning_brief",
    custom_prompt: str = "",
) -> str:
    if not _valid_time(cron_time):
        return f"Định dạng giờ không hợp lệ: '{cron_time}'. Dùng HH:MM (VD: 08:00)."
    if content_type not in _CONTENT_LABELS:
        return f"content_type phải là: {', '.join(_CONTENT_LABELS)}."
    if content_type == "custom" and not custom_prompt.strip():
        return "Với loại 'custom', cần truyền nội dung custom_prompt."

    review_id = await db_mod.create_scheduled_review(
        db_mod._db, str(ctx.boss_chat_id), cron_time, content_type,
        custom_prompt.strip() or None,
    )
    label = _CONTENT_LABELS[content_type]
    return f"Đã thêm lịch review #{review_id}: {label} lúc {cron_time}."


async def list_review_schedules(ctx: ChatContext) -> str:
    reviews = await db_mod.list_scheduled_reviews(db_mod._db, str(ctx.boss_chat_id))
    if not reviews:
        return "Chưa có lịch review nào được cấu hình."
    lines = ["Lịch review hiện tại:"]
    for r in reviews:
        flag = "✅" if r["enabled"] else "⏸"
        label = _CONTENT_LABELS.get(r["content_type"], r["content_type"])
        extra = f" — {r['custom_prompt'][:50]}" if r.get("custom_prompt") else ""
        lines.append(f"{flag} #{r['id']} | {r['cron_time']} | {label}{extra}")
    return "\n".join(lines)


async def toggle_review(ctx: ChatContext, review_id: int, enabled: bool) -> str:
    ok = await db_mod.update_scheduled_review(
        db_mod._db, review_id, owner_id=str(ctx.boss_chat_id),
        enabled=1 if enabled else 0,
    )
    if not ok:
        return f"Không tìm thấy lịch review #{review_id}."
    return f"Đã {'bật' if enabled else 'tắt'} lịch review #{review_id}."


async def delete_review_schedule(ctx: ChatContext, review_id: int) -> str:
    ok = await db_mod.delete_scheduled_review(
        db_mod._db, review_id, owner_id=str(ctx.boss_chat_id),
    )
    if not ok:
        return f"Không tìm thấy lịch review #{review_id}."
    return f"Đã xoá lịch review #{review_id}."
