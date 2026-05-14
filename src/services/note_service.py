"""Note read/write tools. Takes ChatContext as first argument."""
import asyncio
import logging
from datetime import datetime, timezone

from src import db
from src.context import ChatContext
from src.infrastructure import lark_client as lark

logger = logging.getLogger("services.note")


async def _embed_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> None:
    """Async background: embed note to Qdrant notes_{boss_chat_id} collection."""
    try:
        from src.infrastructure import qdrant_client as qdrant
        from src.agent.llm_for_ctx import get_llm_for_ctx
        llm = await get_llm_for_ctx(ctx)
        collection = f"notes_{ctx.boss_chat_id}_{llm.embedding_dim}"
        await qdrant.ensure_collection(collection, dim=llm.embedding_dim)
        vector, _ = await llm.embed(content)
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
        logger.warning("Qdrant embed failed for note (%s/%s)", note_type, ref_id, exc_info=True)


async def _sync_note_to_lark(
    ctx: ChatContext, note_type: str, ref_id: str, content: str, sqlite_id: int,
) -> None:
    """Inline-await Lark sync; persist lark_record_id on success.
    On failure: log warning. Reverse-sync reconciler will retry on next pass."""
    if not ctx.lark_table_notes:
        return
    try:
        rec_id = await lark.with_retry(lambda: lark.sync_note_to_lark(
            ctx.lark_base_token,
            ctx.lark_table_notes,
            {
                "type": note_type,
                "ref_id": ref_id,
                "content": content,
                "updated_at": datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
            },
            sqlite_id,
        ))
        if rec_id:
            from src.repositories.note_repo import NoteRepo
            repo = NoteRepo(await db.get_db())
            existing = await repo.get_by_id(sqlite_id)
            if existing and not existing.get("lark_record_id"):
                await repo.set_lark_record_id(sqlite_id, rec_id)
    except Exception:
        logger.warning(
            "Lark sync failed for note (%s/%s); reconciler will retry",
            note_type, ref_id, exc_info=True,
        )


async def update_note(ctx: ChatContext, note_type: str, ref_id: str, content: str) -> str:
    sqlite_id = await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, content))
    await _sync_note_to_lark(ctx, note_type, ref_id, content, sqlite_id)
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
    sqlite_id = await db.update_note(
        boss_chat_id=ctx.boss_chat_id,
        note_type=note_type,
        ref_id=ref_id,
        content=new_content,
    )
    asyncio.create_task(_embed_note(ctx, note_type, ref_id, new_content))
    await _sync_note_to_lark(ctx, note_type, ref_id, new_content, sqlite_id)
    return f"Đã cập nhật note ({note_type}/{ref_id})."
