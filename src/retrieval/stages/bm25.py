from src.retrieval.base import Hit, RetrievalContext, retrieval_stage


@retrieval_stage("bm25", "source")
class BM25Retriever:
    def __init__(self, pool, k: int = 30):
        self.pool = pool
        self.k = k

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]":
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT id, text, sender_name, ts,
                       ts_rank(fts, plainto_tsquery('simple', unaccent($2))) AS rank
                FROM messages
                WHERE boss_id=$1
                  AND ($3::TEXT IS NULL OR chat_id=$3)
                  AND fts @@ plainto_tsquery('simple', unaccent($2))
                ORDER BY rank DESC
                LIMIT $4
                """,
                ctx.boss_id,
                query,
                ctx.chat_id,
                self.k,
            )
        return [
            Hit(
                message_id=r["id"],
                score=float(r["rank"]),
                text=r["text"],
                sender=r["sender_name"],
                ts=r["ts"].isoformat(),
                source="bm25",
            )
            for r in rows
        ]
