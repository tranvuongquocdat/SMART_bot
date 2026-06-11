"""Tests for admin web chat — boss chats with their bot via the web channel."""
from __future__ import annotations

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-chat"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_chat_messages_unauthenticated(client):
    r = client.get("/api/v1/admin/chat/messages")
    assert r.status_code == 401


def test_chat_send_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/chat/send", json={"text": "hi"})
    assert r.status_code == 403


def test_chat_messages_creates_identity(client, logged_in_boss, clean_db):
    """First call auto-creates a web identity linked to the boss."""
    r = client.get("/api/v1/admin/chat/messages")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    import asyncio

    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT COUNT(*) FROM web_users WHERE boss_user_id=$1 AND is_boss",
                logged_in_boss.boss_id,
            )

    assert asyncio.get_event_loop().run_until_complete(_check()) == 1


def test_chat_send_and_replay(client, logged_in_boss):
    r = client.post(
        "/api/v1/admin/chat/send",
        json={"text": "xin chào bot"},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get("/api/v1/admin/chat/messages")
    assert r2.status_code == 200
    texts = [m["text"] for m in r2.json()]
    assert "xin chào bot" in texts


def test_chat_send_empty_text(client, logged_in_boss):
    r = client.post(
        "/api/v1/admin/chat/send",
        json={"text": "   "},
        headers=_csrf(client),
    )
    assert r.status_code == 400


def test_chat_identity_stable_across_calls(client, logged_in_boss, clean_db):
    """Repeated calls reuse the same web identity (no duplicates)."""
    client.get("/api/v1/admin/chat/messages")
    client.get("/api/v1/admin/chat/messages")

    import asyncio

    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT COUNT(*) FROM web_users WHERE boss_user_id=$1 AND is_boss",
                logged_in_boss.boss_id,
            )

    assert asyncio.get_event_loop().run_until_complete(_check()) == 1
