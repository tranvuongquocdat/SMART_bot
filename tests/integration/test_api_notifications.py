"""Chuông thông báo: broadcast + theo boss, đếm chưa đọc, mark read, auto-notify khi duyệt/từ chối gói."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-notif"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_feed_unauthenticated(client):
    assert client.get("/api/v1/me/notifications").status_code == 401


def test_broadcast_visible_and_mark_read(client, logged_in_boss, logged_in_superadmin):
    # logged_in_superadmin gắn cookie superadmin sau cùng — dùng nó để broadcast,
    # nhưng feed phải tính theo user đang đăng nhập. Tách 2 client-state bằng cookie.
    # Tạo broadcast (đang là superadmin)
    r = client.post(
        "/api/v1/superadmin/announcements",
        json={"title": "Phiên bản 2.1", "body": "Có nhiều cải tiến"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text

    feed = client.get("/api/v1/me/notifications").json()
    assert feed["unread_count"] >= 1
    assert any(n["title"] == "Phiên bản 2.1" for n in feed["items"])

    nid = next(n["id"] for n in feed["items"] if n["title"] == "Phiên bản 2.1")
    r2 = client.post("/api/v1/me/notifications/read", json={"id": nid}, headers=_csrf(client))
    assert r2.status_code == 200

    feed2 = client.get("/api/v1/me/notifications").json()
    assert next(n for n in feed2["items"] if n["id"] == nid)["is_read"] is True


def test_announcement_requires_title(client, logged_in_superadmin):
    r = client.post("/api/v1/superadmin/announcements", json={"body": "x"}, headers=_csrf(client))
    assert r.status_code == 422


def test_mark_all_read(client, logged_in_superadmin):
    for i in range(3):
        client.post(
            "/api/v1/superadmin/announcements",
            json={"title": f"tin {i}"},
            headers=_csrf(client),
        )
    before = client.get("/api/v1/me/notifications").json()
    assert before["unread_count"] >= 3
    client.post("/api/v1/me/notifications/read", json={}, headers=_csrf(client))
    after = client.get("/api/v1/me/notifications").json()
    assert after["unread_count"] == 0


def test_approve_notifies_boss(client, logged_in_superadmin, clean_db):
    # Tạo boss + request pending, duyệt, boss nhận được notification subscription
    async def _seed():
        async with clean_db.acquire() as c:
            boss_id = await c.fetchval(
                "INSERT INTO users (email, name, role) VALUES ('notif-boss@t.local','B','boss') "
                "ON CONFLICT (email) DO UPDATE SET role='boss' RETURNING id"
            )
            plan_id = await c.fetchval("SELECT id FROM plans WHERE name='starter'")
            req_id = await c.fetchval(
                """
                INSERT INTO subscription_requests (boss_id, plan_id, status, billing_months)
                VALUES ($1, $2, 'pending', 1) RETURNING id
                """,
                boss_id,
                plan_id,
            )
            return boss_id, req_id

    boss_id, req_id = _run(_seed())
    r = client.post(
        f"/api/v1/superadmin/subscription-requests/{req_id}/approve",
        json={},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text

    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT COUNT(*) FROM notifications WHERE boss_id=$1 AND kind='subscription'",
                boss_id,
            )

    assert _run(_check()) >= 1
