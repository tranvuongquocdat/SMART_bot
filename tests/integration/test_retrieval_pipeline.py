import os

import pytest
import pytest_asyncio

import src.retrieval  # noqa: F401
from src.events.bus import InMemoryEventBus
from src.infra.qdrant import create_qdrant
from src.llm.api_keys import make_api_key_provider
from src.llm.native import NativeGateway
from src.llm.registry import ModelRegistry
from src.memory.internal import ensure_collection
from src.repositories.base import BossContext
from src.repositories.feature_budgets import FeatureBudgetsRepo
from src.repositories.llm_routes import LLMRoutesRepo
from src.repositories.retrieval_pipelines import RetrievalPipelinesRepo
from src.retrieval.base import RetrievalContext
from src.retrieval.pipeline import assemble

pytestmark = pytest.mark.skipif(
    not os.getenv("PLATFORM_OPENAI_API_KEY"), reason="no PLATFORM_OPENAI_API_KEY"
)


@pytest_asyncio.fixture
async def qdrant():
    client = create_qdrant()
    await ensure_collection(client)
    yield client


@pytest_asyncio.fixture
async def gateway(db_pool, boss_user):
    admin = BossContext(boss_id=0, user_role="superadmin")
    async with db_pool.acquire() as c:
        mid = await c.fetchval(
            """
            INSERT INTO models (name, provider, endpoint_kind, base_url, tier, ctx_max,
                                capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
                                is_platform_default)
            VALUES ('gpt-4o-mini','openai','openai_compat',NULL,'smart',128000,
                    '["text"]'::jsonb, 0.15, 0.60, TRUE)
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        )
        if mid:
            await c.execute(
                "UPDATE users SET smart_model_id=$1 WHERE id=$2",
                mid,
                boss_user["id"],
            )
    bus = InMemoryEventBus()
    registry = ModelRegistry(db_pool, bus)
    yield NativeGateway(
        pool=db_pool,
        registry=registry,
        llm_routes_repo=LLMRoutesRepo(db_pool, admin),
        feature_budgets_repo=FeatureBudgetsRepo(db_pool, admin),
        api_key_provider=make_api_key_provider(db_pool),
    )


@pytest.mark.asyncio
async def test_pipeline_assemble_bm25_only(db_pool, qdrant, gateway, boss_user):
    admin = BossContext(boss_id=0, user_role="superadmin")
    repo = RetrievalPipelinesRepo(db_pool, admin)
    await repo.upsert(
        feature="dm_general",
        stages=[{"name": "bm25", "args": {"k": 10}}],
        description="bm25 only",
    )
    # Insert a couple of messages.
    async with db_pool.acquire() as c:
        for text in [
            "meeting with anh Tan next monday",
            "review the Q3 sales pipeline",
            "lunch with the team",
        ]:
            await c.execute(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type, message_external_id,
                                      sender_external_id, sender_name, sender_is_boss,
                                      mentions_bot, text, ts)
                VALUES ($1,'zalo','c1','dm','m'||extract(epoch from now())::TEXT,
                        's1','Tan',FALSE,FALSE,$2,NOW())
                """,
                boss_user["id"],
                text,
            )
    pipeline = await assemble("dm_general", db_pool, qdrant, gateway)
    out = await pipeline.run("Tan", RetrievalContext(boss_id=boss_user["id"]))
    assert len(out) >= 1
    assert any("Tan" in h.text for h in out)
