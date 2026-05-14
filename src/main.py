import asyncio
import logging
import mimetypes
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-10s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

from src import agent, context, db, scheduler
from src.config import Settings
from src.channels import telegram_singleton as telegram
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

    # Channel registry — `telegram_singleton.send/edit` dispatch via this map
    # so a chat with provider="zalo" goes to ZaloMessenger automatically.
    from src.channels import registry as channel_registry
    channel_registry.register("telegram", telegram.get_messenger())

    # Debug channel for /debug/test_message — only when enabled.
    if settings.debug_enabled:
        from src.channels.capturing_messenger import CapturingMessenger
        debug_messenger = CapturingMessenger()
        channel_registry.register("debug", debug_messenger)
        _app.state.container.messengers["debug"] = debug_messenger
        _app.state.debug_settings = settings
        logging.getLogger("main").warning(
            "DEBUG endpoint /debug/test_message ENABLED — disable in production",
        )

    # Start scheduler + polling. Polling now feeds raw IncomingMessage to the
    # router (skipping the legacy positional-arg bridge in services/telegram).
    await scheduler.start(settings)
    polling_task = asyncio.create_task(
        telegram.get_messenger().start(_router.handle)
    )

    # Optional Zalo channel (demo: single account; bridge auto-loads session.json
    # next to bridge.js unless ZALO_SESSION_PATH overrides). `start()` returns
    # once the bridge is ready; subprocess + listener run on background tasks.
    zalo_messenger = None
    if settings.zalo_enabled:
        import os as _os
        from src.channels.zalo import ZaloMessenger
        from src.channels.zalo_bridge.inbound_filter import ZaloInboundFilter
        bridge_js = _os.path.join(
            _os.path.dirname(__file__), "channels", "zalo_bridge", "bridge.js",
        )
        zalo_messenger = ZaloMessenger(
            node_path=settings.zalo_node_path,
            bridge_js_path=bridge_js,
            session_path=settings.zalo_session_path,
            inbound_filter=ZaloInboundFilter(settings.zalo_onboard_phrase),
        )
        try:
            await zalo_messenger.start(_router.handle)
            _app.state.container.messengers["zalo"] = zalo_messenger
            channel_registry.register("zalo", zalo_messenger)
        except Exception:
            logging.getLogger("main").exception("Zalo bridge failed to start; continuing without it")
            zalo_messenger = None

    yield

    # Shutdown
    telegram.stop_polling()
    polling_task.cancel()
    if zalo_messenger is not None:
        await zalo_messenger.stop()
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


@app.post("/debug/test_message")
async def debug_test_message(request: Request):
    """Drive the bot end-to-end without Telegram/Zalo.

    Body:
      {
        "text": "Tóm tắt giúp file PDF này",
        "attach": "/app/data/inbound/test.pdf",  # optional, path inside container
        "boss_id": "<chat_id>"  # optional; defaults to first boss in DB
      }

    Returns: {reply, all_messages: [(send|edit, text)], elapsed_sec}

    Gated by settings.debug_enabled (env: DEBUG_ENABLED=true). Off by default.
    """
    settings = getattr(request.app.state, "debug_settings", None)
    if settings is None or not settings.debug_enabled:
        raise HTTPException(status_code=404, detail="not found")

    body = await request.json()
    text = (body.get("text") or "").strip()
    attach_path = body.get("attach") or ""
    boss_id = body.get("boss_id") or ""

    if not text and not attach_path:
        raise HTTPException(400, "either 'text' or 'attach' required")

    if not boss_id:
        bosses = await db.get_all_bosses()
        if not bosses:
            raise HTTPException(404, "no bosses in DB; onboard one first")
        boss_id = bosses[0]["chat_id"]

    # Resolve / create a debug-channel conversation tied to this boss.
    conv_id = await db.resolve_or_create_conversation("debug", boss_id, "dm", "")

    # Build attachments if requested
    from src.channels.base import Attachment, IncomingMessage
    attachments: list[Attachment] = []
    if attach_path:
        p = Path(attach_path)
        if not p.exists():
            raise HTTPException(404, f"file not found inside container: {attach_path}")
        mime, _ = mimetypes.guess_type(str(p))
        attachments.append(Attachment(
            kind="file",
            url=str(p),
            mime_type=mime or "application/octet-stream",
            filename=p.name,
            size_bytes=p.stat().st_size,
        ))

    incoming = IncomingMessage(
        channel="debug",
        chat_id=conv_id,
        chat_type="dm",
        sender_id=boss_id,
        sender_name="DebugUser",
        text=text,
        attachments=attachments,
        timestamp=int(time.time()),
    )

    from src.channels.capturing_messenger import (
        set_capture_buffer, reset_capture_buffer,
    )
    buf: list[tuple[str, str]] = []
    token = set_capture_buffer(buf)
    t0 = time.monotonic()
    try:
        await request.app.state.router.handle(incoming)
    finally:
        reset_capture_buffer(token)
    elapsed = time.monotonic() - t0

    final = buf[-1][1] if buf else ""
    return {
        "reply": final,
        "all_messages": buf,
        "elapsed_sec": round(elapsed, 3),
    }
