"""
Reminder creation tool. Takes ChatContext as first argument.
"""
from datetime import datetime

from src import db
from src.context import ChatContext


async def create_reminder(ctx: ChatContext, content: str, remind_at: str) -> str:
    try:
        remind_dt = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"Định dạng thời gian không hợp lệ: '{remind_at}'. Vui lòng dùng YYYY-MM-DD HH:MM."

    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=content,
        remind_at=remind_dt,
    )
    return f"Đã tạo nhắc nhở #{reminder_id}: '{content}' lúc {remind_at}."
