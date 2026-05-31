import pytest

import src.retrieval  # noqa: F401
from src.retrieval.base import Hit, RetrievalContext
from src.retrieval.stages.mmr import MMRDeduper


def _h(mid, score, text):
    return Hit(message_id=mid, score=score, text=text, sender=None, ts="2026-01-01", source="rrf")


@pytest.mark.asyncio
async def test_mmr_prefers_diversity():
    near_dups = [
        _h(1, 0.9, "alpha beta gamma"),
        _h(2, 0.85, "alpha beta gamma delta"),
        _h(3, 0.84, "alpha beta gamma epsilon"),
    ]
    diverse = _h(4, 0.7, "totally different vocabulary words")
    deduper = MMRDeduper(lambda_=0.3, k_out=2)
    out = await deduper.run("q", near_dups + [diverse], RetrievalContext(boss_id=1))
    ids = [h.message_id for h in out]
    assert ids[0] == 1
    # With low lambda (favor diversity) the second pick should be the diverse hit.
    assert ids[1] == 4


@pytest.mark.asyncio
async def test_mmr_respects_k_out():
    hits = [_h(i, 1.0 - 0.1 * i, f"text {i}") for i in range(10)]
    deduper = MMRDeduper(lambda_=0.5, k_out=3)
    out = await deduper.run("q", hits, RetrievalContext(boss_id=1))
    assert len(out) == 3


@pytest.mark.asyncio
async def test_mmr_empty():
    out = await MMRDeduper().run("q", [], RetrievalContext(boss_id=1))
    assert out == []
