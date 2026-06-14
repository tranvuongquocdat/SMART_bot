"""Search tools — hybrid retrieval + exact-quote lookup + structured count."""

from datetime import datetime

from src.memory.knowledge_index import KnowledgeIndex
from src.repositories.base import BossContext
from src.repositories.knowledge import KnowledgeRepo
from src.repositories.messages import MessagesRepo
from src.retrieval.base import RetrievalContext
from src.tools.base import ToolResult
from src.tools.registry import tool


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    # Accept "YYYY-MM-DD" or full ISO; fromisoformat handles both since 3.11.
    return datetime.fromisoformat(s)


@tool(
    name="search_history",
    description=(
        "Tìm trong lịch sử chat (hybrid FTS + vector + RRF + MMR), trả top-20. "
        "Có thể lọc theo nhóm, người gửi, khoảng thời gian. "
        "Khi muốn 'tháng trước em A nói gì', truyền with_users=['A'] + after='2026-05-01' + before='2026-06-01'."
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
                "description": "Giới hạn số ngày gần đây (ưu tiên dùng after/before nếu cần khoảng cụ thể)",
            },
            "with_users": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Substring khớp sender_name (ILIKE); vd ['Tuấn Anh', 'Lan']",
            },
            "after": {
                "type": "string",
                "description": "ISO datetime/date — chỉ lấy message từ thời điểm này trở đi",
            },
            "before": {
                "type": "string",
                "description": "ISO datetime/date — chỉ lấy message TRƯỚC thời điểm này",
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
    with_users: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
) -> ToolResult:
    if ctx.retriever_factory is None:
        return ToolResult(content=[], error="retriever_factory not available")
    pipeline = await ctx.retriever_factory("qa_with_search")
    hits = await pipeline.run(
        query,
        RetrievalContext(
            boss_id=ctx.boss_id,
            chat_id=group_id,
            days=days,
            with_users=with_users,
            after=_parse_iso(after),
            before=_parse_iso(before),
        ),
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
    name="count_messages",
    description=(
        "Đếm số message khớp filter — dùng để 'thăm dò' trước khi search_history. "
        "Vd: count_messages(with_users=['Tuấn Anh'], after='2026-05-01') → "
        "thấy 800 thì siết thêm filter, thấy 30 thì gọi search_history với cùng filter."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "FTS query optional"},
            "group_id": {"type": "string"},
            "with_users": {
                "type": "array",
                "items": {"type": "string"},
            },
            "after": {"type": "string", "description": "ISO datetime/date"},
            "before": {"type": "string", "description": "ISO datetime/date"},
        },
        "required": [],
    },
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=5,
)
async def count_messages(
    ctx,
    query: str | None = None,
    group_id: str | None = None,
    with_users: list[str] | None = None,
    after: str | None = None,
    before: str | None = None,
) -> ToolResult:
    repo = MessagesRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    count = await repo.count_filtered(
        query=query,
        chat_id=group_id,
        with_users=with_users,
        after=_parse_iso(after),
        before=_parse_iso(before),
    )
    return ToolResult(content={"count": count})


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


@tool(
    name="search_knowledge",
    description=(
        "Tìm trong KHO TRI THỨC đã chưng cất (decision/fact/note/risk) — DÙNG TRƯỚC "
        "search_history khi câu hỏi về việc đã chốt / thông tin dự án / quyết định. "
        "Hybrid (vector+FTS), scope theo nhóm + thời gian. Trả item kèm source_message_ids "
        "(để dẫn nguồn 'ai nói')."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "group_id": {"type": "string", "description": "Lọc 1 nhóm; null = tất cả nhóm của sếp"},
            "kind": {
                "type": "string",
                "enum": ["decision", "fact", "note", "risk"],
                "description": (
                    "HIẾM khi cần — ĐỂ TRỐNG cho hầu hết câu hỏi (ai phụ trách việc gì, "
                    "deadline, đã chốt gì, rủi ro…). Phân công/ownership thường nằm trong "
                    "'decision' chứ không phải 'fact', nên đừng đoán loại. Chỉ set khi sếp "
                    "yêu cầu rõ đúng MỘT loại tri thức."
                ),
            },
            "after": {"type": "string", "description": "ISO date — tri thức ghi từ thời điểm này"},
            "before": {"type": "string", "description": "ISO date — tri thức ghi trước thời điểm này"},
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
async def search_knowledge(
    ctx,
    query: str,
    group_id: str | None = None,
    kind: str | None = None,
    after: str | None = None,
    before: str | None = None,
) -> ToolResult:
    # Scope mặc định = nhóm hiện tại (khi sếp tag bot trong 1 nhóm, câu hỏi gần như
    # luôn về nhóm đó). Model không truyền group_id → tự lấy chat_id hiện tại nếu đang
    # ở group; muốn nhóm khác thì truyền group_id tường minh. DM/web → None = mọi nhóm.
    if group_id is None and ctx.chat_type == "group" and ctx.chat_id:
        group_id = ctx.chat_id
    repo = KnowledgeRepo(ctx.pool, BossContext(ctx.boss_id, ctx.boss_role))
    index = KnowledgeIndex(ctx.pool, ctx.qdrant, ctx.llm)
    items = await index.search(
        repo, query, boss_id=ctx.boss_id, chat_id=group_id,
        after=_parse_iso(after), before=_parse_iso(before), k=15,
    )
    if kind:
        items = [it for it in items if it.kind == kind]
    out = []
    for it in items[:10]:
        prov = await repo.provenance(it.id)
        out.append(
            {
                "id": it.id,
                "kind": it.kind,
                "title": it.title,
                "content": it.content,
                "importance": it.importance,
                "source_message_ids": prov[:5],
            }
        )
    return ToolResult(content=out)
