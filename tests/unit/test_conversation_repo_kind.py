"""ConversationRepo.get_kind round-trip — needed by ZaloMessenger.send to
choose dm vs group thread_type when calling the bridge.
"""
from __future__ import annotations

import pytest


async def test_get_kind_returns_chat_type(tmp_path):
    from src import db as _db_mod
    await _db_mod.close_db()

    db = await _db_mod.get_db(str(tmp_path / "k.db"))

    from src.repositories.conversation_repo import ConversationRepo
    repo = ConversationRepo(db)

    chat_id = await repo.resolve_or_create_conversation(
        "zalo", "ext-thread-1", "group", "Team",
    )
    assert await repo.get_kind(chat_id) == "group"

    dm = await repo.resolve_or_create_conversation("zalo", "u-1", "dm", "")
    assert await repo.get_kind(dm) == "dm"


async def test_get_kind_unknown_returns_empty(tmp_path):
    from src import db as _db_mod
    await _db_mod.close_db()
    db = await _db_mod.get_db(str(tmp_path / "k2.db"))

    from src.repositories.conversation_repo import ConversationRepo
    repo = ConversationRepo(db)

    assert await repo.get_kind("nonexistent-uuid") == ""
