"""
Note read/write tools. Takes ChatContext as first argument.
"""
import asyncio
from src import db
from src.context import ChatContext


async def _embed_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> None:
    """Async background: embed note to Qdrant notes_{boss_chat_id} collection."""
    try:
        from src.services import qdrant, openai_client
        collection = f"notes_{ctx.boss_chat_id}"
        await qdrant.ensure_collection(collection)
        vector = await openai_client.embed(content)
        point_id = abs(hash(f"note_{ctx.boss_chat_id}_{note_type}_{ref_id}")) % (2 ** 53)
        await qdrant.upsert_note(
            collection=collection,
            point_id=point_id,
            boss_chat_id=ctx.boss_chat_id,
            text=content,
            vector=vector,
            note_type=note_type,
            ref=ref_id,
        )
    except Exception:
        pass  # Qdrant embedding is best-effort


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, content))
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
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, new_content))
    return f"Đã cập nhật note ({note_type}/{ref_id})."
