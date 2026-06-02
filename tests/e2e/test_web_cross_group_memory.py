"""E2E test cho web channel: agent nắm context cross-group.

Setup: 2 group, mỗi group có vài message khác chủ đề. Boss DM hỏi
about content; assert response chứa keyword từ group đúng.

Marked slow + requires real LLM keys (set qua env vars).
"""

from __future__ import annotations

import asyncio
import os

import pytest

from fastapi.testclient import TestClient


pytestmark = pytest.mark.skipif(
    not os.getenv("PLATFORM_GROQ_API_KEY") and not os.getenv("PLATFORM_OPENAI_API_KEY"),
    reason="needs real LLM keys",
)


def _send(client, *, as_uid, chat_id, text, mention=False):
    r = client.post(
        "/test/api/send",
        json={"as": as_uid, "chat_id": chat_id, "text": text, "mention_bot": mention},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_boss_dm_recalls_content_from_two_groups(clean_db):
    from src.main import app

    with TestClient(app) as client:
        # 1. Create boss + 2 non-bosses
        boss_uid = client.post(
            "/test/api/users", json={"name": "Boss", "is_boss": True}
        ).json()["id"]
        u_alice = client.post(
            "/test/api/users", json={"name": "Alice", "is_boss": False}
        ).json()["id"]
        u_bob = client.post(
            "/test/api/users", json={"name": "Bob", "is_boss": False}
        ).json()["id"]

        # 2. Two groups, both include boss
        g1 = client.post(
            "/test/api/groups",
            json={"name": "marketing", "member_ids": [boss_uid, u_alice]},
        ).json()["id"]
        g2 = client.post(
            "/test/api/groups",
            json={"name": "engineering", "member_ids": [boss_uid, u_bob]},
        ).json()["id"]

        # 3. Group messages (different topics)
        _send(client, as_uid=u_alice, chat_id=g1, text="Bài quảng cáo TikTok đã chốt ngân sách 50 triệu")
        _send(client, as_uid=u_bob, chat_id=g2, text="Migration Postgres 14 → 16 lên schedule thứ 6 tuần sau")
        await asyncio.sleep(0.5)  # let normalizer flush

        # 4. Boss DM asks across groups
        _send(client, as_uid=boss_uid, chat_id=f"dm:{boss_uid}", text="Tóm tắt nhóm marketing đang bàn gì?")
        # Wait for LLM reply
        await asyncio.sleep(8.0)

        # 5. Replay DM → should contain bot reply mentioning topic
        msgs = client.get(
            f"/test/api/chats/dm:{boss_uid}/messages?limit=50"
        ).json()
        bot_replies = [m["text"] for m in msgs if m["kind"] == "out"]
        assert any(
            ("TikTok" in r or "quảng cáo" in r or "50 triệu" in r)
            for r in bot_replies
        ), f"bot reply missed group-1 topic: {bot_replies}"
