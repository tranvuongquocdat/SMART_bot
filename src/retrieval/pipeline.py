import logging
import time

from src.infra.metrics import retrieval_latency
from src.repositories.base import BossContext
from src.repositories.retrieval_pipelines import RetrievalPipelinesRepo
from src.retrieval.base import Hit, RetrievalContext, get_stage_class

log = logging.getLogger(__name__)


class RetrievalPipeline:
    def __init__(self, stages: "list"):
        self.stages = stages

    async def run(self, query: str, ctx: RetrievalContext) -> "list[Hit]":
        hits: list[Hit] = []
        for s in self.stages:
            t0 = time.time()
            hits = await s.run(query, hits, ctx)
            # H2: per-stage latency. Stage name is the registry key (bm25,
            # dense, rrf, mmr, parallel_fanout, …) — bounded cardinality.
            try:
                stage_name = getattr(s, "name", s.__class__.__name__)
                retrieval_latency.labels(stage=stage_name).observe(time.time() - t0)
            except Exception:
                log.exception("metrics: retrieval_latency record failed")
        return hits


def _make_stage(stage_cfg, pool, qdrant, llm_gateway):
    name = stage_cfg["name"]
    args = dict(stage_cfg.get("args", {}))
    cls = get_stage_class(name)
    if name == "bm25":
        return cls(pool, **args)
    if name == "dense":
        return cls(pool, qdrant, llm_gateway, **args)
    if name == "parallel_fanout":
        sources_cfg = args.pop("sources", [])
        sources = [_make_stage(s, pool, qdrant, llm_gateway) for s in sources_cfg]
        return cls(sources=sources, **args)
    return cls(**args)


async def assemble(
    feature: str, pool, qdrant, llm_gateway
) -> RetrievalPipeline:
    admin = BossContext(boss_id=0, user_role="superadmin")
    repo = RetrievalPipelinesRepo(pool, admin)
    cfg = await repo.get(feature)
    if cfg is None:
        raise LookupError(f"no retrieval_pipeline for feature={feature}")
    stages = [_make_stage(s, pool, qdrant, llm_gateway) for s in cfg.stages_json]
    return RetrievalPipeline(stages)
