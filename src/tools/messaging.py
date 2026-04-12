"""
Messaging tool — send Telegram message to a person by name lookup.
"""
from src.context import ChatContext
from src.services import lark, telegram


async def send_message(ctx: ChatContext, to: str, content: str) -> str:
    # Search People table for the recipient
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search_lower = to.lower()
    matches = [
        r for r in all_records
        if search_lower in str(r.get("Tên", "")).lower()
        or search_lower in str(r.get("Tên gọi", "")).lower()
    ]

    if not matches:
        return f"Không tìm thấy người tên '{to}' trong danh sách."

    recipient = matches[0]
    chat_id_val = recipient.get("Chat ID")
    if not chat_id_val:
        return f"Người '{to}' chưa có Chat ID trong hệ thống."

    try:
        recipient_chat_id = int(chat_id_val)
    except (ValueError, TypeError):
        return f"Chat ID của '{to}' không hợp lệ: {chat_id_val}"

    text = f"Tin nhắn từ {ctx.boss_name}:\n\n{content}"
    await telegram.send(recipient_chat_id, text)

    return f"Đã gửi tin nhắn đến {recipient.get('Tên', to)}."
