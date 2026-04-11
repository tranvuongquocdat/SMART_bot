from src.services import qdrant


async def search_history(query: str, chat_id: int) -> str:
    results = await qdrant.search(query, chat_id, top_n=5)

    if not results:
        return f"Không tìm thấy lịch sử nào liên quan đến '{query}'."

    lines = [f"Kết quả tìm kiếm cho '{query}':"]
    for r in results:
        lines.append(f"  [{r['role']}]: {r['content']}")

    return "\n".join(lines)
