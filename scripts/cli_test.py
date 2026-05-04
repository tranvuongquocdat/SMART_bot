#!/usr/bin/env python
"""Interactive CLI to test the AI pipeline without Telegram/Zalo.

Usage:
    python scripts/cli_test.py                # picks first boss
    python scripts/cli_test.py --boss "Dat"   # match by name substring
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import mimetypes
import os
import sys
import time

# Project root on sys.path
sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-10s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

from src import agent, context, db, scheduler            # noqa: E402
from src.config import Settings                           # noqa: E402
from src.channels import telegram_singleton as telegram   # noqa: E402
from src.channels import registry as channel_registry     # noqa: E402
from src.channels.cli_messenger import CliMessenger, mark_start  # noqa: E402
from src.channels.base import IncomingMessage             # noqa: E402
from src.infrastructure import (                          # noqa: E402
    cohere_client as cohere,
    lark_client as lark,
    openai_client,
    qdrant_client as qdrant,
)


async def init_services(settings: Settings) -> None:
    """Mirror the init sequence from main.py lifespan (no polling)."""
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
    agent.init_agent(settings)

    from src.agent.llm_for_ctx import init_llm_settings
    init_llm_settings(settings)

    from src.infrastructure.observability import setup_logging
    setup_logging(settings)

    from src.container import build_container
    container = await build_container(settings)

    # Register real Telegram (for fallback routing) + CLI channel
    channel_registry.register("telegram", telegram.get_messenger())
    cli = CliMessenger()
    channel_registry.register("cli", cli)
    container.messengers["telegram"] = telegram.get_messenger()
    container.messengers["cli"] = cli

    from src.controllers.message_router import MessageRouter
    router = MessageRouter(container)

    await scheduler.start(settings)
    return router


async def pick_boss(name_hint: str | None) -> dict:
    bosses = await db.get_all_bosses()
    if not bosses:
        print("No bosses in DB. Run the bot normally first to onboard.")
        sys.exit(1)

    if name_hint:
        q = name_hint.lower()
        matches = [b for b in bosses if q in (b.get("name") or "").lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print("Ambiguous --boss, matches:")
            for b in matches:
                print(f"  - {b['name']}  (chat_id={b['chat_id']})")
            sys.exit(1)
        print(f"No boss matching '{name_hint}'. Available:")
        for b in bosses:
            print(f"  - {b['name']}  (chat_id={b['chat_id']})")
        sys.exit(1)

    # Default: first boss
    return bosses[0]


async def main() -> None:
    parser = argparse.ArgumentParser(description="CLI debug tool for SMART bot")
    parser.add_argument("--boss", default=None, help="Boss name substring")
    parser.add_argument(
        "--attach", action="append", default=[],
        help="Local file path to attach to the next prompt (repeat for multi)",
    )
    args = parser.parse_args()

    settings = Settings()
    router = await init_services(settings)

    boss = await pick_boss(args.boss)
    boss_id = boss["chat_id"]  # internal UUID
    boss_name = boss.get("name") or "Boss"

    # Create/reuse a CLI conversation for this boss
    conv_id = await db.resolve_or_create_conversation("cli", boss_id, "dm", "")

    print(f"\n\033[1mCLI Debug — boss: {boss_name} ({boss_id})\033[0m")
    print(f"conversation: {conv_id}")
    print("Type a message, or 'quit' to exit.\n")

    while True:
        try:
            text = input(f"\033[33m[{boss_name}]\033[0m > ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        text = text.strip()
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break

        attachments: list = []
        for ap in (args.attach or []):
            ap_path = os.path.abspath(ap)
            if not os.path.exists(ap_path):
                print(f"\033[31m[skip] not found: {ap}\033[0m")
                continue
            from src.channels.base import Attachment
            mime, _ = mimetypes.guess_type(ap_path)
            attachments.append(Attachment(
                kind="file",
                url=ap_path,
                mime_type=mime or "application/octet-stream",
                filename=os.path.basename(ap_path),
                size_bytes=os.path.getsize(ap_path),
            ))
        # Once-only — clear so subsequent prompts don't reattach
        args.attach = []

        incoming = IncomingMessage(
            channel="cli",
            chat_id=conv_id,
            chat_type="dm",
            sender_id=boss_id,
            sender_name=boss_name,
            text=text,
            attachments=attachments,
            timestamp=int(time.time()),
        )

        mark_start()
        t0 = time.monotonic()
        await router.handle(incoming)
        elapsed = time.monotonic() - t0
        print(f"\033[2m--- total: {elapsed:.1f}s ---\033[0m\n")

    # Cleanup
    await scheduler.stop()
    await telegram.close_telegram()
    await lark.close_lark()
    await cohere.close_cohere()
    await qdrant.close_qdrant()
    await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
