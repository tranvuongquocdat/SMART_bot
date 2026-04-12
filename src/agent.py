"""
Secretary Agent — multi-user routing, thinking UX, tool loop.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src import context, db
from src.config import Settings
from src.context import ChatContext
from src.services import lark, openai_client, qdrant, telegram
from src.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("agent")

_settings: Settings | None = None

MAX_TOOL_ROUNDS = 10

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

SECRETARY_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}. Giao tiếp tiếng Việt, thân thiện, ngắn gọn, chuyên nghiệp.

## Personal Note:
{personal_note}

## Thời gian: {current_time}

## Nhân sự:
{people_summary}

## Đang nói chuyện với:
Chat: {chat_type}
Người: {sender_name} ({sender_type})
{context_note}

## Quy tắc phân quyền:
- Nếu đang nói với SẾP ({boss_name}):
  → Toàn quyền. Xưng hô theo personal note.
  → Khi giao task → check_effort trước → cảnh báo nếu xung đột → gợi ý giải pháp.
  → Khi sếp hỏi chiến lược / sắp xếp tổng thể → gọi escalate_to_advisor.
  → Mọi thao tác xóa → confirm trước.
  → Khi sếp bảo nhắn ai → gọi send_message.

- Nếu đang nói với MEMBER/PARTNER:
  → Xưng "em là trợ lý của {boss_name}".
  → Chỉ cho xem/cập nhật task của họ.
  → Được sửa: status, nội dung, tên task, đẩy lại assignee.
  → Khi đẩy lại assignee → ghi nhận, báo sếp qua send_message.
  → KHÔNG cho xem task người khác, giao task, xem tổng quan.
  → Không tự quyết thay sếp. "Em ghi nhận, báo lại {boss_name} nhé."

- Trong GROUP: chỉ phản hồi khi được tag. Quyền tùy người tag.

## Hướng dẫn:
- Trả lời ngắn gọn, đi thẳng vấn đề.
- Gọi nhiều tool liên tiếp nếu cần.
- Biết thêm thông tin → update_note.
- Cần context cũ → search_history.
- Nhận diện người bằng tên + context nhân sự. Không chắc → hỏi lại.
"""

# ---------------------------------------------------------------------------
# Thinking UX map
# ---------------------------------------------------------------------------

THINKING_MAP = {
    "create_task": "Đang tạo task...",
    "list_tasks": "Đang xem danh sách task...",
    "update_task": "Đang cập nhật task...",
    "delete_task": "Đang xóa task...",
    "search_tasks": "Đang tìm task...",
    "add_people": "Đang thêm người...",
    "get_people": "Đang tra thông tin...",
    "list_people": "Đang xem danh sách...",
    "check_effort": "Đang kiểm tra lịch...",
    "search_history": "Đang tra lịch sử...",
    "get_summary": "Đang tổng hợp...",
    "get_workload": "Đang xem workload...",
    "web_search": "Đang tìm kiếm web...",
    "send_message": "Đang gửi tin nhắn...",
    "escalate_to_advisor": "Đang phân tích chiến lược...",
}


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_agent(settings: Settings):
    global _settings
    _settings = settings


# ---------------------------------------------------------------------------
# People summary helper
# ---------------------------------------------------------------------------

async def _build_people_summary(ctx: ChatContext) -> str:
    """Query Lark People table → return concise list per person."""
    try:
        records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
        if not records:
            return "(Chưa có nhân sự)"
        lines = []
        for r in records:
            name = r.get("Tên", "")
            nickname = r.get("Tên gọi", "")
            ptype = r.get("Type", "")
            group = r.get("Nhóm", "")
            role = r.get("Vai trò", "")
            display_name = f"{name} ({nickname})" if nickname else name
            parts = [f"- {display_name}"]
            if ptype:
                parts.append(ptype)
            if group:
                parts.append(group)
            if role:
                parts.append(role)
            lines.append(" | ".join(parts))
        return "\n".join(lines)
    except Exception:
        logger.exception("Failed to build people summary")
        return "(Không thể tải danh sách nhân sự)"


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_message(
    text: str,
    chat_id: int,
    sender_id: int,
    is_group: bool,
    bot_mentioned: bool,
):
    start_time = time.time()
    log_prefix = f"[chat:{chat_id} sender:{sender_id}]"

    logger.info("%s >>> INPUT: %s", log_prefix, text[:200])

    try:
        # ------------------------------------------------------------------
        # Step 1: Group + not mentioned → only persist, no reply
        # ------------------------------------------------------------------
        if is_group and not bot_mentioned:
            msg_id = await db.save_message(chat_id, "user", text, sender_id)
            vector = await openai_client.embed(text)
            asyncio.create_task(
                qdrant.upsert(
                    collection=f"messages_{chat_id}",
                    point_id=msg_id,
                    chat_id=chat_id,
                    role="user",
                    text=text,
                    vector=vector,
                )
            )
            logger.info("%s Group message saved (not mentioned, no reply)", log_prefix)
            return

        # ------------------------------------------------------------------
        # Step 2: Resolve context
        # ------------------------------------------------------------------
        ctx = await context.resolve(chat_id, sender_id, is_group)
        if ctx is None:
            # Unknown user — trigger onboarding state machine
            from src import onboarding  # noqa: PLC0415
            if not onboarding.is_onboarding(chat_id):
                onboarding.start_onboarding(chat_id)
            await onboarding.handle_onboard_message(text, chat_id)
            return

        log_prefix = f"[chat:{chat_id} sender:{sender_id} boss:{ctx.boss_chat_id}]"

        # ------------------------------------------------------------------
        # Step 3: Save user message to DB + Qdrant (async embed)
        # ------------------------------------------------------------------
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        vector = await openai_client.embed(text)
        asyncio.create_task(
            qdrant.upsert(
                collection=ctx.messages_collection,
                point_id=msg_id,
                chat_id=chat_id,
                role="user",
                text=text,
                vector=vector,
            )
        )

        # ------------------------------------------------------------------
        # Step 4: Gather context in parallel
        # ------------------------------------------------------------------
        assert _settings is not None, "init_agent() must be called before handling messages"
        assert ctx.boss_chat_id is not None, "ChatContext must have a boss_chat_id"
        boss_chat_id: int = ctx.boss_chat_id

        personal_note_row, recent, rag_results, people_summary = await asyncio.gather(
            db.get_note(boss_chat_id, "personal", str(boss_chat_id)),
            db.get_recent(chat_id, limit=_settings.recent_messages),
            qdrant.search(
                collection=ctx.messages_collection,
                query=text,
                chat_id=chat_id,
                top_n=_settings.rag_messages,
            ),
            _build_people_summary(ctx),
        )

        personal_note = personal_note_row["content"] if personal_note_row else "(Chưa có ghi chú)"

        logger.info(
            "%s Context: %d recent, %d RAG",
            log_prefix, len(recent), len(rag_results),
        )

        # ------------------------------------------------------------------
        # Step 5: Build group/context notes
        # ------------------------------------------------------------------
        context_note = ""
        if is_group:
            group_note_row = await db.get_note(
                boss_chat_id, "group", str(chat_id)
            )
            if group_note_row:
                context_note = f"Ghi chú nhóm: {group_note_row['content']}"
            else:
                context_note = f"Nhóm: {ctx.group_name or str(chat_id)}"

        # ------------------------------------------------------------------
        # Step 6: Build messages array
        # ------------------------------------------------------------------
        tz = ZoneInfo(_settings.timezone)
        current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

        boss = await db.get_boss(boss_chat_id)
        company = boss.get("company", "") if boss else ""
        company_info = f" — {company}" if company else ""

        chat_type = "Nhóm" if is_group else "Riêng tư"

        system_content = SECRETARY_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
            people_summary=people_summary,
            chat_type=chat_type,
            sender_name=ctx.sender_name,
            sender_type=ctx.sender_type,
            context_note=context_note,
        )

        messages = [{"role": "system", "content": system_content}]

        # RAG context as system message
        if rag_results:
            rag_text = "\n".join(
                f"[{m['role']}]: {m['content']}" for m in rag_results
            )
            messages.append({
                "role": "system",
                "content": f"Lịch sử liên quan:\n{rag_text}",
            })

        # Recent messages
        for msg in recent:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Current user message
        messages.append({"role": "user", "content": text})

        # ------------------------------------------------------------------
        # Step 7: Send thinking placeholder
        # ------------------------------------------------------------------
        thinking_msg_id = await telegram.send(chat_id, "_Đang xử lý..._")

        # ------------------------------------------------------------------
        # Step 8: Agent loop (max MAX_TOOL_ROUNDS)
        # ------------------------------------------------------------------
        reply_text = ""
        total_tokens = 0

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            response, usage = await openai_client.chat_with_tools(messages, TOOL_DEFINITIONS)
            total_tokens += usage.get("total_tokens", 0)

            logger.info(
                "%s Round %d | %din/%dout tokens",
                log_prefix,
                round_num,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            if response.tool_calls:
                messages.append(response)

                for tool_call in response.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = tool_call.function.arguments

                    # Update thinking UX
                    thinking_text = THINKING_MAP.get(tool_name, f"Đang xử lý {tool_name}...")
                    if thinking_msg_id:
                        await telegram.edit_message(chat_id, thinking_msg_id, f"_{thinking_text}_")

                    logger.info("%s TOOL: %s(%s)", log_prefix, tool_name, tool_args[:200])

                    result = await execute_tool(tool_name, tool_args, ctx)

                    # Handle advisor escalation
                    if result == "__ESCALATE__":
                        try:
                            args_dict = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                        except Exception:
                            args_dict = {}

                        if thinking_msg_id:
                            await telegram.edit_message(
                                chat_id, thinking_msg_id, "_Đang phân tích chiến lược..._"
                            )

                        from src import advisor  # noqa: PLC0415
                        question = args_dict.get("reason", text)
                        result = await advisor.run_advisor(
                            ctx,
                            context_str=f"Tin nhắn: {text}",
                            question=question,
                            settings=_settings,
                        )

                    logger.info("%s TOOL RESULT: %s", log_prefix, str(result)[:200])

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

                continue  # next round

            # Text reply — done
            reply_text = response.content or "..."
            break

        if not reply_text:
            reply_text = "Xin lỗi, em không thể xử lý yêu cầu này."

        # ------------------------------------------------------------------
        # Step 9: Replace thinking message with final reply
        # ------------------------------------------------------------------
        if thinking_msg_id:
            await telegram.edit_message(chat_id, thinking_msg_id, reply_text)
        else:
            await telegram.send(chat_id, reply_text)

        # ------------------------------------------------------------------
        # Step 10: Save assistant reply to DB + Qdrant
        # ------------------------------------------------------------------
        reply_id = await db.save_message(chat_id, "assistant", reply_text)
        reply_vector = await openai_client.embed(reply_text)
        asyncio.create_task(
            qdrant.upsert(
                collection=ctx.messages_collection,
                point_id=reply_id,
                chat_id=chat_id,
                role="assistant",
                text=reply_text,
                vector=reply_vector,
            )
        )

        elapsed = time.time() - start_time
        logger.info(
            "%s <<< OUTPUT: %s | %d tokens | %.1fs",
            log_prefix,
            reply_text[:150],
            total_tokens,
            elapsed,
        )

    except Exception:
        logger.exception("%s Error handling message", log_prefix)
        try:
            await telegram.send(chat_id, "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.")
        except Exception:
            logger.exception("%s Failed to send error message", log_prefix)
