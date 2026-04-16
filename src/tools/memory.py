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


async def list_pending_approvals(ctx: ChatContext) -> str:
    """Lists all pending approvals for the boss: task change requests + join requests."""
    import json
    from src import db

    lines = []

    # Pending task approvals
    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending' ORDER BY created_at",
        (str(ctx.boss_chat_id),),
    ) as cur:
        task_approvals = [dict(r) for r in await cur.fetchall()]

    for a in task_approvals:
        payload = json.loads(a["payload"]) if isinstance(a["payload"], str) else a["payload"]
        task_name = payload.get("task_name", "unknown task")
        changes = payload.get("changes", {})
        changes_str = ", ".join(f"{k}→{v}" for k, v in changes.items())
        lines.append(
            f"[task_approval id={a['id']}] '{task_name}': {changes_str} "
            f"(requested by user {a['requester_id']})"
        )

    # Pending join requests
    async with _db.execute(
        "SELECT * FROM memberships WHERE boss_chat_id = ? AND status = 'pending' ORDER BY requested_at",
        (str(ctx.boss_chat_id),),
    ) as cur:
        join_requests = [dict(r) for r in await cur.fetchall()]

    for j in join_requests:
        lines.append(
            f"[join_request chat_id={j['chat_id']}] {j['name'] or 'Unknown'} "
            f"wants to join as {j['person_type']}. Info: {j.get('request_info', '')}"
        )

    if not lines:
        return "No pending approvals."
    return "Pending approvals:\n" + "\n".join(lines)
