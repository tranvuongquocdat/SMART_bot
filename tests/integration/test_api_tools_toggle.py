"""Tests for the core-tools list.

New model (2026-06): tools in _REGISTRY are CORE — always on for every boss,
not toggleable, not capped. max_active_tools no longer applies to them; caps
belong to integrations (MCP/plugins). Toggle/disable-all are rejected.
"""
from __future__ import annotations

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-tools"


def _csrf_headers(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_list_tools_unauthenticated(client):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 401


def test_list_tools_returns_core_always_on(client, logged_in_boss):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) > 0
    for t in body:
        assert "name" in t and "description" in t
        # Every built-in tool is core: always active, cannot be disabled.
        assert t["active"] is True
        assert t["core"] is True
        assert t["can_disable"] is False


def test_toggle_core_tool_rejected(client, logged_in_boss):
    """Core tools cannot be turned off."""
    r = client.patch(
        "/api/v1/admin/tools/current_time/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 400


def test_toggle_tool_no_csrf(client, logged_in_boss):
    r = client.patch("/api/v1/admin/tools/current_time/toggle")
    assert r.status_code == 403


def test_toggle_nonexistent_tool(client, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/tools/nonexistent_tool_xyz/toggle",
        headers=_csrf_headers(client),
    )
    assert r.status_code == 404


def test_enable_all_is_full_and_uncapped(client, logged_in_boss, clean_db):
    """Enable-all keeps every core tool active regardless of plan limits."""
    r = client.post("/api/v1/admin/tools/enable-all", headers=_csrf_headers(client))
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == body["total"]
    assert body["limit"] is None


def test_disable_all_rejected(client, logged_in_boss):
    """Core tools can't be disabled — disable-all is rejected and list stays on."""
    r = client.post("/api/v1/admin/tools/disable-all", headers=_csrf_headers(client))
    assert r.status_code == 400
    r2 = client.get("/api/v1/admin/tools")
    assert all(t["active"] for t in r2.json())
