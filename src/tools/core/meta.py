"""Meta tools — list_groups, current_time."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.users import UsersRepo
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="list_groups",
    description="Liệt kê các nhóm sếp đã link",
    parameters={"type": "object", "properties": {}},
    available_to={"dm_responder"},
    parallel_safe=True,
)
async def list_groups(ctx) -> ToolResult:
    repo = GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    notes = await repo.list_all()
    return ToolResult(
        content=[
            {
                "chat_id": n.chat_id,
                "group_name": n.group_name,
                "provider": n.provider,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            }
            for n in notes
        ]
    )


@tool(
    name="list_members",
    description=(
        "Roster: liệt kê TẤT CẢ thành viên trong nhóm/team (tên + vai trò + các nhóm họ tham gia). "
        "Dùng khi cần biết team gồm ĐỦ những ai, hoặc KẾT HỢP với workload_summary để suy 'ai đang "
        "rảnh' = người có trong roster nhưng KHÔNG có việc đang mở. group_id=null = mọi nhóm của sếp; "
        "truyền group_id để xem 1 nhóm/team cụ thể."
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "Lọc 1 nhóm/team; null = roster gộp mọi nhóm của sếp",
            },
        },
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def list_members(ctx, group_id: str | None = None) -> ToolResult:
    from src.tools.core.search import _scope_group

    group_id = _scope_group(ctx, group_id)
    repo = GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    return ToolResult(content=await repo.list_members(chat_id=group_id))


@tool(
    name="current_time",
    description="Thời gian hiện tại theo TZ của sếp",
    parameters={"type": "object", "properties": {}},
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def current_time(ctx) -> ToolResult:
    repo = UsersRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    boss = await repo.get_me()
    tz = boss.tz if boss and boss.tz else "Asia/Ho_Chi_Minh"
    now = datetime.now(ZoneInfo(tz))
    return ToolResult(content={"iso": now.isoformat(), "tz": tz})
