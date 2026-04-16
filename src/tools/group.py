"""
group.py — Group-specific tools for the AI Secretary.
"""
import logging

from src import db
from src.context import ChatContext
from src.services import openai_client, telegram

logger = logging.getLogger("tools.group")


async def summarize_group_conversation(ctx: ChatContext, n_messages: int = 20) -> str:
    """
    Reads last N messages from the group and returns an LLM summary:
    main topic, decisions made, action items not yet assigned.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    _db = await db.get_db()
    async with _db.execute(
        "SELECT role, content, sender_id FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (ctx.chat_id, n_messages),
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        return "Không có tin nhắn nào trong nhóm để tóm tắt."

    messages_text = "\n".join(
        f"{r['role']}: {r['content']}"
        for r in reversed(rows)
    )

    response, _ = await openai_client.chat_with_tools(
        [
            {
                "role": "system",
                "content": (
                    "Tóm tắt cuộc trò chuyện nhóm này theo 3 phần:\n"
                    "1. Chủ đề chính đang bàn\n"
                    "2. Các quyết định đã đưa ra\n"
                    "3. Các việc cần làm chưa được giao task (action items)\n"
                    "Ngắn gọn, rõ ràng."
                ),
            },
            {"role": "user", "content": messages_text},
        ],
        [],
    )
    return (response.content or "Không thể tóm tắt.").strip()


async def update_group_note(ctx: ChatContext, content: str, append: bool = True) -> str:
    """
    Write or append to the group note. Used to record decisions, rules,
    recurring context about this group.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    existing = await db.get_note(ctx.boss_chat_id, "group", str(ctx.chat_id))
    if append and existing and existing.get("content"):
        new_content = existing["content"] + "\n\n" + content
    else:
        new_content = content

    await db.update_note(ctx.boss_chat_id, "group", str(ctx.chat_id), new_content)
    return "Đã cập nhật ghi chú nhóm."


async def broadcast_to_group(ctx: ChatContext, message: str) -> str:
    """
    Send a message to the group chat. Used for team announcements,
    deadline broadcasts, approval results.
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."
    await telegram.send(ctx.chat_id, message)
    return "Đã gửi thông báo vào nhóm."


async def manage_group(ctx: ChatContext, action: str, **kwargs) -> str:
    """
    Telegram group management actions. Requires bot to be admin.

    action values:
      invite           name (str) — add member or generate invite link
      rename           title (str) — rename the group
      pin              message_id (int, optional) — pin a message
      unpin            — unpin all messages
      kick             name (str) — remove member from group
      set_description  text (str)
      invite_link      — generate a single-use 24h invite link
    """
    if not ctx.is_group:
        return "This tool is only available in group chats."

    # Check bot is admin
    bot_id = await telegram.get_bot_id()
    if bot_id:
        member_info = await telegram.get_chat_member(ctx.chat_id, bot_id)
        if member_info.get("status") not in ("administrator", "creator"):
            return (
                "Em cần quyền admin để thực hiện việc này. "
                "Nhờ admin vào Settings → Administrators → Add Administrator → chọn @bot nhé."
            )

    if action == "invite":
        return await _invite_member(ctx, kwargs.get("name", ""))

    elif action == "rename":
        title = kwargs.get("title", "")
        ok = await telegram.set_chat_title(ctx.chat_id, title)
        return f"Đã đổi tên nhóm thành '{title}'." if ok else "Không thể đổi tên nhóm."

    elif action == "pin":
        message_id = kwargs.get("message_id")
        if not message_id:
            return "Cần cung cấp message_id để pin."
        ok = await telegram.pin_chat_message(ctx.chat_id, int(message_id))
        return "Đã pin tin nhắn." if ok else "Không thể pin tin nhắn."

    elif action == "unpin":
        ok = await telegram.unpin_all_chat_messages(ctx.chat_id)
        return "Đã bỏ pin tất cả tin nhắn." if ok else "Không thể bỏ pin."

    elif action == "kick":
        return await _kick_member(ctx, kwargs.get("name", ""))

    elif action == "set_description":
        text = kwargs.get("text", "")
        ok = await telegram.set_chat_description(ctx.chat_id, text)
        return "Đã cập nhật mô tả nhóm." if ok else "Không thể cập nhật mô tả."

    elif action == "invite_link":
        link = await telegram.create_invite_link(ctx.chat_id, member_limit=1, expire_hours=24)
        return f"Link mời (dùng 1 lần, hết hạn 24h): {link}" if link else "Không thể tạo link mời."

    return f"Hành động '{action}' không được nhận ra."


async def _invite_member(ctx: ChatContext, name: str) -> str:
    """Try direct add first; fallback to invite link."""
    from src.services import lark as _lark

    # Search People table for chat_id
    records = await _lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    person = next(
        (r for r in records if name.lower() in r.get("Tên", "").lower()),
        None,
    )

    if person and person.get("Chat ID"):
        try:
            ok = await telegram.add_chat_member(ctx.chat_id, int(person["Chat ID"]))
            if ok:
                return f"Đã mời {person['Tên']} vào nhóm."
        except Exception:
            pass  # person hasn't DM'd bot or API error

    # Fallback: generate single-use invite link
    link = await telegram.create_invite_link(ctx.chat_id, member_limit=1, expire_hours=24)
    person_name = person["Tên"] if person else name
    if link:
        return (
            f"{person_name} chưa nhắn bot lần nào. "
            f"Đây là link mời (dùng 1 lần, hết hạn 24h): {link}"
        )
    return f"Không tìm thấy {name} hoặc không thể tạo link mời."


async def _kick_member(ctx: ChatContext, name: str) -> str:
    """Find member in People table and kick from group (ban + immediate unban)."""
    from src.services import lark as _lark

    records = await _lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    person = next(
        (r for r in records if name.lower() in r.get("Tên", "").lower()),
        None,
    )
    if not person or not person.get("Chat ID"):
        return f"Không tìm thấy {name} trong danh sách nhân sự."

    user_id = int(person["Chat ID"])
    await telegram.ban_chat_member(ctx.chat_id, user_id)
    await telegram.unban_chat_member(ctx.chat_id, user_id)  # ban + unban = kick without permanent ban
    return f"Đã xóa {person['Tên']} khỏi nhóm."
