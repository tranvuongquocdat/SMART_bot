"""Tests for POST /api/v1/admin/channels/{provider}/connect — self-service assignment."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-channels"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _seed_platform_account(clean_db, provider="web", max_bosses=5) -> int:
    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind,
                   ownership, status, max_assigned_bosses)
                VALUES ($1, $2, 'Pool Bot', 'personal', 'platform', 'active', $3)
                ON CONFLICT (provider, provider_user_id) DO UPDATE
                  SET max_assigned_bosses = EXCLUDED.max_assigned_bosses
                RETURNING id
                """,
                provider,
                f"{provider}-pool-1",
                max_bosses,
            )

    return asyncio.get_event_loop().run_until_complete(_())


def _set_channel_limit(clean_db, boss_id, max_channels):
    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                "UPDATE users SET plan_overrides_json = jsonb_build_object('max_active_channels', $2::int) WHERE id=$1",
                boss_id,
                max_channels,
            )

    asyncio.get_event_loop().run_until_complete(_())


def test_connect_unauthenticated(client):
    r = client.post("/api/v1/admin/channels/web/connect")
    assert r.status_code in (401, 403)


def test_connect_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/channels/web/connect")
    assert r.status_code == 403


def test_connect_happy_path(client, logged_in_boss, clean_db):
    _seed_platform_account(clean_db, "web")
    _set_channel_limit(clean_db, logged_in_boss.boss_id, 3)
    r = client.post("/api/v1/admin/channels/web/connect", headers=_csrf(client))
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "web"
    assert body["status"] == "active"

    # Assignment row exists and is active
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchrow(
                "SELECT status FROM bot_account_assignments WHERE boss_id=$1 AND provider='web'",
                logged_in_boss.boss_id,
            )

    row = asyncio.get_event_loop().run_until_complete(_check())
    assert row["status"] == "active"


def test_connect_already_connected(client, logged_in_boss, clean_db):
    _seed_platform_account(clean_db, "web")
    _set_channel_limit(clean_db, logged_in_boss.boss_id, 3)
    r1 = client.post("/api/v1/admin/channels/web/connect", headers=_csrf(client))
    assert r1.status_code == 200
    r2 = client.post("/api/v1/admin/channels/web/connect", headers=_csrf(client))
    assert r2.status_code == 409


def test_connect_no_capacity(client, logged_in_boss, clean_db):
    # No bot account seeded for this provider at all
    _set_channel_limit(clean_db, logged_in_boss.boss_id, 3)
    r = client.post("/api/v1/admin/channels/zalo/connect", headers=_csrf(client))
    assert r.status_code == 409
    assert "tài khoản" in r.json()["detail"].lower() or "capacity" in r.json()["detail"].lower()


def test_connect_respects_channel_limit(client, logged_in_boss, clean_db):
    _seed_platform_account(clean_db, "web")
    _set_channel_limit(clean_db, logged_in_boss.boss_id, 0)
    r = client.post("/api/v1/admin/channels/web/connect", headers=_csrf(client))
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower() or "giới hạn" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Zalo QR login (boss tự kết nối acc phụ)
# ---------------------------------------------------------------------------


def test_zalo_qr_login_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/channels/zalo/qr-login", json={})
    assert r.status_code == 403


def test_zalo_qr_login_status_unknown_id(client, logged_in_boss):
    r = client.get("/api/v1/admin/channels/zalo/qr-login/deadbeef")
    assert r.status_code == 404


def _seed_zalo_assignment(clean_db, boss_id, *, ownership, kind):
    import asyncio

    async def _seed():
        async with clean_db.acquire() as c:
            acc_id = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind,
                   ownership, owner_boss_id, status, max_assigned_bosses)
                VALUES ('zalo', $1, 'Acc phụ', 'personal', $2, $3::int, 'active', 1)
                RETURNING id
                """,
                f"z-test-{ownership}",
                ownership,
                boss_id if ownership == "boss_owned" else None,
            )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, 'zalo', $2, $3, 'active')
                """,
                boss_id,
                acc_id,
                kind,
            )

    asyncio.get_event_loop().run_until_complete(_seed())


def test_zalo_qr_login_allows_relogin_for_boss_owned(client, logged_in_boss, clean_db):
    """Session Zalo chết là chuyện thường — boss_owned đang active vẫn phải
    mở lại được phiên QR (re-login), không bị 409 kẹt luôn."""
    _seed_zalo_assignment(
        clean_db, logged_in_boss.boss_id, ownership="boss_owned", kind="boss_owned"
    )
    r = client.post(
        "/api/v1/admin/channels/zalo/qr-login",
        json={},
        headers=_csrf(client),
    )
    # Gate cho qua → manager mở phiên (200). Trạng thái phiên (error vì thiếu
    # node deps trong môi trường test) không thuộc phạm vi gate.
    assert r.status_code == 200
    assert "login_id" in r.json()


def test_zalo_qr_login_blocked_when_platform_assigned(client, logged_in_boss, clean_db):
    _seed_zalo_assignment(
        clean_db, logged_in_boss.boss_id, ownership="platform", kind="platform_assigned"
    )
    r = client.post(
        "/api/v1/admin/channels/zalo/qr-login",
        json={},
        headers=_csrf(client),
    )
    assert r.status_code == 409
