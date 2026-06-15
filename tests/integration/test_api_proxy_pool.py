"""Proxy pool: CRUD + gán per-boss + cap max_bosses + resolve cho adapter."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-proxy"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _seed_boss(clean_db, email="proxy-boss@test.local") -> int:
    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO users (email, name, role) VALUES ($1, 'PB', 'boss')
                ON CONFLICT (email) DO UPDATE SET role='boss' RETURNING id
                """,
                email,
            )

    return _run(_())


def test_proxy_crud_and_masking(client, logged_in_superadmin):
    r = client.post(
        "/api/v1/superadmin/proxies",
        json={"label": "VN-HN-1", "url": "http://user:secret@1.2.3.4:8080", "region": "VN-HN", "max_bosses": 1},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    lst = client.get("/api/v1/superadmin/proxies").json()
    row = next(p for p in lst if p["id"] == pid)
    # URL masked — không lộ password
    assert "secret" not in str(row)
    assert row["url_masked"] == "http://user:***@1.2.3.4:8080"
    assert row["assigned_count"] == 0

    r2 = client.patch(
        f"/api/v1/superadmin/proxies/{pid}",
        json={"max_bosses": 3, "region": "VN-HCM"},
        headers=_csrf(client),
    )
    assert r2.status_code == 200


def test_proxy_create_requires_scheme(client, logged_in_superadmin):
    r = client.post(
        "/api/v1/superadmin/proxies",
        json={"label": "bad", "url": "1.2.3.4:8080"},
        headers=_csrf(client),
    )
    assert r.status_code == 422


def test_assign_resolve_and_cap(client, logged_in_superadmin, clean_db):
    from src.services.proxy_pool import resolve_for_boss

    pid = client.post(
        "/api/v1/superadmin/proxies",
        json={"label": "cap1", "url": "http://u:p@9.9.9.9:3128", "max_bosses": 1},
        headers=_csrf(client),
    ).json()["id"]

    b1 = _seed_boss(clean_db, "pb1@test.local")
    b2 = _seed_boss(clean_db, "pb2@test.local")

    r = client.put(
        f"/api/v1/superadmin/bosses/{b1}/proxy",
        json={"proxy_id": pid},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text

    # Adapter resolve ra đúng URL đã giải mã
    url = _run(resolve_for_boss(clean_db, b1))
    assert url == "http://u:p@9.9.9.9:3128"

    # Cap=1 → gán boss thứ 2 bị chặn
    r2 = client.put(
        f"/api/v1/superadmin/bosses/{b2}/proxy",
        json={"proxy_id": pid},
        headers=_csrf(client),
    )
    assert r2.status_code == 409

    # Không gán proxy → resolve None
    assert _run(resolve_for_boss(clean_db, b2)) is None

    # Gỡ proxy khỏi b1
    r3 = client.put(
        f"/api/v1/superadmin/bosses/{b1}/proxy",
        json={"proxy_id": None},
        headers=_csrf(client),
    )
    assert r3.status_code == 200
    assert _run(resolve_for_boss(clean_db, b1)) is None


def test_delete_blocked_when_assigned(client, logged_in_superadmin, clean_db):
    pid = client.post(
        "/api/v1/superadmin/proxies",
        json={"label": "del", "url": "http://u:p@8.8.8.8:3128"},
        headers=_csrf(client),
    ).json()["id"]
    b = _seed_boss(clean_db, "pbdel@test.local")
    client.put(f"/api/v1/superadmin/bosses/{b}/proxy", json={"proxy_id": pid}, headers=_csrf(client))

    r = client.delete(f"/api/v1/superadmin/proxies/{pid}", headers=_csrf(client))
    assert r.status_code == 409  # còn gán

    client.put(f"/api/v1/superadmin/bosses/{b}/proxy", json={"proxy_id": None}, headers=_csrf(client))
    r2 = client.delete(f"/api/v1/superadmin/proxies/{pid}", headers=_csrf(client))
    assert r2.status_code == 200


def test_overview_shows_assigned_proxy(client, logged_in_superadmin, clean_db):
    pid = client.post(
        "/api/v1/superadmin/proxies",
        json={"label": "ov", "url": "http://u:p@7.7.7.7:3128", "region": "VN"},
        headers=_csrf(client),
    ).json()["id"]
    b = _seed_boss(clean_db, "pbov@test.local")
    client.put(f"/api/v1/superadmin/bosses/{b}/proxy", json={"proxy_id": pid}, headers=_csrf(client))

    ov = client.get(f"/api/v1/superadmin/bosses/{b}/overview").json()
    assert ov["proxy"]["id"] == pid
    assert ov["proxy"]["label"] == "ov"


# ---------------------------------------------------------------------------
# Ràng buộc: mỗi boss chỉ 1 bot account boss_owned / nền tảng (DB index)
# ---------------------------------------------------------------------------


def test_one_boss_owned_account_per_provider(clean_db):
    import asyncpg as _pg

    b = _seed_boss(clean_db, "oneacc@test.local")

    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind,
                   ownership, owner_boss_id, status)
                VALUES ('zalo','z-a','A','personal','boss_owned',$1,'active')
                """,
                b,
            )
            # Acc Zalo thứ 2 cho cùng boss → vi phạm partial unique index
            try:
                await c.execute(
                    """
                    INSERT INTO bot_accounts
                      (provider, provider_user_id, display_name, account_kind,
                       ownership, owner_boss_id, status)
                    VALUES ('zalo','z-b','B','personal','boss_owned',$1,'active')
                    """,
                    b,
                )
                return "inserted"
            except _pg.UniqueViolationError:
                return "blocked"

    assert _run(_()) == "blocked"


def test_different_provider_same_boss_ok(clean_db):
    b = _seed_boss(clean_db, "multiplat@test.local")

    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind,
                   ownership, owner_boss_id, status)
                VALUES ('zalo','mz-1','Z','personal','boss_owned',$1,'active'),
                       ('messenger','mm-1','M','personal','boss_owned',$1,'active'),
                       ('telegram','mt-1','T','personal','boss_owned',$1,'active')
                """,
                b,
            )
            return await c.fetchval(
                "SELECT COUNT(*) FROM bot_accounts WHERE owner_boss_id=$1", b
            )

    # 3 nền tảng khác nhau cho cùng boss → OK
    assert _run(_()) == 3
