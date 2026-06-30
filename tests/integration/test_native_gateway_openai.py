import os

import pytest
import pytest_asyncio

from src.events.bus import InMemoryEventBus
from src.llm.api_keys import make_api_key_provider
from src.llm.base import ChatMessage, LLMRequest
from src.llm.native import NativeGateway
from src.llm.registry import ModelRegistry
from src.repositories.base import BossContext
from src.repositories.feature_budgets import FeatureBudgetsRepo
from src.repositories.llm_routes import LLMRoutesRepo

pytestmark = pytest.mark.skipif(
    not os.getenv("PLATFORM_OPENAI_API_KEY"), reason="no PLATFORM_OPENAI_API_KEY"
)


@pytest_asyncio.fixture
async def seed_openai(boss_user, db_pool):
    async with db_pool.acquire() as c:
        mid = await c.fetchval(
            """
            INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                                capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
                                is_platform_default)
            VALUES ('gpt-4o-mini','openai','openai_compat',NULL,'smart',128000,
                    '["text","vision","tools"]'::jsonb, 0.15, 0.60, TRUE)
            RETURNING id
            """
        )
        await c.execute(
            "UPDATE users SET smart_model_id=$1 WHERE id=$2", mid, boss_user["id"]
        )
        await c.execute(
            """
            INSERT INTO llm_routes (feature, target_tier, fallback_chain, weight)
            VALUES ('dm_general','smart','[]'::jsonb, 100)
            ON CONFLICT DO NOTHING
            """
        )
    yield mid


@pytest.mark.asyncio
async def test_complete_gpt4o_mini(db_pool, boss_user, seed_openai):
    admin = BossContext(boss_id=0, user_role="superadmin")
    bus = InMemoryEventBus()
    registry = ModelRegistry(db_pool, bus)
    gw = NativeGateway(
        pool=db_pool,
        registry=registry,
        llm_routes_repo=LLMRoutesRepo(db_pool, admin),
        feature_budgets_repo=FeatureBudgetsRepo(db_pool, admin),
        api_key_provider=make_api_key_provider(db_pool),
    )
    req = LLMRequest(
        feature="dm_general",
        boss_id=boss_user["id"],
        messages=[
            ChatMessage(
                role="user",
                content="Reply with just the word 'hi' and nothing else.",
            )
        ],
        max_output_tokens=16,
    )
    resp = await gw.complete(req)
    assert resp.status == "ok"
    assert resp.content is not None
    assert "hi" in resp.content.lower()
    assert resp.usage.tokens_in > 0
