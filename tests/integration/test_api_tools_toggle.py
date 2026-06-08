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
    """Boss has tools active from migration seed; they should show active=True."""
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    # Boss was seeded with 0 tools (no boss_active_tools since it's a fresh test user)
    # So all should be inactive after clean_db truncates boss_active_tools
    body = r.json()
    active = [t for t in body if t["active"]]
    inactive = [t for t in body if not t["active"]]
    # After truncate all are inactive (boss_active_tools cleared by cascade on users truncate)
    assert len(inactive) > 0


def test_toggle_tool_no_csrf(client, logged_in_boss):
    r = client.patch("/api/v1/admin/tools/current_time/toggle")
    assert r.status_code == 403


def test_toggle_tool_activate(client, logged_in_boss):
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
                "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, 'current_time')",
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
    assert "limit" in r.json()["detail"].lower()
