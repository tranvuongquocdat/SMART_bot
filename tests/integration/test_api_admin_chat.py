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


def test_conversations_crud(client, logged_in_boss):
    headers = _csrf(client)
    # list tự tạo hội thoại mặc định
    r = client.get("/api/v1/admin/chat/conversations")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # tạo mới
    r2 = client.post("/api/v1/admin/chat/conversations", json={"name": "Kế hoạch Q3"}, headers=headers)
    assert r2.status_code == 201
    cid = r2.json()["id"]

    # rename
    r3 = client.patch(f"/api/v1/admin/chat/conversations/{cid}", json={"name": "Q3 mới"}, headers=headers)
    assert r3.status_code == 200

    # gửi tin vào hội thoại mới
    r4 = client.post("/api/v1/admin/chat/send", json={"text": "hello q3", "conversation_id": cid}, headers=headers)
    assert r4.status_code == 200
    msgs = client.get(f"/api/v1/admin/chat/messages?conversation_id={cid}").json()
    assert any(m["text"] and "hello q3" in m["text"] for m in msgs)

    # hội thoại mặc định không chứa tin đó
    default_msgs = client.get("/api/v1/admin/chat/messages").json()
    assert not any(m["text"] and "hello q3" in m["text"] for m in default_msgs)

    # xoá
    r5 = client.delete(f"/api/v1/admin/chat/conversations/{cid}", headers=headers)
    assert r5.status_code == 204
    assert len(client.get("/api/v1/admin/chat/conversations").json()) == 1


def test_send_with_attachment(client, logged_in_boss):
    import io
    headers = _csrf(client)
    r = client.post(
        "/api/v1/admin/chat/upload",
        files={"file": ("bao_cao.pdf", io.BytesIO(b"%PDF fake"), "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 200
    att = r.json()
    assert att["kind"] == "file"

    r2 = client.post(
        "/api/v1/admin/chat/send",
        json={"text": "xem giúp file", "attachment": att},
        headers=headers,
    )
    assert r2.status_code == 200
    msgs = client.get("/api/v1/admin/chat/messages").json()
    last_in = [m for m in msgs if m["kind"] == "in"][-1]
    assert last_in["media_url"] == att["url"]


def test_integrations_flow(client, logged_in_boss, clean_db):
    """Catalog → add → slot limit → toggle → delete."""
    import asyncio as _asyncio
    headers = _csrf(client)

    async def _seed():
        async with clean_db.acquire() as c:
            cid1 = await c.fetchval(
                "INSERT INTO mcp_catalog (name, url) VALUES ('Google Calendar', 'https://mcp.gcal.test') RETURNING id"
            )
            cid2 = await c.fetchval(
                "INSERT INTO mcp_catalog (name, url) VALUES ('Lark Base', 'https://mcp.lark.test') RETURNING id"
            )
            await c.execute(
                "UPDATE users SET plan_overrides_json='{\"mcp_slots\": 1}'::jsonb WHERE id=$1",
                logged_in_boss.boss_id,
            )
            return cid1, cid2

    cid1, cid2 = _asyncio.get_event_loop().run_until_complete(_seed())

    body = client.get("/api/v1/admin/integrations").json()
    assert body["mcp_slots"] == 1
    assert len(body["catalog"]) == 2

    r = client.post("/api/v1/admin/mcp-servers", json={"catalog_id": cid1}, headers=headers)
    assert r.status_code == 201
    sid = r.json()["id"]

    # slot đầy → thêm cái 2 bị chặn
    r2 = client.post("/api/v1/admin/mcp-servers", json={"catalog_id": cid2}, headers=headers)
    assert r2.status_code == 400

    # tắt → bật lại ok
    assert client.patch(f"/api/v1/admin/mcp-servers/{sid}/toggle", headers=headers).json()["enabled"] is False
    assert client.patch(f"/api/v1/admin/mcp-servers/{sid}/toggle", headers=headers).json()["enabled"] is True

    assert client.delete(f"/api/v1/admin/mcp-servers/{sid}", headers=headers).status_code == 204
