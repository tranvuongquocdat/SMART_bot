"""
Idea creation tool. Takes ChatContext as first argument.
"""
import asyncio
from src.context import ChatContext
from src.services import lark


async def create_idea(ctx: ChatContext, content: str, tags: str = "", project: str = "") -> str:
    fields: dict = {
        "Nội dung": content,
        "Người tạo": ctx.sender_name,
    }
    if tags:
        fields["Tags"] = tags
    if project:
        fields["Project"] = project

    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_ideas, fields)
    record_id = record.get("record_id", "") if isinstance(record, dict) else ""

    # Embed to notes Qdrant collection for search_notes
    async def _embed():
        try:
            from src.services import qdrant, openai_client
            collection = f"notes_{ctx.boss_chat_id}"
            await qdrant.ensure_collection(collection)
            vector = await openai_client.embed(content)
            point_id = abs(hash(f"idea_{ctx.boss_chat_id}_{record_id or content[:20]}")) % (2 ** 53)
            await qdrant.upsert_note(
                collection=collection,
                point_id=point_id,
                boss_chat_id=ctx.boss_chat_id,
                text=content,
                vector=vector,
                note_type="idea",
                ref=project or tags or "",
            )
        except Exception:
            pass

    asyncio.create_task(_embed())
    return f"Đã lưu ý tưởng: {content}"
