"""
Search tools — semantic search for notes/ideas and message history.
"""
from src.context import ChatContext
from src.infrastructure import qdrant_client as qdrant
from src.agent_pkg.llm_for_ctx import get_llm_for_ctx


async def search_notes(
    ctx: ChatContext,
    query: str,
    note_type: str = "all",
    workspace_ids: str = "current",
) -> str:
    """
    Semantic search across notes and ideas.
    note_type: "personal" | "group" | "project" | "idea" | "all"
    Notes and ideas are embedded on write — Qdrant collection: notes_{boss_chat_id}_{dim}
    """
    llm = await get_llm_for_ctx(ctx)
    collection = f"notes_{ctx.boss_chat_id}_{llm.embedding_dim}"
    await qdrant.ensure_collection(collection, dim=llm.embedding_dim)

    query_vector, _ = await llm.embed(query)
    results = await qdrant.search(
        collection, query, chat_id=None, top_n=8, query_vector=query_vector,
    )

    if note_type != "all":
        results = [r for r in results if r.get("type", "") == note_type]

    if not results:
        return f"Không tìm thấy ghi chú nào liên quan đến '{query}'."

    lines = [f"Kết quả tìm kiếm ghi chú cho '{query}' ({len(results)} kết quả):"]
    for r in results:
        snippet = r.get("content", "")[:120]
        ref = r.get("ref", "")
        ntype = r.get("type", "")
        label = f"[{ntype}]" + (f" {ref}" if ref else "")
        lines.append(f"  {label}: {snippet}...")
    return "\n".join(lines)


async def search_history(
    ctx: ChatContext,
    query: str,
    scope: str = "current_chat",
    workspace_ids: str = "current",
) -> str:
    """
    Semantic search in message history.
    scope: "current_chat" (default) | "all" (searches all chats belonging to this workspace)
    """
    llm = await get_llm_for_ctx(ctx)
    collection = ctx.messages_collection
    await qdrant.ensure_collection(collection, dim=llm.embedding_dim)

    chat_id_filter = ctx.chat_id if scope == "current_chat" else None
    query_vector, _ = await llm.embed(query)
    results = await qdrant.search(
        collection, query, chat_id=chat_id_filter, top_n=10, query_vector=query_vector,
    )

    if not results:
        return f"Không tìm thấy lịch sử liên quan đến '{query}'."

    lines = [f"Lịch sử liên quan đến '{query}' ({len(results)} kết quả):"]
    for r in results:
        role = r.get("role", "")
        content = r.get("content", "")[:120]
        lines.append(f"  [{role}]: {content}")
    return "\n".join(lines)
