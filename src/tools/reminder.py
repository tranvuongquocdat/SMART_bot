"""
Reminder creation tool. Takes ChatContext as first argument.
"""
from datetime import datetime

from src import db
from src.context import ChatContext
from src.services import lark


async def create_reminder(ctx: ChatContext, content: str, remind_at: str, target: str = "") -> str:
    try:
        remind_dt = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"Dinh dang thoi gian khong hop le: '{remind_at}'. Vui long dung YYYY-MM-DD HH:MM."

    target_chat_id = None
    target_name = ""

    if target:
        # Tra People table de tim chat_id cua nguoi can nhac
        all_people = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
        search_lower = target.lower()
        matches = [
            p for p in all_people
            if search_lower in str(p.get("Tên", "")).lower()
            or search_lower in str(p.get("Tên gọi", "")).lower()
        ]
        if matches:
            person = matches[0]
            target_name = person.get("Tên", target)
            chat_id_val = person.get("Chat ID")
            if chat_id_val:
                try:
                    target_chat_id = int(chat_id_val)
                except (ValueError, TypeError):
                    pass

    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=content,
        remind_at=remind_dt,
        target_chat_id=target_chat_id,
        target_name=target_name,
    )

    if target_name:
        return f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
    return f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."
