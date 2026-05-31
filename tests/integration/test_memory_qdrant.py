import os

import pytest
import pytest_asyncio

from src.domain.memory import MemoryScope
from src.events.bus import InMemoryEventBus
from src.infra.qdrant import create_qdrant
from src.llm.api_keys import make_api_key_provider
from src.llm.native import NativeGateway
from src.llm.registry import ModelRegistry
from src.memory.internal import InternalMemoryProvider, ensure_collection
from src.repositories.base import BossContext
from src.repositories.feature_budgets import FeatureBudgetsRepo
from src.repositories.llm_routes import LLMRoutesRepo

pytestmark = pytest.mark.skipif(
    not os.getenv("PLATFORM_OPENAI_API_KEY"), reason="no PLATFORM_OPENAI_API_KEY"
)


@pytest_asyncio.fixture
async def qdrant():
    client = create_qdrant()
    await ensure_collection(client)
    yield client


@pytest_asyncio.fixture
async def memory_provider(db_pool, qdrant, boss_user):
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
    yield InternalMemoryProvider(pool=db_pool, qdrant=qdrant, llm_gateway=gw)


@pytest.mark.asyncio
async def test_write_recall_semantic_by_key(memory_provider, boss_user):
    m = await memory_provider.write(
        MemoryScope.SEMANTIC,
        content="Nguyen Van Tan — sales lead from Q3 deal",
        boss_id=boss_user["id"],
        key="alias:anh Tan",
    )
    assert m.key == "alias:anh Tan"
    found = await memory_provider.recall(
        MemoryScope.SEMANTIC,
        "Who is Tan?",
        boss_user["id"],
        k=3,
    )
    assert any("Tan" in x.content for x in found)
