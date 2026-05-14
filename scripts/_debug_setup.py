"""One-shot setup for /debug/test_message smoke testing.

Creates a debug boss with empty Lark fields (Lark calls fail gracefully)
and pre-creates the Qdrant collections that secretary_agent expects.

Usage:
    docker exec smart_bot-app-1 .venv/bin/python /app/scripts/_debug_setup.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app")

from src import db
from src.config import Settings


async def main() -> None:
    settings = Settings()
    await db.get_db(settings.db_path)

    # 1. Reuse if a debug boss already exists, else create new.
    existing = [b for b in await db.get_all_bosses() if str(b.get("chat_id", "")).startswith("dbg-")]
    if existing:
        boss = existing[0]
        print(f"REUSING boss_id={boss['chat_id']}")
    else:
        bid = "dbg-" + uuid.uuid4().hex[:8]
        await db.create_boss(
            chat_id=bid, name="Debug Boss", company="Debug Co",
            lark_base_token="", lark_table_people="",
            lark_table_tasks="", lark_table_projects="",
            lark_table_ideas="", lark_table_reminders="",
            lark_table_notes="", email="dbg@x.com",
        )
        boss = await db.get_boss(bid)
        print(f"CREATED boss_id={bid}")

    boss_id = boss["chat_id"]
    dim = boss.get("embedding_dim") or 1536

    # 2. Pre-create Qdrant collections so secretary_agent's RAG/upsert don't 404.
    from src.infrastructure import qdrant_client as qc
    await qc.init_qdrant(settings.qdrant_url)
    try:
        await qc.provision_collections(boss_id, embedding_dim=dim)
        print(f"COLLECTIONS ok: messages_{boss_id}_{dim}, tasks_{boss_id}_{dim}")
    except Exception as e:
        print(f"COLLECTION provision fail: {e}")

    print(f"\nSETUP DONE. boss_id={boss_id}")


if __name__ == "__main__":
    asyncio.run(main())
