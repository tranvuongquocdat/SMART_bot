import asyncio

from src.retrieval.base import Hit, RetrievalContext, retrieval_stage


@retrieval_stage("parallel_fanout", "combinator")
class ParallelFanout:
    def __init__(self, sources: "list", k_each: int = 30):
        self.sources = sources
        self.k_each = k_each

    async def run(
        self, query: str, hits: "list[Hit]", ctx: RetrievalContext
    ) -> "list[Hit]":
        results = await asyncio.gather(*(s.run(query, [], ctx) for s in self.sources))
        merged: list[Hit] = []
        for arr in results:
            merged.extend(arr)
        return merged
