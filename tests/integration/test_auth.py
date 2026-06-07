"""G1: web auth foundation.

We boot the FastAPI app via TestClient using the same lifespan (db pool +
qdrant). Tests verify:
  - /login renders with CSRF cookie
  - email/password login (with bcrypt) sets session and redirects
  - logged-in cookie reaches /app routes
  - anonymous /app/* → 401
  - OAuth login disabled cleanly when client_id is empty
  - CSRF mismatch on POST → 403
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from src.web.routes.auth import hash_password


@pytest.fixture
def app_client(boss_user):
    # Force the test to NOT require Google OAuth creds.
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "")
    from src import main as main_mod
    # Use the configured `app` (lifespan starts pool + qdrant; both must be
    # available in the test environment).
    with TestClient(main_mod.app) as client:
        yield client, boss_user


@pytest.mark.asyncio
async def test_login_page_renders(app_client):
    client, _ = app_client
    r = client.get("/login")
    assert r.status_code == 200
    # CSRF cookie minted by ensure_csrf in the login route
    assert "smart_csrf" in r.cookies


@pytest.mark.asyncio
async def test_anonymous_api_me_401(app_client):
    client, _ = app_client
    # /api/v1/me requires auth; anonymous call must return 401.
    r = client.get("/api/v1/me", follow_redirects=False)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_email_password_login(app_client, db_pool):
    client, boss = app_client
    # Set a known password on the seeded user.
    pw_hash = hash_password("hunter2")
    async with db_pool.acquire() as c:
        await c.execute(
            "UPDATE users SET password_hash=$1 WHERE id=$2", pw_hash, boss["id"]
        )

    # Visit login first to mint CSRF cookie.
    client.get("/login")
    csrf = client.cookies.get("smart_csrf")
    assert csrf

    r = client.post(
        "/login",
        data={"email": boss["email"], "password": "hunter2", "_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/app"
    assert "smart_session" in r.cookies or "smart_session" in client.cookies

    # After login, /api/v1/me should return the authenticated user.
    r2 = client.get("/api/v1/me")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_login_csrf_mismatch_rejected(app_client, db_pool):
    client, boss = app_client
    async with db_pool.acquire() as c:
        await c.execute(
            "UPDATE users SET password_hash=$1 WHERE id=$2",
            hash_password("hunter2"),
            boss["id"],
        )
    client.get("/login")
    # Strip the CSRF cookie -> server-side verify_csrf must fail (no cookie).
    client.cookies.delete("smart_csrf")
    r = client.post(
        "/login",
        data={"email": boss["email"], "password": "hunter2", "_csrf": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_oauth_disabled_when_no_client_id(app_client, monkeypatch):
    client, _ = app_client
    # In this test config, GOOGLE_OAUTH_CLIENT_ID is empty by fixture setup.
    from src.config import settings
    if settings.GOOGLE_OAUTH_CLIENT_ID:
        pytest.skip("OAuth client id is configured; skip disabled-path test")
    r = client.get("/api/oauth/google/login", follow_redirects=False)
    assert r.status_code in (400, 503)


@pytest.mark.asyncio
async def test_logout_clears_session(app_client, db_pool):
    client, boss = app_client
    async with db_pool.acquire() as c:
        await c.execute(
            "UPDATE users SET password_hash=$1 WHERE id=$2",
            hash_password("pw"),
            boss["id"],
        )
    client.get("/login")
    csrf = client.cookies.get("smart_csrf")
    client.post(
        "/login",
        data={"email": boss["email"], "password": "pw", "_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert "smart_session" in client.cookies

    r = client.post(
        "/logout",
        data={"_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # After logout the session cookie should be cleared.
    # After logout, /api/v1/me should return 401.
    r2 = client.get("/api/v1/me", follow_redirects=False)
    assert r2.status_code == 401
