from src.retrieval.base import Hit, RetrievalContext, retrieval_stage


@retrieval_stage("dense", "source")
class DenseRetriever:
    def __init__(self, pool, qdrant, llm_gateway, k: int = 30):
        self.pool = pool
        self.qdrant = qdrant
        self.llm = llm_gateway
        self.k = k

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]":
        [vec] = await self.llm.embed([query], model="text-embedding-3-small")
        must = [
            {"key": "boss_id", "match": {"value": ctx.boss_id}},
            {"key": "kind", "match": {"value": "message"}},
        ]
        if ctx.chat_id:
            must.append({"key": "chat_id", "match": {"value": ctx.chat_id}})
        results = await self.qdrant.search(
            collection_name="smart_bot",
            query_vector=vec,
            query_filter={"must": must},
            limit=self.k,
        )
        msg_ids = [r.payload["message_id"] for r in results]
        if not msg_ids:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT id, text, sender_name, ts FROM messages WHERE id = ANY($1::BIGINT[])",
                msg_ids,
            )
        by_id = {r["id"]: r for r in rows}
        out: list[Hit] = []
        for mid, r in zip(msg_ids, results):
            row = by_id.get(mid)
            if not row:
                continue
            out.append(
                Hit(
                    message_id=mid,
                    score=float(r.score),
                    text=row["text"],
                    sender=row["sender_name"],
                    ts=row["ts"].isoformat(),
                    source="dense",
                )
            )
        return out
