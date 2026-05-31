from decimal import Decimal

from src.domain.model import Model
from src.llm.base import LLMRequest, LLMResponse, LLMUsage
from src.llm.budget import apply_budget
from src.llm.cache_hint import mark_cache_breakpoint
from src.llm.clients.gemini import GeminiClient
from src.llm.clients.openai_compat import OpenAICompatibleClient
from src.llm.routes import pick_model
from src.repositories.base import BossContext
from src.repositories.token_usage import TokenUsageRepo
from src.repositories.users import UsersRepo


def _compute_cost(model: Model, usage: LLMUsage) -> Decimal:
    in_rate = model.cost_per_1m_input_usd or Decimal("0")
    out_rate = model.cost_per_1m_output_usd or Decimal("0")
    cost = (Decimal(usage.tokens_in) * Decimal(in_rate) + Decimal(usage.tokens_out) * Decimal(out_rate)) / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"))


def _compute_cache_savings(model: Model, usage: LLMUsage) -> Decimal:
    if not usage.tokens_cached:
        return Decimal("0")
    in_rate = model.cost_per_1m_input_usd or Decimal("0")
    saved = Decimal(usage.tokens_cached) * Decimal(in_rate) / Decimal("1000000")
    return saved.quantize(Decimal("0.000001"))


class NativeGateway:
    def __init__(
        self,
        pool,
        registry,
        llm_routes_repo,
        feature_budgets_repo,
        api_key_provider,
    ):
        self.pool = pool
        self.registry = registry
        self.routes = llm_routes_repo
        self.budgets = feature_budgets_repo
        self.api_key_provider = api_key_provider

    async def complete(self, req: LLMRequest) -> LLMResponse:
        boss = await UsersRepo(
            self.pool, BossContext(boss_id=req.boss_id, user_role="boss")
        ).get_me()
        if boss is None:
            raise LookupError(f"boss={req.boss_id} not found")
        await apply_budget(req, self.pool)
        mark_cache_breakpoint(req.messages, req.cache_prefix_hint)

        model, route_id = await pick_model(req, boss, self.pool, self.registry)
        client = await self._client_for(model, boss)

        resp = await client.chat(model.name, req)
        if resp.status != "ok":
            fb_resp = await self._try_fallback(req, route_id, boss, model)
            if fb_resp is not None:
                resp = fb_resp

        await TokenUsageRepo(
            self.pool, BossContext(boss_id=boss.id, user_role=boss.role)
        ).insert(
            feature=req.feature,
            operation=req.routing_hints.get("op", "unknown"),
            provider=model.provider,
            model=model.name,
            tokens_in=resp.usage.tokens_in,
            tokens_out=resp.usage.tokens_out,
            tokens_cached=resp.usage.tokens_cached,
            latency_ms=resp.usage.latency_ms,
            cost_usd=_compute_cost(model, resp.usage),
            cost_saved_cache_usd=_compute_cache_savings(model, resp.usage),
            status=resp.status,
            trace_id=req.routing_hints.get("trace_id"),
            span_id=req.routing_hints.get("span_id"),
            gen_ai_system=model.provider,
            gen_ai_request_model=model.name,
            gen_ai_response_model=model.name,
            gen_ai_operation_name="chat",
        )
        return resp

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        from src.config import settings as _settings

        client = OpenAICompatibleClient(
            base_url=None, api_key=_settings.PLATFORM_OPENAI_API_KEY
        )
        return await client.embed(texts, model)

    async def _client_for(self, model: Model, boss):
        key = await self.api_key_provider(boss.id, model.provider)
        if model.endpoint_kind == "openai_compat":
            return OpenAICompatibleClient(model.base_url, key)
        if model.endpoint_kind == "gemini":
            return GeminiClient(key)
        raise ValueError(f"unknown endpoint_kind={model.endpoint_kind}")

    async def _try_fallback(
        self, req: LLMRequest, route_id: int, boss, primary: Model
    ) -> LLMResponse | None:
        route = await self.routes.get(route_id)
        if route is None:
            return None
        last: LLMResponse | None = None
        for fb in route.fallback_chain:
            try:
                tier = fb.get("tier")
                slot_map = {
                    "smart": boss.smart_model_id,
                    "fast": boss.fast_model_id,
                    "vision": boss.vision_model_id,
                }
                mid = slot_map.get(tier)
                if mid is None:
                    m = await self.registry.platform_default(tier)
                else:
                    m = await self.registry.get(mid)
                if m.id == primary.id:
                    continue
                client = await self._client_for(m, boss)
                resp = await client.chat(m.name, req)
                last = resp
                if resp.status == "ok":
                    return resp
            except Exception:
                continue
        return last
