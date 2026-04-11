import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src import agent, db, scheduler
from src.config import Settings
from src.services import cohere, lark, openai_client, qdrant, telegram
from src.tools import init_tools


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = Settings()

    # Init all services
    await db.init_db(settings.db_path)
    openai_client.init_openai(
        settings.openai_api_key,
        settings.openai_chat_model,
        settings.openai_embedding_model,
    )
    await qdrant.init_qdrant(settings.qdrant_url, settings.qdrant_collection)
    await cohere.init_cohere(settings.cohere_api_key)
    await lark.init_lark(
        settings.lark_app_id, settings.lark_app_secret, settings.lark_base_app_token
    )
    await telegram.init_telegram(settings.telegram_bot_token)

    # Init tools + agent
    init_tools(settings)
    agent.init_agent(settings)

    # Start scheduler
    await scheduler.start(settings)

    yield

    # Shutdown
    await scheduler.stop()
    await telegram.close_telegram()
    await lark.close_lark()
    await cohere.close_cohere()
    await qdrant.close_qdrant()
    await db.close_db()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update = await request.json()
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if text and chat_id:
        asyncio.create_task(agent.handle_message(text, chat_id))

    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
