"""G2: user-facing pages render 200 for logged-in boss; 401 for anonymous.

Pages tested:
  /app           (dashboard)
  /app/groups
  /app/action-items
  /app/projects
  /app/reminders   (+ POST create / cancel)
  /app/channels
  /app/usage
  /app/settings/general
  /app/settings/account
  /app/settings/ai
  /app/subscription
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.web.routes.auth import hash_password


@pytest.fixture
def logged_in_client(boss_user, db_pool):
    """Boss user with a known password, logged in via TestClient."""
    from src import main as main_mod

    with TestClient(main_mod.app) as client:
        # Set password on the seeded boss synchronously via the running loop.
        import asyncio
        loop = asyncio.get_event_loop()

        async def _set_pw():
            async with db_pool.acquire() as c:
                await c.execute(
                    "UPDATE users SET password_hash=$1 WHERE id=$2",
                    hash_password("pw"),
                    boss_user["id"],
                )
        loop.run_until_complete(_set_pw())

        client.get("/login")
        csrf = client.cookies.get("smart_csrf")
        r = client.post(
            "/login",
            data={"email": boss_user["email"], "password": "pw", "_csrf": csrf},
            headers={"X-CSRF-Token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        yield client, boss_user, csrf


USER_PAGES = [
    "/legacy-app",
    "/legacy-app/groups",
    "/legacy-app/action-items",
    "/legacy-app/projects",
    "/legacy-app/reminders",
    "/legacy-app/channels",
    "/legacy-app/usage",
    "/legacy-app/settings/general",
    "/legacy-app/settings/account",
    "/legacy-app/settings/ai",
    "/legacy-app/subscription",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", USER_PAGES)
async def test_user_page_renders_for_logged_in_boss(logged_in_client, path):
    client, _, _ = logged_in_client
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


@pytest.mark.asyncio
async def test_anonymous_blocked(boss_user):
    from src import main as main_mod
    with TestClient(main_mod.app) as client:
        for path in USER_PAGES:
            r = client.get(path, follow_redirects=False)
            assert r.status_code in (401, 303, 307), f"{path} -> {r.status_code}"


@pytest.mark.asyncio
async def test_create_and_cancel_reminder(logged_in_client, db_pool, boss_user):
    client, _, csrf = logged_in_client
    r = client.post(
        "/legacy-app/reminders",
        data={
            "text": "Họp với khách",
            "due_at": "2030-01-01T10:00",
            "scope": "dm",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    async with db_pool.acquire() as c:
        rid = await c.fetchval(
            "SELECT id FROM scheduled_reminders WHERE boss_id=$1 AND text=$2",
            boss_user["id"],
            "Họp với khách",
        )
    assert rid is not None

    r2 = client.post(
        f"/legacy-app/reminders/{rid}/cancel",
        data={"_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    async with db_pool.acquire() as c:
        status = await c.fetchval(
            "SELECT status FROM scheduled_reminders WHERE id=$1", rid
        )
    assert status == "canceled"
