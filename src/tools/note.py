"""
Note read/write tools. Takes ChatContext as first argument.
"""
from src import db
from src.context import ChatContext


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=content,
    )
    return f"Đã cập nhật note ({note_type}/{ref_id})."


async def get_note(ctx: ChatContext, note_type: str, ref_id: str) -> str:
    note = await db.get_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
    )
    if note is None:
        return ""
    return note.get("content", "")


async def append_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    """Appends content to an existing note without overwriting. Creates if not exists."""
    existing = await db.get_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
    )
    if existing and existing.get("content"):
        new_content = existing["content"] + "\n\n" + content
    else:
        new_content = content
    await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=new_content,
    )
    return f"Đã cập nhật note ({note_type}/{ref_id})."
