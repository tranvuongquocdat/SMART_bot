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
