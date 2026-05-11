"""
Reminder tools: CRUD. ChatContext as first argument on each entrypoint.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import asyncio

from src import db
from src.channels import telegram_singleton as telegram
from src.config import Settings
from src.context import ChatContext
from src.infrastructure import lark_client as lark


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
            # Lark stores external numeric. reminders.target_chat_id holds
            # internal UUID — resolve before returning so the caller writes
            # the right shape into the DB.
            internal_id = await db.resolve_or_create_person(
                "telegram", str(int(chat_id_val)), name, ""
            )
            return internal_id, name
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

    stored_content = content
    if project:
        stored_content = f"[project:{project}] {stored_content}"
    if task_keyword:
        stored_content = f"[task:{task_keyword}] {stored_content}"

    source_chat_id = str(ctx.chat_id) if ctx.is_group else None
    reminder_id = await db.create_reminder(
        boss_chat_id=ctx.boss_chat_id,
        content=stored_content,
        remind_at=remind_dt,
        target_chat_id=target_chat_id,
        target_name=target_name,
        source_chat_id=source_chat_id,
    )

    base = (
        f"Da tao nhac nho #{reminder_id}: '{content}' cho {target_name} luc {remind_at}."
        if target_name and target_chat_id
        else f"Da tao nhac nho #{reminder_id}: '{content}' luc {remind_at}."
    )

    if ctx.is_group:
        target_disp = target_name or "sếp"
        summary = f"Reminder: {content} for {target_disp} at {remind_at}"
        try:
            await telegram.send(str(ctx.chat_id), summary, save_history=False)
        except Exception:
            import logging as _logging
            _logging.getLogger("services.reminder").warning(
                "group announce failed for reminder %d", reminder_id, exc_info=True,
            )

    if not ctx.lark_table_reminders:
        return base

    try:
        record_id = await lark.with_retry(lambda: lark.sync_reminder_to_lark(
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
        if record_id:
            from src.repositories.reminder_repo import ReminderRepo
            repo = ReminderRepo(await db.get_db())
            await repo.set_lark_record_id(reminder_id, record_id)
        return base
    except Exception:
        import logging as _logging
        _logging.getLogger("services.reminder").warning(
            "Lark sync failed for reminder %d; reconciler will retry", reminder_id,
            exc_info=True,
        )
        return base + " (đang chờ đồng bộ Lark)"


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

    base = f"Da cap nhat nhac nho #{reminder_id}."

    if not ctx.lark_table_reminders:
        return base

    from src.repositories.reminder_repo import ReminderRepo
    repo = ReminderRepo(await db.get_db())
    row = await repo.get_by_id(reminder_id)
    if not row:
        return base

    remind_at_local = remind_at or _utc_naive_stored_to_local_display(row["remind_at"])
    try:
        rec_id = await lark.with_retry(lambda: lark.sync_reminder_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_reminders,
            {
                "content": row["content"],
                "remind_at_local": remind_at_local,
                "target_name": row.get("target_name") or "",
                "status": row["status"],
            },
            reminder_id,
        ))
        if rec_id and not row.get("lark_record_id"):
            await repo.set_lark_record_id(reminder_id, rec_id)
        return base
    except Exception:
        import logging as _logging
        _logging.getLogger("services.reminder").warning(
            "Lark update sync failed for reminder %d", reminder_id, exc_info=True,
        )
        return base + " (đang chờ đồng bộ Lark)"


async def delete_reminder(ctx: ChatContext, reminder_id: int) -> str:
    from src.repositories.reminder_repo import ReminderRepo
    repo = ReminderRepo(await db.get_db())
    row = await repo.get_by_id(reminder_id)
    if not row or str(row.get("boss_chat_id")) != str(ctx.boss_chat_id):
        return f"Khong tim thay nhac nho #{reminder_id}."

    lark_id = row.get("lark_record_id")
    if lark_id and ctx.lark_table_reminders:
        try:
            await lark.with_retry(lambda: lark.delete_record(
                ctx.lark_base_token, ctx.lark_table_reminders, lark_id,
            ))
        except Exception:
            import logging as _logging
            _logging.getLogger("services.reminder").warning(
                "Lark delete failed for reminder %d", reminder_id, exc_info=True,
            )
            return f"Lark dang loi, chua xoa duoc #{reminder_id} — anh thu lai sau."

    ok = await db.delete_reminder(reminder_id, ctx.boss_chat_id)
    if not ok:
        return f"Khong tim thay nhac nho #{reminder_id}."
    return f"Da xoa nhac nho #{reminder_id}."
