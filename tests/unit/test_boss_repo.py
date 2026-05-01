"""Tests for src.repositories.boss_repo — round-trip via the canonical schema."""
from __future__ import annotations

import aiosqlite
import pytest

from src.db import _init_schema
from src.repositories.boss_repo import BossRepo


@pytest.mark.asyncio
async def test_create_get_list_round_trip(tmp_path):
    path = tmp_path / "t.db"
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await _init_schema(conn)

    repo = BossRepo(conn)
    await repo.create(
        chat_id="uuid-boss-1",
        name="Boss A",
        company="ACME",
        lark_base_token="bt",
        lark_table_people="tp",
        lark_table_tasks="tt",
        lark_table_projects="tpr",
        lark_table_ideas="ti",
        lark_table_reminders="tr",
        lark_table_notes="tn",
        email="a@x.com",
    )

    one = await repo.get("uuid-boss-1")
    assert one is not None
    assert one["chat_id"] == "uuid-boss-1"
    assert one["name"] == "Boss A"
    assert one["status"] == "active"          # default from Phase 3 schema
    assert one["llm_api_key_encrypted"] is None

    assert await repo.get("nope") is None

    everyone = await repo.list_all()
    assert len(everyone) == 1
    assert everyone[0]["chat_id"] == "uuid-boss-1"

    await conn.close()
