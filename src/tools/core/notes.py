"""Group-note tools — read / refresh / edit + pin / unpin messages."""

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.pins import PinsRepo
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="read_group_note",
    description="Đọc note hiện tại của 1 nhóm",
    parameters={
        "type": "object",
        "properties": {"group_id": {"type": "string"}},
        "required": ["group_id"],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def read_group_note(ctx, group_id: str) -> ToolResult:
    repo = GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    note = await repo.get_by_chat(group_id)
    return ToolResult(
        content={
            "content": note.content if note else "",
            "group_name": note.group_name if note else None,
        }
    )


@tool(
    name="refresh_group_note",
    description="Yêu cầu cập nhật ngay note của 1 nhóm (không đợi debounce)",
    parameters={
        "type": "object",
        "properties": {"group_id": {"type": "string"}},
        "required": ["group_id"],
    },
    available_to={"dm_responder", "in_group_responder"},
    feature="note_update",
    cost_class="high",
    parallel_safe=False,
    timeout_s=60,
)
async def refresh_group_note(ctx, group_id: str) -> ToolResult:
    # Resolve provider via chat_id lookup so NoteUpdater can find the right note.
    repo = GroupNotesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    note = await repo.get_by_chat(group_id)
    provider = note.provider if note else "zalo"
    await ctx.bus.publish(
        "op.note_updater.fire",
        {
            "reason": "on_demand",
            "boss_id": ctx.boss_id,
            "source_event": {
                "boss_id": ctx.boss_id,
                "provider": provider,
                "chat_id": group_id,
            },
        },
    )
    return ToolResult(content={"queued": True})


@tool(
    name="edit_group_note",
    description="Sửa 1 section của note (LLM viết section mới hoặc xoá)",
    parameters={
        "type": "object",
        "properties": {
            "group_id": {"type": "string"},
            "section_key": {"type": "string"},
            "new_content": {"type": "string"},
        },
        "required": ["group_id", "section_key", "new_content"],
    },
    available_to={"dm_responder"},
    parallel_safe=False,
)
async def edit_group_note(
    ctx, group_id: str, section_key: str, new_content: str
) -> ToolResult:
    from src.services.note_service import NoteService

    svc = NoteService(ctx.pool, ctx.bus, ctx.llm)
    await svc.edit_section(
        boss_id=ctx.boss_id,
        chat_id=group_id,
        section_key=section_key,
        new_content=new_content,
        by="llm",
    )
    return ToolResult(content={"ok": True})


@tool(
    name="pin_message",
    description="Ghim 1 tin nhắn vào section 'Đã pin' của note",
    parameters={
        "type": "object",
        "properties": {
            "message_id": {"type": "integer"},
            "note": {"type": "string"},
        },
        "required": ["message_id"],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=False,
)
async def pin_message(
    ctx, message_id: int, note: str | None = None
) -> ToolResult:
    from src.services.note_service import NoteService

    svc = NoteService(ctx.pool, ctx.bus, ctx.llm)
    pin_id = await svc.pin(boss_id=ctx.boss_id, message_id=message_id, note=note)
    return ToolResult(content={"pin_id": pin_id})


@tool(
    name="unpin_message",
    description="Bỏ ghim",
    parameters={
        "type": "object",
        "properties": {"pin_id": {"type": "integer"}},
        "required": ["pin_id"],
    },
    available_to={"dm_responder"},
    parallel_safe=False,
)
async def unpin_message(ctx, pin_id: int) -> ToolResult:
    repo = PinsRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    await repo.delete(pin_id)
    return ToolResult(content={"ok": True})
