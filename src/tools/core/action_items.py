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
    items = await repo.list_all(group_id=group_id, status=status)
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
    name="workload_summary",
    description=(
        "Tổng hợp KHỐI LƯỢNG CÔNG VIỆC theo người: mỗi người bao nhiêu việc đang mở / quá hạn / "
        "đã xong + tỷ lệ hoàn thành (by_assignee), KÈM danh sách việc quá hạn cụ thể (overdue_items: "
        "{assignee, what, due}) để nêu ĐÚNG việc nào trễ. Dùng cho 'ai đang quá tải', 'ai nhiều việc "
        "nhất', 'việc NÀO/ai đang trễ hạn', 'tiến độ/hiệu suất team'. group_id=null = TẤT CẢ nhóm; "
        "truyền group_id để xem 1 nhóm/team. Đã xếp người nhiều việc-quá-hạn/đang-mở lên trước."
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "Lọc 1 nhóm/team; null = tổng hợp mọi nhóm của sếp",
            },
        },
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def workload_summary(ctx, group_id: str | None = None) -> ToolResult:
    # Nguồn = SPINE knowledge (item có assignee_name): active=đang làm, resolved=đã xong.
    from src.repositories.knowledge import KnowledgeRepo
    from src.tools.core.search import _scope_group

    group_id = _scope_group(ctx, group_id)
    repo = KnowledgeRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    return ToolResult(content=await repo.workload_summary(chat_id=group_id))


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
