from src.retrieval.base import Hit, RetrievalContext, retrieval_stage


@retrieval_stage("mmr", "dedupe")
class MMRDeduper:
    def __init__(self, lambda_: float = 0.5, k_out: int = 20):
        self.lambda_ = lambda_
        self.k_out = k_out

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]":
        def sim(a: Hit, b: Hit) -> float:
            ta = set(a.text.lower().split())
            tb = set(b.text.lower().split())
            union = ta | tb
            return len(ta & tb) / max(len(union), 1)

        selected: list[Hit] = []
        remaining = list(hits)
        while remaining and len(selected) < self.k_out:
            if not selected:
                best = remaining.pop(0)
            else:
                def mmr_score(h: Hit) -> float:
                    max_sim = max((sim(h, s) for s in selected), default=0.0)
                    return self.lambda_ * h.score - (1 - self.lambda_) * max_sim

                remaining.sort(key=lambda h: -mmr_score(h))
                best = remaining.pop(0)
            selected.append(best)
        return selected
