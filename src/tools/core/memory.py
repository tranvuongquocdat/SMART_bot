"""Memory tools — remember (semantic key/value) + forget."""

from src.domain.memory import MemoryScope
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="remember",
    description=(
        "Lưu thông tin về sếp/người xung quanh để nhớ cho lần sau. "
        "Vd: remember('preferred_name','Đạt'), "
        "remember('alias:anh Tân', 'Nguyễn Văn Tân — sale lead')"
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Khóa ngữ nghĩa, vd 'preferred_name' hoặc 'alias:Tân'",
            },
            "value": {"type": "string", "description": "Giá trị cần nhớ"},
        },
        "required": ["key", "value"],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=False,
)
async def remember(ctx, key: str, value: str) -> ToolResult:
    m = await ctx.memory.write(
        MemoryScope.SEMANTIC,
        content=value,
        boss_id=ctx.boss_id,
        key=key,
    )
    return ToolResult(content={"memory_id": m.id, "key": key})


@tool(
    name="forget",
    description="Xoá entry memory đã nhớ trước đó",
    parameters={
        "type": "object",
        "properties": {"memory_id": {"type": "integer"}},
        "required": ["memory_id"],
    },
    available_to={"dm_responder"},
    parallel_safe=False,
)
async def forget(ctx, memory_id: int) -> ToolResult:
    await ctx.memory.forget(memory_id, ctx.boss_id)
    return ToolResult(content={"ok": True})
