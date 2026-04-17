"""
Secretary Agent — multi-user routing, thinking UX, tool loop.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src import context, db, identity
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

SECRETARY_PROMPT = """You are the AI secretary of {boss_name}{company_info}.

## Context
Time: {current_time}
Language: respond in {language}
Talking to: {sender_name} ({sender_type})
Their workspaces: {memberships_summary}
Active workspace: {boss_name}'s workspace

## Team
{people_summary}

## Your notes
{personal_note}

## Current conversation context
{context_note}

## Active sessions
{active_sessions_summary}
{group_section}
## Who you are
You genuinely know this team. You care about their wellbeing, not just their output.
When making decisions that affect someone, understand their situation before acting.

You remember everything shared with you. Your notes are your extended memory —
when context feels incomplete about a person or project, check them.

You have access to multiple workspaces. When a question spans workspaces or
doesn't specify one, use your judgment about where to look.

You use tools to understand context before acting, not just to execute commands.

## Permissions
- Boss ({boss_name}): full access. Confirm before deleting anything.
- Member/Partner: can view and update their own tasks. Significant changes need boss approval.
- Group: respond only when tagged. Permissions follow the person who tagged you.

## Tool errors
If a tool returns [TOOL_ERROR:lark] — Lark is unreachable. Retry once. If it fails again, tell the user clearly: "Hệ thống Lark đang có vấn đề, vui lòng thử lại sau."
If a tool returns [TOOL_ERROR:not_found] — Ask the user to clarify (different name? different workspace?).
If a tool returns [TOOL_ERROR:unknown] — Surface the error message directly to the user. Do not claim the action succeeded.
Never ignore a [TOOL_ERROR] response.

## Cross-chat rules
- Before answering "have you messaged X" or "did you remind X about Y": always call get_communication_log first.
- When the user asks about tasks/projects/workload across all their workspaces: pass workspace_ids="all".
- After a non-boss member marks a task complete (status → Hoàn thành or Huỷ): the update_task tool will auto-notify the boss and group. You do not need to do this manually.

## Identity rules
- chat_id là nguồn duy nhất xác định 1 người; tên có thể trùng/nhập nhằng/typo.
- Khi cần nhắn/nhắc/check ai đó mà Lark record thiếu Chat ID, GỌI resolve_person trước — hệ thống có thể đã biết chat_id qua bosses/memberships/seen_contacts.
- get_communication_log trả 2 section: outbound_messages (bot gửi qua send_dm/reminder) VÀ messages DM thread. Đọc cả 2 rồi mới kết luận.
- Khi resolve_person trả cùng 1 chat_id ở nhiều dòng khác source, và 1 dòng là lark_people chưa có Chat ID — đề xuất link_contact_to_person. Nếu boss chưa xác nhận rõ, hỏi confirm trước khi gắn.
- Nếu link_contact_to_person trả [CONFLICT] — KHÔNG tự overwrite; báo boss và chờ xác nhận.
- Trong group mà cần danh sách admin, gọi get_group_admins. Không list được non-admin (Telegram giới hạn).
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
    "escalate_to_advisor": "Đang phân tích chiến lược...",
    "create_reminder": "Đang tạo nhắc nhở...",
    "list_reminders": "Đang xem nhắc nhở...",
    "update_reminder": "Đang cập nhật nhắc nhở...",
    "delete_reminder": "Đang xóa nhắc nhở...",
    # Tools added after initial release
    "send_dm": "Đang gửi tin nhắn...",
    "broadcast": "Đang gửi thông báo hàng loạt...",
    "get_communication_log": "Đang tra lịch sử liên lạc...",
    "check_team_engagement": "Đang kiểm tra tương tác team...",
    "search_notes": "Đang tìm ghi chú...",
    "get_project_report": "Đang tạo báo cáo dự án...",
    "get_project": "Đang xem dự án...",
    "list_projects": "Đang xem danh sách dự án...",
    "create_project": "Đang tạo dự án...",
    "update_project": "Đang cập nhật dự án...",
    "delete_project": "Đang xóa dự án...",
    "append_note": "Đang thêm ghi chú...",
    "update_note": "Đang cập nhật ghi chú...",
    "create_idea": "Đang lưu ý tưởng...",
    "switch_workspace": "Đang chuyển workspace...",
    "approve_join": "Đang duyệt tham gia...",
    "reject_join": "Đang từ chối...",
    "list_pending_approvals": "Đang xem yêu cầu chờ...",
    "approve_task_change": "Đang duyệt thay đổi...",
    "reject_task_change": "Đang từ chối thay đổi...",
    "resolve_person": "Đang tra ứng viên người...",
    "link_contact_to_person": "Đang gắn Chat ID vào Lark...",
    "list_unlinked_contacts": "Đang xem chat_id chưa gắn...",
    "get_group_admins": "Đang xem admin group...",
    "summarize_group_conversation": "Đang tóm tắt group...",
    "update_group_note": "Đang cập nhật note group...",
    "broadcast_to_group": "Đang gửi thông báo vào group...",
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
# Session summary helper
# ---------------------------------------------------------------------------

def _build_group_section(group_ctx: dict | None) -> str:
    if not group_ctx:
        return ""
    project_str = ""
    if group_ctx.get("project"):
        p = group_ctx["project"]
        project_str = f" | Project: {p['name']} ({p['status']})" if p.get("status") else f" | Project: {p['name']}"
    participants = ", ".join(group_ctx.get("recent_participants", [])) or "chưa có"
    note = group_ctx.get("group_note") or "chưa có"
    topic = group_ctx.get("active_topic") or "chưa rõ"
    return (
        f"## Nhóm\n"
        f"Tên: {group_ctx.get('group_name', '')}{project_str}\n"
        f"Đang bàn: {topic}\n"
        f"Tham gia gần đây: {participants}\n"
        f"Ghi chú nhóm: {note}\n\n"
    )


def _build_sessions_summary(sessions: dict) -> str:
    parts = []
    if sessions.get("reset_pending"):
        parts.append(f"Reset flow active (step {sessions['reset_pending'].get('step', '?')})")
    if sessions.get("join_pending"):
        parts.append(f"{len(sessions['join_pending'])} join request(s) you sent pending approval")
    if sessions.get("approvals_pending"):
        parts.append(f"{len(sessions['approvals_pending'])} item(s) awaiting your approval")
    return "; ".join(parts) if parts else "none"


# ---------------------------------------------------------------------------
# Turn context builder — gathers data + formats system prompt + builds msgs
# ---------------------------------------------------------------------------

async def _build_turn_messages(
    ctx,
    text: str,
    chat_id: int,
    is_group: bool,
    built: dict,
    group_ctx: dict | None,
) -> tuple[list[dict], int, int]:
    """
    Returns (messages, recent_count, rag_count). Handles both DM and group.
    Group note is read from group_ctx (deduplicated from the old inline read).
    """
    assert _settings is not None
    from src.context_builder import membership_summary as _ms  # noqa: PLC0415
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

    # context_note for group turns — reuse group_ctx to avoid duplicate DB read
    context_note = ""
    if is_group:
        gnote = (group_ctx or {}).get("group_note")
        if gnote:
            context_note = f"Ghi chú nhóm: {gnote}"
        else:
            gname = (group_ctx or {}).get("group_name") or ctx.group_name or str(chat_id)
            context_note = f"Nhóm: {gname}"

    tz = ZoneInfo(_settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")
    boss = await db.get_boss(boss_chat_id)
    company = boss.get("company", "") if boss else ""
    company_info = f" — {company}" if company else ""

    system_content = SECRETARY_PROMPT.format(
        boss_name=ctx.boss_name,
        company_info=company_info,
        personal_note=personal_note,
        current_time=current_time,
        people_summary=people_summary,
        sender_name=ctx.sender_name,
        sender_type=ctx.sender_type,
        context_note=context_note,
        language=built["language"],
        memberships_summary=_ms(built["memberships"]),
        active_sessions_summary=_build_sessions_summary(built["active_sessions"]),
        group_section=_build_group_section(group_ctx),
    )

    messages: list[dict] = [{"role": "system", "content": system_content}]
    if rag_results:
        rag_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in rag_results)
        messages.append({"role": "system", "content": f"Lịch sử liên quan:\n{rag_text}"})
    for msg in recent:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": text})

    return messages, len(recent), len(rag_results)


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_message(
    text: str,
    chat_id: int,
    sender_id: int,
    is_group: bool,
    bot_mentioned: bool,
    group_name: str = "",
    *,
    sender_name: str = "",
    mentions: list[dict] | None = None,
    username_mentions: list[str] | None = None,
    reply_to: dict | None = None,
    new_members: list[dict] | None = None,
):
    start_time = time.time()
    log_prefix = f"[chat:{chat_id} sender:{sender_id}]"
    mentions = mentions or []
    username_mentions = username_mentions or []
    new_members = new_members or []

    logger.info("%s >>> INPUT: %s", log_prefix, text[:200])

    # Fire-and-forget: harvest chat_ids observed in this update.
    # Index only — must not block or crash message flow.
    sender_dict = {"id": sender_id, "name": sender_name, "username": ""} if sender_id else None
    asyncio.create_task(
        identity.harvest(
            context_chat_id=chat_id,
            sender=sender_dict,
            mentions=mentions,
            reply_to=reply_to,
            new_members=new_members,
        )
    )

    try:
        # ------------------------------------------------------------------
        # Step 1: Group messages
        # ------------------------------------------------------------------
        if is_group:
            group_info = await db.get_group(chat_id)

            if not bot_mentioned:
                # Silent indexing only — persist message, no reply
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

            # Bot mentioned — if group not registered, run group onboarding
            if not group_info:
                from src import group_onboarding  # noqa: PLC0415
                if await group_onboarding.is_group_onboarding(chat_id):
                    await group_onboarding.handle(text, chat_id, group_name)
                else:
                    await group_onboarding.start(chat_id, sender_id)
                return

        # ------------------------------------------------------------------
        # Step 2: Build rich context via context_builder
        # ------------------------------------------------------------------
        from src import context_builder as _cb  # noqa: PLC0415
        built = await _cb.build(sender_id, chat_id)

        # ------------------------------------------------------------------
        # Step 2b: Resolve context (using preferred workspace from context_builder)
        # ------------------------------------------------------------------
        ctx = await context.resolve(
            chat_id, sender_id, is_group,
            preferred_boss_id=built["primary_workspace_id"],
        )
        if ctx is None:
            # Unknown user — trigger onboarding state machine
            from src import onboarding  # noqa: PLC0415
            if not await onboarding.is_onboarding(chat_id):
                await onboarding.start_onboarding(chat_id)
            await onboarding.handle_onboard_message(text, chat_id)
            return

        log_prefix = f"[chat:{chat_id} sender:{sender_id} boss:{ctx.boss_chat_id}]"

        # ------------------------------------------------------------------
        # Step 2c: Group context enrichment
        # ------------------------------------------------------------------
        group_ctx = None
        if is_group:
            from src.context_builder import build_group_context as _bgc  # noqa: PLC0415
            try:
                group_ctx = await _bgc(chat_id, ctx.boss_chat_id)
            except Exception:
                logger.exception("%s Failed to build group context", log_prefix)

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
        # Step 4-6: Gather context + build messages array (extracted helper)
        # ------------------------------------------------------------------
        assert _settings is not None, "init_agent() must be called before handling messages"
        assert ctx.boss_chat_id is not None, "ChatContext must have a boss_chat_id"
        messages, recent_count, rag_count = await _build_turn_messages(
            ctx, text, chat_id, is_group, built, group_ctx,
        )
        logger.info("%s Context: %d recent, %d RAG", log_prefix, recent_count, rag_count)

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
                    await telegram.edit_message(chat_id, thinking_msg_id, f"_{thinking_text}_", parse_mode="")

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

        await db.log_token_usage(ctx.boss_chat_id, "chat", total_prompt, total_completion, total_tokens)

    except Exception:
        logger.exception("%s Error handling message", log_prefix)
        try:
            await telegram.send(chat_id, "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.")
        except Exception:
            logger.exception("%s Failed to send error message", log_prefix)


# ---------------------------------------------------------------------------
# Scheduler-driven reminder delivery via LLM
# ---------------------------------------------------------------------------

REMINDER_PROMPT = """Bạn là thư ký AI của {boss_name}{company_info}.
Language: {language}. Respond entirely in that language. Thân thiện, ngắn gọn.

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

    # Parse [task:keyword] and [project:name] prefixes from stored content
    task_status_note = ""
    while content.startswith("[task:") or content.startswith("[project:"):
        if content.startswith("[task:"):
            end = content.index("]")
            task_kw = content[6:end]
            content = content[end + 2:] if len(content) > end + 2 else content[end + 1:]
            # Fetch live task status
            try:
                ctx_temp = await context.resolve(boss_chat_id, boss_chat_id, False)
                if ctx_temp:
                    tasks = await lark.search_records(ctx_temp.lark_base_token, ctx_temp.lark_table_tasks)
                    matched = [t for t in tasks if task_kw.lower() in t.get("Tên task", "").lower()]
                    if matched:
                        t = matched[0]
                        task_status_note = f"\n(Task '{t.get('Tên task')}' hiện: {t.get('Status', '?')})"
            except Exception:
                pass
        elif content.startswith("[project:"):
            end = content.index("]")
            content = content[end + 2:] if len(content) > end + 2 else content[end + 1:]

    if task_status_note:
        content = content + task_status_note

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
        language = boss.get("language", "vi") if boss else "vi"

        tz = ZoneInfo(settings.timezone)
        current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

        system_content = REMINDER_PROMPT.format(
            boss_name=ctx.boss_name,
            company_info=company_info,
            personal_note=personal_note,
            current_time=current_time,
            language=language,
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
        await db.log_outbound_dm(
            boss_chat_id=boss_chat_id,
            to_chat_id=int(target_id),
            to_name=target_name or "",
            content=reply,
            trigger_type="reminder",
        )
        # Báo sếp biết đã nhắc (raw, không cần LLM cho dòng này)
        await telegram.send(boss_chat_id, f"✓ Đã nhắc {target_name or 'người nhận'}: {content}")
    else:
        await telegram.send(boss_chat_id, reply)
