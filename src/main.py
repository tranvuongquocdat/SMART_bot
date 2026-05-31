from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.events.bus import InMemoryEventBus
from src.infra.db import create_pool
from src.infra.observability import configure_logging
from src.infra.qdrant import create_qdrant
from src.llm.api_keys import make_api_key_provider
from src.llm.native import NativeGateway
from src.llm.registry import ModelRegistry
from src.repositories.base import BossContext
from src.repositories.feature_budgets import FeatureBudgetsRepo
from src.repositories.llm_routes import LLMRoutesRepo


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.db_pool = await create_pool()
    app.state.qdrant = create_qdrant()
    app.state.bus = InMemoryEventBus()
    app.state.model_registry = ModelRegistry(app.state.db_pool, app.state.bus)
    _admin_ctx = BossContext(boss_id=0, user_role="superadmin")
    app.state.llm_gateway = NativeGateway(
        pool=app.state.db_pool,
        registry=app.state.model_registry,
        llm_routes_repo=LLMRoutesRepo(app.state.db_pool, _admin_ctx),
        feature_budgets_repo=FeatureBudgetsRepo(app.state.db_pool, _admin_ctx),
        api_key_provider=make_api_key_provider(app.state.db_pool),
    )
    yield
    await app.state.db_pool.close()


app = FastAPI(title="SMART_bot", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    db_ok = False
    qdrant_ok = False
    try:
        async with app.state.db_pool.acquire() as c:
            await c.fetchval("SELECT 1")
            db_ok = True
    except Exception:
        pass
    try:
        await app.state.qdrant.get_collections()
        qdrant_ok = True
    except Exception:
        pass
    return {
        "status": "ok",
        "db": "ok" if db_ok else "fail",
        "qdrant": "ok" if qdrant_ok else "fail",
    }
