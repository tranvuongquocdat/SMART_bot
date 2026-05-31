from datetime import datetime, timezone

import pytest

from src.domain.message import NewMessage
from src.repositories.base import BossContext
from src.repositories.messages import MessagesRepo


@pytest.mark.asyncio
async def test_insert_and_list_recent(db_pool, boss_user):
    repo = MessagesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    now = datetime.now(timezone.utc)
    mid = await repo.insert(
        NewMessage(
            provider="zalo",
            chat_id="g1",
            chat_type="group",
            provider_msg_id="m1",
            sender_provider_id="u1",
            sender_name="Alice",
            text="Hôm nay deal nóng",
            media_kind=None,
            media_url=None,
            media_text=None,
            ts=now,
        )
    )
    assert mid is not None
    recent = await repo.list_recent("g1")
    assert len(recent) == 1
    assert recent[0].text == "Hôm nay deal nóng"


@pytest.mark.asyncio
async def test_fts_search_unaccent(db_pool, boss_user):
    repo = MessagesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    now = datetime.now(timezone.utc)
    await repo.insert(
        NewMessage(
            provider="zalo",
            chat_id="g1",
            chat_type="group",
            provider_msg_id="m1",
            sender_provider_id="u1",
            sender_name="Alice",
            text="Khách báo deal",
            media_kind=None,
            media_url=None,
            media_text=None,
            ts=now,
        )
    )
    # search without diacritics should still hit
    rows = await repo.fts_search("khach")
    assert len(rows) == 1
