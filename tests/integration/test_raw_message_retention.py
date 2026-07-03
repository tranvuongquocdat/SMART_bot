"""Retention TTL: tin thô quá hạn bị dọn, tin mới + knowledge giữ nguyên.

Spec: docs/superpowers/specs/2026-07-02-compliance-erasure-retention-design.md
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.config import settings
from src.scheduler.jobs.raw_message_retention import job
from src.services import platform_settings


async def _boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1, 'Sếp TTL', 'boss') RETURNING id",
            email,
        )


async def _msg(pool, boss_id, age_days, text):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id, "
            "text, ts) VALUES ($1,'zalo','g-ttl','group',$2,$3, NOW() - make_interval(days => $4)) "
            "RETURNING id",
            boss_id, f"ttl-{age_days}-{text[:8]}", text, age_days)


@pytest.mark.asyncio
async def test_purges_old_keeps_recent_and_knowledge(clean_db, monkeypatch):
    monkeypatch.setattr(settings, "RAW_MESSAGE_RETENTION_DAYS", 30)
    platform_settings.clear_cache()  # cache in-process sống xuyên test
    boss = await _boss(clean_db, "ttl1@x.test")
    old_id = await _msg(clean_db, boss, 45, "tin cũ quá hạn")
    new_id = await _msg(clean_db, boss, 5, "tin mới")
    async with clean_db.acquire() as c:
        kid = await c.fetchval(
            "INSERT INTO knowledge_items (boss_id, provider, chat_id, kind, title, content, "
            "status) VALUES ($1,'zalo','g-ttl','decision','V','V','active') RETURNING id", boss)
        await c.execute(
            "INSERT INTO knowledge_provenance (knowledge_item_id, message_id) VALUES ($1,$2)",
            kid, old_id)

    deleted = await job(SimpleNamespace(db_pool=clean_db))

    assert deleted["messages"] >= 1
    async with clean_db.acquire() as c:
        assert await c.fetchval("SELECT 1 FROM messages WHERE id=$1", old_id) is None
        assert await c.fetchval("SELECT 1 FROM messages WHERE id=$1", new_id) == 1
        # knowledge giữ nguyên; provenance mất theo tin (cascade) là chấp nhận
        assert await c.fetchval("SELECT 1 FROM knowledge_items WHERE id=$1", kid) == 1
        assert await c.fetchval(
            "SELECT count(*) FROM knowledge_provenance WHERE knowledge_item_id=$1", kid) == 0


@pytest.mark.asyncio
async def test_zero_ttl_disables_purge(clean_db, monkeypatch):
    monkeypatch.setattr(settings, "RAW_MESSAGE_RETENTION_DAYS", 0)
    platform_settings.clear_cache()
    boss = await _boss(clean_db, "ttl2@x.test")
    old_id = await _msg(clean_db, boss, 400, "tin rất cũ nhưng TTL tắt")

    deleted = await job(SimpleNamespace(db_pool=clean_db))

    assert deleted == {"messages": 0, "outbound_messages": 0}
    async with clean_db.acquire() as c:
        assert await c.fetchval("SELECT 1 FROM messages WHERE id=$1", old_id) == 1
