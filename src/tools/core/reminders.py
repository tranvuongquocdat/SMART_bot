"""Reminder tools — set / list / cancel."""

from datetime import datetime

from src.repositories.base import BossContext
from src.repositories.reminders import RemindersRepo
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="set_reminder",
    description=(
        "Đặt 1 nhắc. Truyền `due_at_iso` ISO 8601 (TZ sếp). "
        "scope=group|dm; target_chat_id null → current chat. "
        "recurring='daily' | 'weekly:mon,wed,fri' | null."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Nội dung nhắc, vd 'nộp báo cáo Q2'",
            },
            "due_at_iso": {
                "type": "string",
                "description": "Thời điểm ISO 8601 (TZ sếp)",
            },
            "scope": {"type": "string", "enum": ["group", "dm"]},
            "target_chat_id": {
                "type": "string",
                "description": "Group ID nếu scope=group; null thì lấy current context",
            },
            "recurring": {
                "type": "string",
                "description": "daily | weekly:mon,wed,fri | null",
            },
        },
        "required": ["text", "due_at_iso", "scope"],
    },
    feature="reminder_parse",
    cost_class="low",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=False,
)
async def set_reminder(
    ctx,
    text: str,
    due_at_iso: str,
    scope: str,
    target_chat_id: str | None = None,
    recurring: str | None = None,
) -> ToolResult:
    from src.services.reminder_service import ReminderService

    svc = ReminderService(ctx.pool, ctx.bus)
    rid = await svc.create(
        boss_id=ctx.boss_id,
        text=text,
        due_at=datetime.fromisoformat(due_at_iso),
        scope=scope,
        chat_id=target_chat_id,
        recurring=recurring,
        created_by_op=getattr(ctx, "op_name", "unknown"),
    )
    return ToolResult(content={"reminder_id": rid})


@tool(
    name="list_reminders",
    description="Liệt kê reminder của sếp",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "fired", "cancelled", "failed"],
                "default": "pending",
            },
            "group_id": {"type": "string"},
        },
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def list_reminders(
    ctx, status: str = "pending", group_id: str | None = None
) -> ToolResult:
    repo = RemindersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    items = await repo.list_all(status=status, chat_id=group_id)
    return ToolResult(
        content=[
            {
                "id": r.id,
                "text": r.text,
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "scope": r.scope,
                "chat_id": r.chat_id,
                "recurring": r.recurring,
            }
            for r in items
        ]
    )


@tool(
    name="cancel_reminder",
    description="Huỷ 1 reminder pending",
    parameters={
        "type": "object",
        "properties": {"reminder_id": {"type": "integer"}},
        "required": ["reminder_id"],
    },
    available_to={"dm_responder"},
    parallel_safe=False,
)
async def cancel_reminder(ctx, reminder_id: int) -> ToolResult:
    repo = RemindersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    await repo.cancel(reminder_id)
    return ToolResult(content={"ok": True})
