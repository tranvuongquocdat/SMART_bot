from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import src.agents  # force import all op modules at startup
from src.agents.dispatcher import OperationDispatcher
from src.agents.triggers import TriggerEngine
from src.channels.zalo import normalizer as zalo_normalizer
from src.channels.zalo import outbound as zalo_outbound
from src.channels.zalo.adapter import ZaloAdapter
from src.config import settings
from src.events.bus import InMemoryEventBus
from src.infra.db import create_pool
from src.infra.observability import configure_logging
from src.infra.qdrant import create_qdrant
from src.llm.api_keys import make_api_key_provider
from src.llm.native import NativeGateway
from src.llm.registry import ModelRegistry
from src.memory.internal import InternalMemoryProvider, ensure_collection
from src.repositories.base import BossContext
from src.repositories.bot_accounts import BotAccountsRepo, _row_to_bot_account
from src.repositories.feature_budgets import FeatureBudgetsRepo
from src.repositories.llm_routes import LLMRoutesRepo
from src.plugins_loader import load_all as load_plugins
from src.scheduler import make_scheduler
from src.security.rate_limit import InMemoryRateLimiter
from src.web.routes import admin as web_admin
from src.web.routes import api as web_api
from src.web.routes import api_ai as web_api_ai
from src.web.routes import app as web_app
from src.web.routes import auth as web_auth
from src.web.routes import oauth as web_oauth
from src.web.security import csrf_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.db_pool = await create_pool()
    app.state.qdrant = create_qdrant()
    app.state.bus = InMemoryEventBus()
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.model_registry = ModelRegistry(app.state.db_pool, app.state.bus)
    _admin_ctx = BossContext(boss_id=0, user_role="superadmin")
    app.state.llm_gateway = NativeGateway(
        pool=app.state.db_pool,
        registry=app.state.model_registry,
        llm_routes_repo=LLMRoutesRepo(app.state.db_pool, _admin_ctx),
        feature_budgets_repo=FeatureBudgetsRepo(app.state.db_pool, _admin_ctx),
        api_key_provider=make_api_key_provider(app.state.db_pool),
    )
    await ensure_collection(app.state.qdrant)
    app.state.memory_provider = InternalMemoryProvider(
        pool=app.state.db_pool,
        qdrant=app.state.qdrant,
        llm_gateway=app.state.llm_gateway,
    )
    app.state.op_dispatcher = OperationDispatcher(app.state.bus, app.state)
    app.state.op_dispatcher.attach_all()
    app.state.trigger_engine = TriggerEngine(app.state.bus)
    app.state.trigger_engine.attach_all()

    # Channel adapters (Zalo first).
    _admin_repo = BotAccountsRepo(app.state.db_pool, _admin_ctx)
    app.state.zalo = ZaloAdapter(app.state.bus, _admin_repo)
    app.state.channels = {"zalo": app.state.zalo}
    zalo_normalizer.register(app.state.bus, app.state.db_pool)
    zalo_outbound.register(
        app.state.bus, app.state.zalo, app.state.db_pool, _admin_repo
    )
    # Boot all active Zalo bot_accounts.
    async with app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM bot_accounts WHERE provider='zalo' AND status='active'"
        )
    for r in rows:
        try:
            await app.state.zalo.start_inbound(_row_to_bot_account(r))
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "zalo start_inbound failed bot_acc=%s", r["id"]
            )

    # Plugins — scan plugins/ and import each plugin's tools module so
    # any @tool decorators register before the dispatcher is hit.
    loaded = load_plugins()
    import logging as _log
    _log.getLogger(__name__).info("plugins loaded: %s", loaded)

    # APScheduler — reminder firer + bot-account health + subscription check.
    app.state.scheduler = make_scheduler(app.state)
    app.state.scheduler.start()

    yield
    # Best-effort shutdown: stop scheduler, stop bridges, close pool.
    try:
        app.state.scheduler.shutdown(wait=False)
    except Exception:
        pass
    for r in rows:
        try:
            await app.state.zalo.stop_inbound(_row_to_bot_account(r))
        except Exception:
            pass
    await app.state.db_pool.close()


app = FastAPI(title="SMART_bot", lifespan=lifespan)

# Web: session (used by authlib OAuth state) + CSRF persistence middleware.
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, same_site="lax")
app.middleware("http")(csrf_middleware)

# Static files for /static/* (Tailwind CDN handles most styling; /static/style.css
# holds small overrides).
_STATIC_DIR = Path(__file__).parent / "web" / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Web routers.
app.include_router(web_auth.router)
app.include_router(web_oauth.router)
app.include_router(web_app.router, prefix="/app")
app.include_router(web_api.router)
app.include_router(web_api_ai.router)
app.include_router(web_admin.router)


@app.get("/")
async def root_index():
    return RedirectResponse("/app", status_code=303)


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
