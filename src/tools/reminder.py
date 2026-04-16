"""
Reminder tools: CRUD. ChatContext as first argument on each entrypoint.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import asyncio

from src import db
from src.config import Settings
from src.context import ChatContext
from src.services import lark


def _local_remind_string_to_utc_naive(remind_at: str) -> datetime:
    naive = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
    tz = ZoneInfo(Settings().timezone)
    return naive.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def _utc_naive_stored_to_local_display(remind_at_stored: str) -> str:
    dt = datetime.fromisoformat(remind_at_stored.strip())
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(Settings().timezone)).strftime("%Y-%m-%d %H:%M")


async def _resolve_target(ctx: ChatContext, target: str) -> tuple[Optional[int], str]:
    if not target:
        return None, ""
    all_people = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search_lower = target.lower()
    matches = [
        p
        for p in all_people
        if search_lower in str(p.get("Tên", "")).lower()
        or search_lower in str(p.get("Tên gọi", "")).lower()
    ]
    if not matches:
        return None, ""
    person = matches[0]
    name = str(person.get("Tên", target))
    chat_id_val = person.get("Chat ID")
    if chat_id_val:
        try:
            return int(chat_id_val), name
        except (ValueError, TypeError):
            pass
    return None, name


async def create_reminder(
    ctx: ChatContext,
    content: str,
    remind_at: str,
    target: str = "",
    task_keyword: str = "",
    project: str = "",
    workspace_ids: str = "current",
) -> str:
    """
    Create a reminder. task_keyword links to a task — scheduler will fetch live task
    status when the reminder fires. project is optional context for the message.
    """
    try:
        remind_dt = _local_remind_string_to_utc_naive(remind_at)
    except ValueError:
        return f"Dinh dang thoi gian khong hop le: '{remind_at}'. Vui long dung YYYY-MM-DD HH:MM."

    target_chat_id = None
    target_name = ""
    if target:
        target_chat_id, target_name = await _resolve_target(ctx, target)
        if not target_name:
            target_name = target

    # Encode task_keyword and project as structured prefix in content
    stored_content = content
    if project:
        stored_content = f"[project:{project}] {stored_content}"
    if task_keyword:
        stored_content = f"[task:{task_keyword}] {stored_content}"

    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=stored_content,
        remind_at=remind_dt,
        target_chat_id=target_chat_id,
        target_name=target_name,
    )

    # Sync to Lark async (non-blocking)
    if ctx.lark_table_reminders:
        boss = await db.get_boss(str(ctx.boss_chat_id))
        if boss:
            asyncio.create_task(lark.sync_reminder_to_lark(
                ctx.lark_base_token,
                ctx.lark_table_reminders,
                {
                    "content": stored_content,
                    "remind_at_local": remind_at,
                    "target_name": target_name,
                    "status": "pending",
                },
                reminder_id,
            ))

    if target_name and target_chat_id:
        return f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
    return f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."


async def list_reminders(
    ctx: ChatContext,
    status: str = "pending",
    limit: int = 30,
) -> str:
    if status not in ("pending", "done", "all"):
        return "Tham so status phai la: pending, done, hoac all."

    rows = await db.list_reminders(ctx.boss_chat_id, status=status, limit=limit)
    if not rows:
        return "Khong co nhac nho nao."

    lines = []
    for r in rows:
        rid = r["id"]
        st = r["status"]
        local_t = _utc_naive_stored_to_local_display(r["remind_at"])
        body = r["content"]
        if r.get("target_chat_id"):
            who = f"cho {r.get('target_name') or 'nguoi nhan'}"
        else:
            who = "cho sep"
        lines.append(f"#{rid} [{st}] {local_t} ({who}): {body}")
    return "\n".join(lines)


async def update_reminder(
    ctx: ChatContext,
    reminder_id: int,
    content: Optional[str] = None,
    remind_at: Optional[str] = None,
    target: Optional[str] = None,
) -> str:
    kwargs: dict = {}
    if content is not None:
        kwargs["content"] = content
    if remind_at is not None:
        try:
            kwargs["remind_at"] = _local_remind_string_to_utc_naive(remind_at)
        except ValueError:
            return f"Dinh dang thoi gian khong hop le: '{remind_at}'. Dung YYYY-MM-DD HH:MM."

    update_target = False
    target_chat_id: Optional[int] = None
    target_name = ""
    if target is not None:
        update_target = True
        if target.strip() == "":
            target_chat_id = None
            target_name = ""
        else:
            target_chat_id, target_name = await _resolve_target(ctx, target)
            if not target_name:
                target_name = target

    ok = await db.update_reminder(
        reminder_id,
        ctx.boss_chat_id,
        **kwargs,
        update_target=update_target,
        target_chat_id=target_chat_id,
        target_name=target_name,
    )
    if not ok:
        return f"Khong tim thay nhac nho #{reminder_id} hoac khong co truong nao de cap nhat."
    return f"Da cap nhat nhac nho #{reminder_id}."


async def delete_reminder(ctx: ChatContext, reminder_id: int) -> str:
    ok = await db.delete_reminder(reminder_id, ctx.boss_chat_id)
    if not ok:
        return f"Khong tim thay nhac nho #{reminder_id}."
    return f"Da xoa nhac nho #{reminder_id}."
