from collections import defaultdict

from src.retrieval.base import Hit, RetrievalContext, retrieval_stage


@retrieval_stage("rrf", "fuser")
class RRFFuser:
    def __init__(self, k: int = 60):
        self.k = k

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]":
        by_source: dict[str, list[Hit]] = defaultdict(list)
        for h in hits:
            by_source[h.source].append(h)
        for s in by_source.values():
            s.sort(key=lambda x: -x.score)
        scores: dict[int, float] = defaultdict(float)
        for src_hits in by_source.values():
            for rank, h in enumerate(src_hits, 1):
                scores[h.message_id] += 1.0 / (self.k + rank)
        seen: dict[int, Hit] = {}
        for h in hits:
            if h.message_id not in seen:
                seen[h.message_id] = h
        out = [
            Hit(
                message_id=mid,
                score=scores[mid],
                text=seen[mid].text,
                sender=seen[mid].sender,
                ts=seen[mid].ts,
                source="rrf",
            )
            for mid in scores
        ]
        out.sort(key=lambda x: -x.score)
        return out
