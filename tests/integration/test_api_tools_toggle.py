"""Tests for tools list and toggle with limit enforcement."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-tools"


def _csrf_headers(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_list_tools_unauthenticated(client):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 401


def test_list_tools_returns_registry(client, logged_in_boss):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    tool = body[0]
    assert "name" in tool and "description" in tool and "active" in tool


def test_list_tools_shows_active_state(client, logged_in_boss, clean_db):
    """Fixture seeds all registry tools active; the list must reflect that."""
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    assert all(t["active"] for t in body)


def test_toggle_tool_no_csrf(client, logged_in_boss):
    r = client.patch("/api/v1/admin/tools/current_time/toggle")
    assert r.status_code == 403


def test_toggle_tool_activate(client, logged_in_boss, clean_db):
    # Fixture seeds current_time active — remove it first so toggle activates.
    async def _clear():
        async with clean_db.acquire() as c:
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1 AND tool_name='current_time'",
                logged_in_boss.boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_clear())
    r = client.patch(
        "/api/v1/admin/tools/current_time/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_toggle_tool_deactivate(client, logged_in_boss, clean_db):
    # Seed one active tool manually
    async def _seed():
        async with clean_db.acquire() as c:
            await c.execute(
                "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, 'current_time') "
                "ON CONFLICT DO NOTHING",
                logged_in_boss.boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_seed())
    r = client.patch(
        "/api/v1/admin/tools/current_time/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_toggle_nonexistent_tool(client, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/tools/nonexistent_tool_xyz/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 404


def test_toggle_respects_plan_limit(client, logged_in_boss, clean_db):
    """Cannot activate more tools than max_active_tools allows."""

    async def _setup():
        async with clean_db.acquire() as c:
            pid = await c.fetchval(
                "INSERT INTO plans (name,label,limits_json) "
                "VALUES ('tiny_test','Tiny',$1::jsonb) "
                "ON CONFLICT(name) DO UPDATE SET limits_json=EXCLUDED.limits_json RETURNING id",
                '{"max_active_tools": 1}',
            )
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1", logged_in_boss.boss_id
            )
            await c.execute(
                "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, 'current_time')",
                logged_in_boss.boss_id,
            )
            await c.execute(
                "UPDATE users SET plan_id=$2 WHERE id=$1", logged_in_boss.boss_id, pid
            )

    asyncio.get_event_loop().run_until_complete(_setup())

    # Trying to activate a second tool should be blocked
    r = client.patch(
        "/api/v1/admin/tools/set_reminder/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 400
    assert "giới hạn" in r.json()["detail"].lower()


def test_enable_all_tools(client, logged_in_boss, clean_db):
    """Enable-all turns on every registry tool when plan is unlimited."""
    async def _clear():
        async with clean_db.acquire() as c:
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1",
                logged_in_boss.boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_clear())
    r = client.post("/api/v1/admin/tools/enable-all", headers=_csrf_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] == body["total"]
    assert body["active"] == body["total"]


def test_enable_all_tools_respects_limit(client, logged_in_boss, clean_db):
    """Enable-all caps at the plan's max_active_tools."""
    async def _setup():
        async with clean_db.acquire() as c:
            pid = await c.fetchval(
                "INSERT INTO plans (name,label,limits_json) VALUES "
                "('tiny-all','Tiny','{\"max_active_tools\": 3}'::jsonb) "
                "ON CONFLICT (name) DO UPDATE SET limits_json=EXCLUDED.limits_json RETURNING id"
            )
            await c.execute(
                "UPDATE users SET plan_id=$2 WHERE id=$1",
                logged_in_boss.boss_id, pid,
            )
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1",
                logged_in_boss.boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_setup())
    r = client.post("/api/v1/admin/tools/enable-all", headers=_csrf_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == 3
    assert body["limit"] == 3


def test_disable_all_tools(client, logged_in_boss):
    r = client.post("/api/v1/admin/tools/disable-all", headers=_csrf_headers(client))
    assert r.status_code == 200
    assert r.json()["active"] == 0
    r2 = client.get("/api/v1/admin/tools")
    assert all(not t["active"] for t in r2.json())
