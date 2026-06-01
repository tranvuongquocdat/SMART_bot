"""Action-item tools — list + mark done/cancelled."""

from src.repositories.action_items import ActionItemsRepo
from src.repositories.base import BossContext
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="list_action_items",
    description="Liệt kê việc đang mở (open) / đã xong (done) cross-group hoặc theo nhóm",
    parameters={
        "type": "object",
        "properties": {
            "group_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["open", "done", "cancelled"],
                "default": "open",
            },
        },
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def list_action_items(
    ctx, group_id: str | None = None, status: str = "open"
) -> ToolResult:
    repo = ActionItemsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    items = await repo.list(group_id=group_id, status=status)
    return ToolResult(
        content=[
            {
                "id": i.id,
                "text": i.text,
                "assignee": i.assignee_name,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "status": i.status,
            }
            for i in items
        ]
    )


@tool(
    name="mark_action_item",
    description="Đánh dấu việc done/cancel",
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "integer"},
            "status": {"type": "string", "enum": ["done", "cancelled"]},
        },
        "required": ["item_id", "status"],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=False,
)
async def mark_action_item(ctx, item_id: int, status: str) -> ToolResult:
    repo = ActionItemsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    await repo.update_status(item_id, status)
    return ToolResult(content={"ok": True})
