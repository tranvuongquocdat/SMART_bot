"""Search tools — hybrid retrieval + exact-quote lookup."""

from src.repositories.base import BossContext
from src.repositories.messages import MessagesRepo
from src.retrieval.base import RetrievalContext
from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="search_history",
    description=(
        "Tìm trong lịch sử chat, hybrid (FTS + vector + RRF + MMR). "
        "Trả top-20 đoạn liên quan nhất."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "group_id": {
                "type": "string",
                "description": "Lọc theo 1 nhóm; null = tất cả nhóm",
            },
            "days": {
                "type": "integer",
                "description": "Giới hạn số ngày gần đây",
            },
        },
        "required": ["query"],
    },
    feature="qa_with_search",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    rate_limit="search:{boss_id}:30/min",
    parallel_safe=True,
    timeout_s=15,
)
async def search_history(
    ctx,
    query: str,
    group_id: str | None = None,
    days: int | None = None,
) -> ToolResult:
    if ctx.retriever_factory is None:
        return ToolResult(content=[], error="retriever_factory not available")
    pipeline = await ctx.retriever_factory("qa_with_search")
    hits = await pipeline.run(
        query,
        RetrievalContext(boss_id=ctx.boss_id, chat_id=group_id, days=days),
    )
    return ToolResult(
        content=[
            {
                "message_id": h.message_id,
                "score": h.score,
                "text": h.text,
                "sender": h.sender,
                "ts": h.ts,
            }
            for h in hits[:20]
        ]
    )


@tool(
    name="find_exact_quote",
    description=(
        "Tìm chính xác câu trích từ lịch sử (FTS exact). "
        "Trả author + ts + context ±3 message."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fragment": {"type": "string"},
            "group_id": {"type": "string"},
        },
        "required": ["fragment"],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def find_exact_quote(
    ctx,
    fragment: str,
    group_id: str | None = None,
) -> ToolResult:
    repo = MessagesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    matches = await repo.fts_exact(fragment, group_id, limit=5)
    out = []
    for m in matches:
        before, after = await repo.context_around(m.id, n=3)
        out.append(
            {
                "message_id": m.id,
                "author": m.sender_name,
                "ts": m.ts.isoformat() if m.ts else None,
                "full_text": m.text,
                "context_before": [b.text for b in before],
                "context_after": [a.text for a in after],
            }
        )
    return ToolResult(content=out)
