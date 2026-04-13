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
    "create_reminder": "Đang tạo nhắc nhở...",
    "list_reminders": "Đang xem nhắc nhở...",
    "update_reminder": "Đang cập nhật nhắc nhở...",
    "delete_reminder": "Đang xóa nhắc nhở...",
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
            group_info = await db.get_group(chat_id)
            if not group_info:
                return  # group chưa đăng ký → bỏ qua
            boss_id = group_info["boss_chat_id"]
            msg_id = await db.save_message(chat_id, "user", text, sender_id)
            vector = await openai_client.embed(text)
            asyncio.create_task(
                qdrant.upsert(
                    collection=f"messages_{boss_id}",
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
        # Step 1b: Join flow (active session or join inquiry intent)
        # ------------------------------------------------------------------
        if not is_group:
            from src import onboarding as _onb  # noqa: PLC0415
            if _onb.is_join_session(sender_id):
                reply = await _onb.handle_join_message(text, sender_id)
                if reply:
                    await telegram.send(chat_id, reply)
                return

            join_keywords = [
                "xem danh sách công ty", "muốn join", "muốn đăng ký vào",
                "danh sách tổ chức", "các công ty đang hỗ trợ",
                "có những công ty nào",
            ]
            if any(k in text.lower() for k in join_keywords):
                reply = await _onb.handle_join_inquiry(sender_id)
                await telegram.send(chat_id, reply)
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
        # Step 2b: Boss approving/rejecting a join request
        # ------------------------------------------------------------------
        if not is_group and ctx.sender_type == "boss":
            from src import onboarding as _onb  # noqa: PLC0415
            decision = await _onb.handle_boss_join_decision(text, str(ctx.boss_chat_id))
            if decision:
                await telegram.send(chat_id, decision)
                return

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
        total_prompt = 0
        total_completion = 0

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            response, usage = await openai_client.chat_with_tools(messages, TOOL_DEFINITIONS)
            total_tokens += usage.get("total_tokens", 0)
            total_prompt += usage.get("prompt_tokens", 0)
            total_completion += usage.get("completion_tokens", 0)

            logger.info(
                "%s Round %d | %din/%dout tokens",
                log_prefix,
                round_num,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            if response.tool_calls:
                messages.append(response)

                # Thinking UX: show all tool names being called
                tool_names = [tc.function.name for tc in response.tool_calls]
                if thinking_msg_id:
                    if len(tool_names) == 1:
                        thinking_text = THINKING_MAP.get(tool_names[0], f"Đang xử lý {tool_names[0]}...")
                    else:
                        parts = [THINKING_MAP.get(n, n) for n in tool_names]
                        thinking_text = " | ".join(parts)
                    await telegram.edit_message(chat_id, thinking_msg_id, f"_{thinking_text}_")

                for tc in response.tool_calls:
                    logger.info("%s TOOL: %s(%s)", log_prefix, tc.function.name, tc.function.arguments[:200])

                # Run all tool calls in parallel
                raw_results = await asyncio.gather(
                    *(execute_tool(tc.function.name, tc.function.arguments, ctx)
                      for tc in response.tool_calls)
                )

                # Process results + handle escalation
                for tool_call, result in zip(response.tool_calls, raw_results):
                    if result == "__ESCALATE__":
                        try:
                            args_dict = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
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

        await db.log_token_usage(boss_chat_id, "chat", total_prompt, total_completion, total_tokens)

    except Exception:
        logger.exception("%s Error handling message", log_prefix)
        try:
            await telegram.send(chat_id, "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.")
        except Exception:
            logger.exception("%s Failed to send error message", log_prefix)


# ---------------------------------------------------------------------------
# Scheduler-driven reminder delivery via LLM
# ---------------------------------------------------------------------------

REMINDER_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}. Giao tiếp tiếng Việt, thân thiện, ngắn gọn.

## Personal Note:
{personal_note}

## Thời gian: {current_time}

## Nhiệm vụ:
Hệ thống đã đến giờ gửi nhắc nhở. Hãy viết MỘT tin nhắn nhắc nhở tự nhiên, thân thiện dựa trên thông tin bên dưới.
- Không cần nói "Nhắc nhở:" — hãy viết như đang nhắn tin bình thường.
- Xưng hô theo personal note.
- Ngắn gọn, 1-3 câu là đủ.
"""


async def send_reminder(reminder: dict, settings: Settings):
    """Gửi reminder qua LLM để có giọng tự nhiên. Fallback nếu LLM lỗi."""
    boss_chat_id = reminder["boss_chat_id"]
    target_id = reminder.get("target_chat_id")
    target_name = reminder.get("target_name", "")
    content = reminder["content"]

    log_prefix = f"[reminder:{reminder['id']}]"

    try:
        ctx = await context.resolve(boss_chat_id, boss_chat_id, False)
        if not ctx:
            logger.warning("%s Cannot resolve boss context, using fallback", log_prefix)
            raise ValueError("no context")

        personal_note_row = await db.get_note(boss_chat_id, "personal", str(boss_chat_id))
        personal_note = personal_note_row["content"] if personal_note_row else ""

        boss = await db.get_boss(boss_chat_id)
        company = boss.get("company", "") if boss else ""
        company_info = f" — {company}" if company else ""

        tz = ZoneInfo(settings.timezone)
        current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

        system_content = REMINDER_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
        )

        if target_id:
            user_msg = (
                f"Nhắc nhở cho {target_name or 'người nhận'}: \"{content}\"\n"
                f"Viết tin nhắn gửi cho {target_name or 'người nhận'} (xưng là trợ lý của {ctx.boss_name})."
            )
        else:
            user_msg = (
                f"Nhắc nhở cho sếp: \"{content}\"\n"
                f"Viết tin nhắn gửi cho sếp."
            )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg},
        ]

        response, usage = await openai_client.chat_with_tools(messages, tools=[])
        reply = response.content or ""

        logger.info("%s LLM reply (%d tokens): %s", log_prefix, usage.get("total_tokens", 0), reply[:150])

        await db.log_token_usage(
            boss_chat_id, "reminder",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            usage.get("total_tokens", 0),
        )

        if not reply.strip():
            raise ValueError("empty LLM reply")

    except Exception:
        logger.exception("%s LLM failed, using fallback", log_prefix)
        if target_id:
            reply = f"Nhắc nhở từ {target_name or 'sếp'}: {content}"
        else:
            reply = f"Nhắc nhở: {content}"

    if target_id:
        await telegram.send(target_id, reply)
        # Báo sếp biết đã nhắc (raw, không cần LLM cho dòng này)
        await telegram.send(boss_chat_id, f"✓ Đã nhắc {target_name or 'người nhận'}: {content}")
    else:
        await telegram.send(boss_chat_id, reply)
