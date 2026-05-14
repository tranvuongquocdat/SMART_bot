"""Secretary agent — main LLM loop for DM + group-mention messages.

Entry point: `handle_message`. Routes through the `ToolDispatcher` registry
defined in `src.agent` (kept there as the wiring stub until Phase 5b's
`AppContainer` takes over).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src import context, db, identity
from src.config import Settings
from src.context import ChatContext
from src.channels import telegram_singleton as telegram
from src.infrastructure import qdrant_client as qdrant
from src.infrastructure import lark_client as lark
from src.agent.tool_definitions import TOOL_DEFINITIONS
from src.agent.llm_for_ctx import get_llm_for_ctx, get_default_llm
from src.infrastructure.llm.factory import get_llm_client
from src.utils.sentinels import strip_sentinels

logger = logging.getLogger("agent")

_settings: Settings | None = None

MAX_TOOL_ROUNDS = 10

# --- Pending-attachment buffer ---------------------------------------------
# When a boss sends a file/image with no user caption (just the file), the
# bot stays silent and stashes the attachments for a short window. The next
# text message in the same chat picks them up and processes file + prompt
# together — same UX as ChatGPT file uploads.

_PENDING_TTL_SEC = 300  # 5 minutes
_pending_attachments: dict[str, tuple[float, list]] = {}


def _looks_like_filename(text: str, atts: list) -> bool:
    """True when `text` is auto-generated from the attachment (e.g. Zalo
    sets text=content.title which is the filename) — i.e. not a real
    user-typed caption."""
    t = (text or "").strip()
    if not t:
        return True
    filenames = {a.filename for a in atts if getattr(a, "filename", "")}
    return t in filenames


def _sweep_expired_pending() -> None:
    now = time.monotonic()
    for k in [k for k, (deadline, _) in _pending_attachments.items() if deadline < now]:
        _pending_attachments.pop(k, None)


def init(settings: Settings) -> None:
    """Wire the live Settings instance. Called from main.py lifespan via
    `src.agent.init_agent`."""
    global _settings
    _settings = settings


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
{group_section}{zalo_guidance}
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
    "fetch_url": "Đang mở link...",
    "escalate_to_advisor": "Đang phân tích chiến lược...",
    "create_reminder": "Đang tạo nhắc nhở...",
    "list_reminders": "Đang xem nhắc nhở...",
    "update_reminder": "Đang cập nhật nhắc nhở...",
    "delete_reminder": "Đang xóa nhắc nhở...",
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
# Helpers
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


async def _notify_boss_new_members(
    boss_chat_id: str, group_label: str, new_members: list[dict],
) -> None:
    """When somebody joins an onboarded group, DM the boss so they can decide
    whether to add them to the team (and via which role). Channel-agnostic:
    `telegram.send` routes to whichever channel the boss registered with."""
    try:
        names = []
        for m in new_members or []:
            n = (m.get("name") or "").strip()
            u = (m.get("username") or "").strip()
            if n and u:
                names.append(f"{n} (@{u})")
            elif n:
                names.append(n)
            elif u:
                names.append(f"@{u}")
        if not names:
            return
        joined = ", ".join(names)
        plural = "Có người" if len(names) == 1 else f"Có {len(names)} người"
        msg = (
            f"{plural} vừa vào group *{group_label}*: {joined}\n\n"
            f"Anh có muốn thêm họ vào team không? (member / partner — hoặc bỏ qua)"
        )
        await telegram.send(boss_chat_id, msg)
    except Exception:
        logger.exception("[new-member-notify] failed for boss=%s", boss_chat_id)


def _build_zalo_guidance(settings) -> str:
    """Tell the agent how Zalo's personal-account model works so it can
    remind the boss when they forget the onboarding rules."""
    if not getattr(settings, "zalo_enabled", False):
        return ""
    phrase = getattr(settings, "zalo_onboard_phrase", "") or ""
    return (
        f"## Zalo channel rules\n"
        f"Bot chạy trên một tài khoản Zalo cá nhân (không phải bot account riêng).\n"
        f"Để giảm noise, kênh Zalo chỉ forward tin tới bạn khi:\n"
        f"  • DM từ sếp đã đăng ký, HOẶC DM chứa cụm khởi tạo \"{phrase}\"\n"
        f"  • Group đã được sếp đăng ký, HOẶC group có sếp @mention bot\n"
        f"\n"
        f"Khi sếp hỏi cách mời người khác, sao bot không trả lời ai đó, hay có\n"
        f"vẻ quên cách bắt đầu — chủ động nhắc:\n"
        f"  - Onboard người mới: bảo họ DM tài khoản Zalo của bot kèm cụm \"{phrase}\".\n"
        f"  - Đăng ký group mới: thêm bot vào group, sếp @mention bot kèm yêu\n"
        f"    cầu \"đăng ký group này\".\n"
        f"\n"
    )


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


async def _build_turn_messages(
    ctx: ChatContext,
    text: str,
    chat_id: str,
    is_group: bool,
    built: dict,
    group_ctx: dict | None,
) -> tuple[list[dict], int, int]:
    """Returns (messages, recent_count, rag_count)."""
    assert _settings is not None
    from src.context_builder import membership_summary as _ms  # noqa: PLC0415
    boss_chat_id: str = ctx.boss_chat_id

    personal_note_row, recent, rag_results, people_summary = await asyncio.gather(
        db.get_note(boss_chat_id, "personal", str(boss_chat_id)),
        db.get_recent(chat_id, limit=_settings.recent_messages),
        qdrant.search(
            collection=ctx.messages_collection,
            query=strip_sentinels(text),
            chat_id=chat_id,
            top_n=_settings.rag_messages,
        ),
        _build_people_summary(ctx),
    )
    personal_note = personal_note_row["content"] if personal_note_row else "(Chưa có ghi chú)"

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
        zalo_guidance=_build_zalo_guidance(_settings),
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
    chat_id: str,
    sender_id: str,
    is_group: bool,
    bot_mentioned: bool,
    group_name: str = "",
    *,
    sender_name: str = "",
    mentions: list[dict] | None = None,
    username_mentions: list[str] | None = None,
    reply_to: dict | None = None,
    new_members: list[dict] | None = None,
    attachments: list | None = None,
):
    # Lazy import — `src.agent` imports us back, so we resolve at call time.
    from src.agent import _dispatcher

    start_time = time.time()
    log_prefix = f"[chat:{chat_id} sender:{sender_id}]"
    mentions = mentions or []
    username_mentions = username_mentions or []
    new_members = new_members or []

    logger.info("%s >>> INPUT: %s", log_prefix, text[:200])

    # ---- Pending-attachment buffer (ChatGPT-style file-then-prompt) ----
    _sweep_expired_pending()
    attachments = attachments or []
    if attachments and _looks_like_filename(text, attachments):
        # Bare file message — defer until the next text prompt. Multiple
        # files in quick succession are accumulated; each new bare-file
        # message extends the deadline.
        existing = _pending_attachments.get(chat_id)
        prior = list(existing[1]) if existing else []
        combined = prior + list(attachments)
        _pending_attachments[chat_id] = (
            time.monotonic() + _PENDING_TTL_SEC, combined,
        )
        logger.info(
            "%s file-only message stashed (+%d files, total %d in stash)",
            log_prefix, len(attachments), len(combined),
        )
        return  # silent — no reply
    if not attachments and chat_id in _pending_attachments:
        deadline, pending = _pending_attachments.pop(chat_id)
        if time.monotonic() < deadline:
            attachments = list(pending)
            logger.info(
                "%s merged %d pending attachments with new prompt",
                log_prefix, len(pending),
            )

    # ---- Step 0: Ingest file attachments → sentinels appended to text ----
    if attachments:
        from src.agent.file_ingestion import ingest as _ingest_files
        from src.infrastructure import openai_client as _openai_client_mod
        try:
            ingested = await _ingest_files(
                _openai_client_mod.get_client(), attachments, chat_id,
            )
            if ingested:
                text = (text + "\n\n" + ingested).strip() if text else ingested
                logger.info("%s file attachments ingested (%d)", log_prefix, len(attachments))
        except Exception:
            logger.exception("%s file_ingestion failed", log_prefix)

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
        # ---- Step 0.5: Reset / re-onboard hook ------------------------
        # When the inbound text contains the configured onboard phrase,
        # short-circuit: clear any half-finished onboarding state and
        # restart from scratch — OR for users who already have a workspace,
        # send a no-op info reply (we don't nuke active memberships).
        if not is_group and text and _settings:
            from src import onboarding as _ob  # noqa: PLC0415
            handled = await _ob.maybe_handle_reset_phrase(
                text, chat_id, sender_id, _settings.zalo_onboard_phrase,
            )
            if handled:
                return

        # ---- Step 1: Group routing ----
        if is_group:
            group_info = await db.get_group(chat_id)

            if not bot_mentioned:
                if not group_info:
                    return
                boss_id = group_info["boss_chat_id"]
                # Proactive: ping boss when a new member joins an onboarded
                # group. Channel of the boss is preserved by telegram.send →
                # _messenger_for routing (Zalo boss gets a Zalo DM).
                if new_members:
                    asyncio.create_task(_notify_boss_new_members(
                        boss_id, group_name or chat_id, new_members,
                    ))
                msg_id = await db.save_message(chat_id, "user", text, sender_id)
                _boss_row = await db.get_boss(boss_id) or {}
                _llm = get_llm_client(_boss_row, _settings or Settings())
                _clean = strip_sentinels(text)
                vector, _dim = await _llm.embed(_clean)
                asyncio.create_task(
                    qdrant.upsert(
                        collection=f"messages_{boss_id}_{_dim}",
                        point_id=msg_id,
                        chat_id=chat_id,
                        role="user",
                        text=_clean,
                        vector=vector,
                    )
                )
                logger.info("%s Group message saved (not mentioned, no reply)", log_prefix)
                return

            if not group_info:
                try:
                    await db.save_message(chat_id, "user", text, sender_id)
                except Exception:
                    logger.warning("%s save_message (onboarding user) failed", log_prefix, exc_info=True)
                from src import group_onboarding  # noqa: PLC0415
                if await group_onboarding.is_group_onboarding(chat_id):
                    await group_onboarding.handle(text, chat_id, group_name)
                else:
                    await group_onboarding.start(chat_id, sender_id)
                return

        # ---- Step 2: Build rich context ----
        from src import context_builder as _cb  # noqa: PLC0415
        built = await _cb.build(sender_id, chat_id)

        ctx = await context.resolve(
            chat_id, sender_id, is_group,
            preferred_boss_id=built["primary_workspace_id"],
        )
        if ctx is None:
            from src import onboarding  # noqa: PLC0415
            try:
                await db.save_message(chat_id, "user", text, sender_id)
            except Exception:
                logger.warning("%s save_message (DM onboarding user) failed", log_prefix, exc_info=True)
            if not await onboarding.is_onboarding(chat_id):
                await onboarding.start_onboarding(chat_id, sender_id)
            await onboarding.handle_onboard_message(text, chat_id, sender_id)
            return

        log_prefix = f"[chat:{chat_id} sender:{sender_id} boss:{ctx.boss_chat_id}]"

        group_ctx = None
        if is_group:
            from src.context_builder import build_group_context as _bgc  # noqa: PLC0415
            try:
                group_ctx = await _bgc(chat_id, ctx.boss_chat_id)
            except Exception:
                logger.exception("%s Failed to build group context", log_prefix)

        # ---- Step 3: Save user message ----
        msg_id = await db.save_message(chat_id, "user", text, sender_id)
        llm = await get_llm_for_ctx(ctx)
        _clean_user = strip_sentinels(text)
        vector, _ = await llm.embed(_clean_user)
        asyncio.create_task(
            qdrant.upsert(
                collection=ctx.messages_collection,
                point_id=msg_id,
                chat_id=chat_id,
                role="user",
                text=_clean_user,
                vector=vector,
            )
        )

        # ---- Step 4-6: Build messages array ----
        assert _settings is not None, "init() must be called before handling messages"
        assert ctx.boss_chat_id is not None, "ChatContext must have a boss_chat_id"
        messages, recent_count, rag_count = await _build_turn_messages(
            ctx, text, chat_id, is_group, built, group_ctx,
        )
        logger.info("%s Context: %d recent, %d RAG", log_prefix, recent_count, rag_count)

        # ---- Step 7: Thinking placeholder ----
        thinking_msg_id = await telegram.send(chat_id, "_Đang xử lý..._", save_history=False)

        # ---- Step 8: Agent loop ----
        reply_text = ""
        total_tokens = 0
        total_prompt = 0
        total_completion = 0

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            response, usage = await llm.chat_with_tools(messages, TOOL_DEFINITIONS)
            total_tokens += usage.get("total_tokens", 0)
            total_prompt += usage.get("prompt_tokens", 0)
            total_completion += usage.get("completion_tokens", 0)

            logger.info(
                "%s Round %d | %din/%dout tokens",
                log_prefix, round_num,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            if response.tool_calls:
                messages.append(response)

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

                raw_results = await asyncio.gather(
                    *(_dispatcher.execute(tc.function.name, tc.function.arguments, ctx)
                      for tc in response.tool_calls)
                )

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
                continue

            reply_text = response.content or "..."
            break

        if not reply_text:
            reply_text = "Xin lỗi, em không thể xử lý yêu cầu này."

        # ---- Step 9: Replace thinking with final reply ----
        if thinking_msg_id:
            await telegram.edit_message(chat_id, thinking_msg_id, reply_text)
        else:
            await telegram.send(chat_id, reply_text, save_history=False)

        # ---- Step 10: Save assistant reply ----
        reply_id = await db.save_message(chat_id, "assistant", reply_text)
        reply_vector, _ = await llm.embed(reply_text)
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
            log_prefix, reply_text[:150], total_tokens, elapsed,
        )

        await db.log_token_usage(ctx.boss_chat_id, "chat", total_prompt, total_completion, total_tokens)

    except Exception:
        logger.exception("%s Error handling message", log_prefix)
        try:
            await telegram.send(chat_id, "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.")
        except Exception:
            logger.exception("%s Failed to send error message", log_prefix)
