import pytest

from src.domain.boss import Boss
from src.domain.model import LLMRoute, Model
from src.llm.base import LLMRequest
from src.llm.routes import _eval_condition, pick_model


def _boss(smart=10, fast=20, vision=None, plan="free"):
    return Boss(
        id=1,
        email="boss@x",
        name="boss",
        role="boss",
        tz="UTC",
        language="vi",
        smart_model_id=smart,
        fast_model_id=fast,
        vision_model_id=vision,
        subscription_status=plan,
        subscription_expiry=None,
        cost_cap_usd_daily=5.0,
    )


def _model(mid: int, tier: str, caps=None, name=None) -> Model:
    return Model(
        id=mid,
        name=name or f"model-{mid}",
        provider="openai",
        endpoint_kind="openai_compat",
        base_url=None,
        tier=tier,
        ctx_max=128000,
        capabilities=caps or [],
    )


class _Registry:
    def __init__(self, models, defaults=None):
        self._m = {m.id: m for m in models}
        self._defaults = defaults or {}

    async def get(self, mid):
        return self._m[mid]

    async def platform_default(self, tier):
        if tier in self._defaults:
            return self._defaults[tier]
        for m in self._m.values():
            if m.tier == tier and m.is_platform_default:
                return m
        raise LookupError(tier)


class _Pool:
    pass


def test_eval_condition_empty_true():
    assert _eval_condition(None, _boss()) is True
    assert _eval_condition("", _boss()) is True


def test_eval_condition_premium_match():
    boss = _boss(plan="premium")
    assert _eval_condition("boss.subscription_status == 'premium'", boss) is True
    assert _eval_condition("boss.subscription_status == 'free'", boss) is False


def test_eval_condition_unsafe_returns_false():
    # Builtins are stripped, so this should be treated as not-matching.
    assert _eval_condition("__import__('os')", _boss()) is False


@pytest.mark.asyncio
async def test_pick_model_uses_boss_slot(monkeypatch):
    smart = _model(10, "smart")
    fast = _model(20, "fast")
    registry = _Registry([smart, fast])
    boss = _boss()

    class _Routes:
        def __init__(self, *_a, **_kw):
            pass

        async def list_active_for_feature(self, feature):
            return [
                LLMRoute(
                    id=99,
                    feature=feature,
                    condition_cel=None,
                    target_tier="smart",
                    fallback_chain=[],
                    weight=100,
                    is_active=True,
                    notes=None,
                    updated_at=None,
                )
            ]

    monkeypatch.setattr("src.llm.routes.LLMRoutesRepo", _Routes)
    req = LLMRequest(feature="dm_general", boss_id=1, messages=[])
    model, route_id = await pick_model(req, boss, _Pool(), registry)
    assert model.id == 10
    assert route_id == 99


@pytest.mark.asyncio
async def test_pick_model_vision_falls_back_to_smart_with_vision_cap(monkeypatch):
    smart = _model(10, "smart", caps=["vision"])
    fast = _model(20, "fast")
    registry = _Registry([smart, fast])
    boss = _boss(vision=None)

    class _Routes:
        def __init__(self, *_a, **_kw):
            pass

        async def list_active_for_feature(self, feature):
            return [
                LLMRoute(
                    id=7,
                    feature=feature,
                    condition_cel=None,
                    target_tier="vision",
                    fallback_chain=[],
                    weight=100,
                    is_active=True,
                    notes=None,
                    updated_at=None,
                )
            ]

    monkeypatch.setattr("src.llm.routes.LLMRoutesRepo", _Routes)
    req = LLMRequest(feature="image_oneshot", boss_id=1, messages=[])
    model, _ = await pick_model(req, boss, _Pool(), registry)
    assert model.id == 10


@pytest.mark.asyncio
async def test_pick_model_required_caps_falls_across_slots(monkeypatch):
    smart = _model(10, "smart", caps=["text"])
    vision = _model(30, "vision", caps=["vision", "text"])
    fast = _model(20, "fast", caps=["text"])
    registry = _Registry([smart, fast, vision])
    boss = _boss(smart=10, fast=20, vision=30)

    class _Routes:
        def __init__(self, *_a, **_kw):
            pass

        async def list_active_for_feature(self, feature):
            return [
                LLMRoute(
                    id=42,
                    feature=feature,
                    condition_cel=None,
                    target_tier="smart",
                    fallback_chain=[],
                    weight=100,
                    is_active=True,
                    notes=None,
                    updated_at=None,
                )
            ]

    monkeypatch.setattr("src.llm.routes.LLMRoutesRepo", _Routes)
    req = LLMRequest(
        feature="dm_general",
        boss_id=1,
        messages=[],
        required_caps={"vision"},
    )
    model, _ = await pick_model(req, boss, _Pool(), registry)
    assert model.id == 30
