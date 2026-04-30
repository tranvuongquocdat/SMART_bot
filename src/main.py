import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-10s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

from src import agent, context, db, scheduler
from src.config import Settings
from src.services import telegram
from src.infrastructure import cohere_client as cohere
from src.infrastructure import qdrant_client as qdrant
from src.infrastructure import lark_client as lark
from src.infrastructure import openai_client


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = Settings()

    # Init services
    database = await db.get_db(settings.db_path)
    context.init_context(database)
    openai_client.init_openai(
        settings.openai_api_key,
        settings.openai_chat_model,
        settings.openai_embedding_model,
    )
    await qdrant.init_qdrant(settings.qdrant_url)
    await cohere.init_cohere(settings.cohere_api_key)
    await lark.init_lark(settings.lark_app_id, settings.lark_app_secret)
    await telegram.init_telegram(settings.telegram_bot_token)

    # Init agent
    agent.init_agent(settings)

    # Phase 4b-3: every LLM call resolves a per-boss LLMClient via this cache.
    from src.agent.llm_for_ctx import init_llm_settings
    init_llm_settings(settings)

    # Phase 5c: structured-logging context filter (boss/chat/request ids).
    from src.infrastructure.observability import setup_logging
    setup_logging(settings)

    # Phase 5a: build AppContainer (read-only wiring snapshot).
    from src.container import build_container
    _app.state.container = await build_container(settings)

    # Phase 5b: MessageRouter is the single inbound boundary.
    from src.controllers.message_router import MessageRouter
    _router = MessageRouter(_app.state.container)
    _app.state.router = _router

    # Start scheduler + polling. Polling now feeds raw IncomingMessage to the
    # router (skipping the legacy positional-arg bridge in services/telegram).
    await scheduler.start(settings)
    polling_task = asyncio.create_task(
        telegram.get_messenger().start(_router.handle)
    )

    yield

    # Shutdown
    telegram.stop_polling()
    polling_task.cancel()
    await scheduler.stop()
    await telegram.close_telegram()
    await lark.close_lark()
    await cohere.close_cohere()
    await qdrant.close_qdrant()
    await db.close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
