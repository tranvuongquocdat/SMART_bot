"""Platform settings + history-window config (boss override > mặc định superadmin > 12)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agents.agent_loop import _history_limit
from src.services import platform_settings
from src.web.security import CSRF_COOKIE

CSRF = "csrf-platform"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


async def _boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1, 'Sếp Cfg', 'boss') RETURNING id",
            email,
        )


def _ctx(pool, boss_id):
    return SimpleNamespace(db=pool, boss=SimpleNamespace(id=boss_id))


@pytest.mark.asyncio
async def test_history_limit_priority_chain(clean_db):
    platform_settings.clear_cache()
    boss = await _boss(clean_db, "cfg1@x.test")
    ctx = _ctx(clean_db, boss)

    # chưa set gì → mặc định 12 (platform_settings bị clean_db truncate? bảng
    # không nằm trong truncate list — set tường minh cho tất định)
    await platform_settings.set_setting(clean_db, "history_window_dm", 12)
    await platform_settings.set_setting(clean_db, "history_window_group", 12)
    assert await _history_limit(ctx, "dm") == 12

    # superadmin đổi mặc định → mọi boss ăn theo (tách DM vs nhóm)
    await platform_settings.set_setting(clean_db, "history_window_dm", 20)
    await platform_settings.set_setting(clean_db, "history_window_group", 6)
    assert await _history_limit(ctx, "dm") == 20
    assert await _history_limit(ctx, "group") == 6

    # boss override thắng mặc định; nhóm không override thì vẫn theo hệ thống
    async with clean_db.acquire() as c:
        await c.execute("UPDATE users SET history_window_dm=3 WHERE id=$1", boss)
    assert await _history_limit(ctx, "dm") == 3
    assert await _history_limit(ctx, "group") == 6

    # 0 = tắt; clamp 0-50
    async with clean_db.acquire() as c:
        await c.execute(
            "UPDATE users SET history_window_dm=0, history_window_group=999 WHERE id=$1",
            boss)
    assert await _history_limit(ctx, "dm") == 0
    assert await _history_limit(ctx, "group") == 50


def test_superadmin_platform_settings_endpoints(client, logged_in_superadmin, clean_db):
    platform_settings.clear_cache()
    r = client.patch(
        "/api/v1/superadmin/platform-settings",
        json={"history_window_dm": 25, "raw_message_retention_days": 90},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    assert r.json()["updated"] == {"history_window_dm": 25, "raw_message_retention_days": 90}

    platform_settings.clear_cache()
    got = client.get("/api/v1/superadmin/platform-settings").json()
    assert got["history_window_dm"] == 25
    assert got["raw_message_retention_days"] == 90

    r = client.patch(
        "/api/v1/superadmin/platform-settings",
        json={"history_window_dm": "abc"},
        headers=_csrf(client),
    )
    assert r.status_code == 422


def test_boss_general_settings_history_fields(client, logged_in_boss, clean_db):
    platform_settings.clear_cache()
    r = client.patch(
        "/api/v1/admin/settings/general",
        json={"history_window_dm": 7, "history_window_group": None},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    got = client.get("/api/v1/admin/settings/general").json()
    assert got["history_window_dm"] == 7
    assert got["history_window_group"] is None
    assert "history_window_dm_default" in got
