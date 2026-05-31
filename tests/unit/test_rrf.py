import pytest

import src.retrieval  # noqa: F401 — register stages
from src.retrieval.base import Hit, RetrievalContext
from src.retrieval.stages.rrf import RRFFuser


def _h(mid, score, source, text="x"):
    return Hit(message_id=mid, score=score, text=text, sender=None, ts="2026-01-01", source=source)


@pytest.mark.asyncio
async def test_rrf_combines_two_sources():
    fuser = RRFFuser(k=60)
    hits = [
        _h(1, 0.9, "bm25"),
        _h(2, 0.5, "bm25"),
        _h(3, 0.1, "bm25"),
        _h(1, 0.8, "dense"),
        _h(4, 0.7, "dense"),
        _h(2, 0.2, "dense"),
    ]
    ctx = RetrievalContext(boss_id=1)
    out = await fuser.run("q", hits, ctx)
    # Message 1 appears top in both → must rank first overall.
    assert out[0].message_id == 1
    assert out[0].source == "rrf"
    ranked_ids = [h.message_id for h in out]
    assert set(ranked_ids) == {1, 2, 3, 4}


@pytest.mark.asyncio
async def test_rrf_empty_input():
    out = await RRFFuser().run("q", [], RetrievalContext(boss_id=1))
    assert out == []
