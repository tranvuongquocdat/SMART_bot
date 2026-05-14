"""Reminder agent — formats and sends a single reminder via LLM.

Triggered by the scheduler when a `reminders` row reaches `remind_at`.
The LLM rewrites the stored content into a natural message; on any LLM
failure we fall back to a raw template so the user still gets the reminder.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src import context, db
from src.config import Settings
from src.channels import telegram_singleton as telegram
from src.infrastructure import lark_client as lark
from src.agent.llm_for_ctx import get_llm_for_ctx

logger = logging.getLogger("agent.reminder")


def _destination_for(row: dict) -> tuple[str, bool]:
    """Pick the dispatch chat for a reminder row.

    Returns (chat_id, cc_boss_separately).
    Priority: target_chat_id → source_chat_id → boss_chat_id.
    Boss is cc'd only when the reminder went to a specific target person.
    """
    if row.get("target_chat_id"):
        return row["target_chat_id"], True
    if row.get("source_chat_id"):
        return row["source_chat_id"], False
    return row["boss_chat_id"], False


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


async def send_reminder(reminder: dict, settings: Settings) -> None:
    """Gửi reminder qua LLM để có giọng tự nhiên. Fallback nếu LLM lỗi."""
    boss_chat_id = reminder["boss_chat_id"]
    target_id = reminder.get("target_chat_id")
    target_name = reminder.get("target_name", "")
    content = reminder["content"]

    # Parse [task:keyword] and [project:name] prefixes from stored content.
    task_status_note = ""
    while content.startswith("[task:") or content.startswith("[project:"):
        if content.startswith("[task:"):
            end = content.index("]")
            task_kw = content[6:end]
            content = content[end + 2:] if len(content) > end + 2 else content[end + 1:]
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

        llm = await get_llm_for_ctx(ctx)
        response, usage = await llm.chat_with_tools(messages, tools=[])
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

    dest_chat_id, cc_boss = _destination_for(reminder)
    await telegram.send(dest_chat_id, reply)
    # Main delivery succeeded → mark done immediately so any failure in the
    # best-effort follow-ups (CC boss, source-group notify, outbound log)
    # cannot leave status=pending and trigger a re-fire next minute.
    await db.mark_reminder_done(reminder["id"])
    if dest_chat_id == target_id:
        try:
            await db.log_outbound_dm(
                boss_chat_id=boss_chat_id,
                to_chat_id=target_id,
                to_name=target_name or "",
                content=reply,
                trigger_type="reminder",
            )
        except Exception:
            logger.warning("%s log_outbound_dm failed", log_prefix, exc_info=True)
    if cc_boss:
        try:
            await telegram.send(boss_chat_id, f"✓ Đã nhắc {target_name or 'người nhận'}: {content}")
        except Exception:
            logger.warning("%s CC boss send failed", log_prefix, exc_info=True)

    # When the reminder was created via group @mention, also post a short
    # notice into that source group so the rest of the team sees the followup
    # the boss asked for publicly. Skip when source is the same as target/boss
    # to avoid duplicate sends.
    source_chat_id = reminder.get("source_chat_id")
    if (
        source_chat_id
        and source_chat_id != dest_chat_id
        and source_chat_id != boss_chat_id
    ):
        try:
            await telegram.send(
                source_chat_id,
                f"⏰ Vừa nhắc {target_name or 'người nhận'}: {content}",
            )
        except Exception:
            logger.warning("%s source-group notify failed", log_prefix, exc_info=True)
