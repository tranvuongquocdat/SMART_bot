from src.domain.boss import Boss
from src.domain.model import LLMRoute, Model
from src.llm.base import LLMRequest
from src.repositories.base import BossContext
from src.repositories.llm_routes import LLMRoutesRepo


def _eval_condition(condition_cel: str | None, boss: Boss) -> bool:
    """MVP: restricted eval for boss.<attr> == 'value' style expressions.

    Returns True when condition is None/empty. Returns False on any error.
    """
    if not condition_cel:
        return True
    safe_globals = {"__builtins__": {}}
    try:
        return bool(eval(condition_cel, safe_globals, {"boss": boss}))
    except Exception:
        return False


async def _match_route(repo: LLMRoutesRepo, feature: str, boss: Boss) -> LLMRoute:
    routes = await repo.list_active_for_feature(feature)
    if not routes:
        raise LookupError(f"no llm_route for feature={feature}")
    for r in routes:
        if _eval_condition(r.condition_cel, boss):
            return r
    return routes[0]


async def pick_model(
    req: LLMRequest, boss: Boss, pool, registry
) -> tuple[Model, int]:
    """Return (model, route_id).

    Resolves tier → boss slot → registry; applies vision-fallback-to-smart
    and capability fallback across slots.
    """
    repo = LLMRoutesRepo(pool, BossContext(boss_id=boss.id, user_role=boss.role))
    route = await _match_route(repo, req.feature, boss)
    slot_map = {
        "smart": boss.smart_model_id,
        "fast": boss.fast_model_id,
        "vision": boss.vision_model_id,
    }
    chosen_id = slot_map.get(route.target_tier)
    if chosen_id is None:
        if route.target_tier == "vision" and boss.smart_model_id:
            sm = await registry.get(boss.smart_model_id)
            if "vision" in sm.capabilities:
                return sm, route.id
        chosen_id = (await registry.platform_default(route.target_tier)).id
    m = await registry.get(chosen_id)
    missing = req.required_caps - set(m.capabilities)
    if missing:
        for slot_id in [boss.vision_model_id, boss.smart_model_id, boss.fast_model_id]:
            if slot_id:
                alt = await registry.get(slot_id)
                if not (req.required_caps - set(alt.capabilities)):
                    return alt, route.id
        raise LookupError(f"no model with required caps={missing}")
    return m, route.id
