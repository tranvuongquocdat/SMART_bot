"""G3: admin pages — superadmin gating + page renders + mutations.

The fixture promotes the seeded boss to 'superadmin' via SUPERADMIN_EMAILS env
so we can exercise all /admin/* routes without ad-hoc DB role mutation.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from src.web.routes.auth import hash_password


@pytest.fixture
def admin_client(boss_user, db_pool, monkeypatch):
    """Boot the app with the seeded boss promoted to superadmin."""
    monkeypatch.setenv("SUPERADMIN_EMAILS", boss_user["email"])
    # Reload settings so the new env value is picked up.
    from src import config as cfg_mod
    cfg_mod.settings = cfg_mod.Settings()
    # Patch the module references that imported `settings` earlier.
    import src.web.deps as deps_mod
    import src.web.routes.oauth as oauth_mod
    deps_mod.settings = cfg_mod.settings
    oauth_mod.settings = cfg_mod.settings

    from src import main as main_mod
    with TestClient(main_mod.app) as client:
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
        assert r.status_code == 303
        yield client, boss_user, csrf


ADMIN_PAGES = [
    "/admin/bosses",
    "/admin/bot-accounts",
    "/admin/bot-accounts?tab=boss_owned",
    "/admin/models",
    "/admin/prompts",
    "/admin/note-templates",
    "/admin/llm-routes",
    "/admin/feature-budgets",
    "/admin/agent-triggers",
    "/admin/retrieval-pipelines",
    "/admin/audit-log",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_PAGES)
async def test_admin_page_renders_for_superadmin(admin_client, path):
    client, _, _ = admin_client
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


@pytest.mark.asyncio
async def test_admin_blocks_non_superadmin(boss_user, db_pool):
    """When no SUPERADMIN_EMAILS set, a plain boss must get 403 on /admin/*."""
    os.environ["SUPERADMIN_EMAILS"] = ""  # force empty for this test
    from src import config as cfg_mod
    cfg_mod.settings = cfg_mod.Settings()
    import src.web.deps as deps_mod
    deps_mod.settings = cfg_mod.settings

    # Seed password before opening TestClient (we're still in the test loop).
    async with db_pool.acquire() as c:
        await c.execute(
            "UPDATE users SET password_hash=$1 WHERE id=$2",
            hash_password("pw"),
            boss_user["id"],
        )

    from src import main as main_mod
    with TestClient(main_mod.app) as client:
        client.get("/login")
        csrf = client.cookies.get("smart_csrf")
        client.post(
            "/login",
            data={"email": boss_user["email"], "password": "pw", "_csrf": csrf},
            headers={"X-CSRF-Token": csrf},
            follow_redirects=False,
        )

        r = client.get("/admin/bosses")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_model_audits(admin_client, db_pool, boss_user):
    client, _, csrf = admin_client
    import uuid

    model_name = f"test-model-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/admin/models",
        data={
            "name": model_name,
            "provider": "openai",
            "tier": "fast",
            "endpoint_kind": "openai_chat",
            "ctx_max": "128000",
            "capabilities": "chat,tools",
            "is_active": "on",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM models WHERE name=$1 AND provider=$2",
            model_name,
            "openai",
        )
        audit = await c.fetchrow(
            "SELECT * FROM admin_audit_log WHERE action='create_model' ORDER BY id DESC LIMIT 1"
        )
    assert row is not None and row["tier"] == "fast"
    assert audit is not None and audit["actor_user_id"] == boss_user["id"]
