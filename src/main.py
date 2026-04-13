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
from src.services import cohere, lark, openai_client, qdrant, telegram


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

    # Start scheduler + polling
    await scheduler.start(settings)
    polling_task = asyncio.create_task(
        telegram.start_polling(agent.handle_message)
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
