"""
Memory / history search tool. Takes ChatContext as first argument.
"""
from src.context import ChatContext
from src.services import qdrant


async def search_history(ctx: ChatContext, query: str, target_chat_id: int = 0) -> str:
    chat_id = target_chat_id or ctx.chat_id
    results = await qdrant.search(ctx.messages_collection, query, chat_id=chat_id, top_n=5)

    if not results:
        return f"Không tìm thấy lịch sử nào liên quan đến '{query}'."

    lines = [f"Kết quả tìm kiếm cho '{query}':"]
    for r in results:
        lines.append(f"  [{r['role']}]: {r['content']}")

    return "\n".join(lines)
