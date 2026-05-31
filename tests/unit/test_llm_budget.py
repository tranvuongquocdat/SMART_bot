import pytest

from src.domain.model import FeatureBudget
from src.llm.base import ChatMessage, LLMRequest
from src.llm.budget import apply_budget


class _FakeBudgetsRepo:
    def __init__(self, budget):
        self._b = budget

    async def get(self, feature):
        return self._b


@pytest.fixture
def patch_repo(monkeypatch):
    def _patch(budget):
        import src.llm.budget as mod

        class _Stub:
            def __init__(self, *_args, **_kw):
                pass

            async def get(self, _feature):
                return budget

        monkeypatch.setattr(mod, "FeatureBudgetsRepo", _Stub)

    return _patch


@pytest.mark.asyncio
async def test_applies_max_output_when_missing(patch_repo):
    budget = FeatureBudget(
        feature="dm_general",
        max_input_tokens=100000,
        max_output_tokens=512,
        trim_policy_json=[],
        compression_strategy="none",
        cache_prefix_hint=None,
        updated_at=None,
    )
    patch_repo(budget)
    req = LLMRequest(
        feature="dm_general",
        boss_id=1,
        messages=[ChatMessage(role="user", content="hi")],
    )
    out = await apply_budget(req, pool=None)
    assert out.max_output_tokens == 512


@pytest.mark.asyncio
async def test_drops_oldest_delta_when_over_budget(patch_repo):
    budget = FeatureBudget(
        feature="dm_general",
        max_input_tokens=10,
        max_output_tokens=128,
        trim_policy_json=["drop_oldest_delta"],
        compression_strategy="none",
        cache_prefix_hint=None,
        updated_at=None,
    )
    patch_repo(budget)
    big = "word " * 200
    req = LLMRequest(
        feature="dm_general",
        boss_id=1,
        messages=[
            ChatMessage(role="system", content="rules"),
            ChatMessage(role="user", content="oldest"),
            ChatMessage(role="user", content=big),
            ChatMessage(role="user", content="latest"),
        ],
    )
    before = len(req.messages)
    out = await apply_budget(req, pool=None)
    assert len(out.messages) < before


@pytest.mark.asyncio
async def test_no_budget_returns_unchanged(patch_repo):
    patch_repo(None)
    req = LLMRequest(
        feature="dm_general",
        boss_id=1,
        messages=[ChatMessage(role="user", content="hi")],
    )
    out = await apply_budget(req, pool=None)
    assert out.max_output_tokens is None
