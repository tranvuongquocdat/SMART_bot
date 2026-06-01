"""G4: settings/ai — 3 slot model picker + BYO API keys (Fernet-encrypted) + cost cap."""

from __future__ import annotations

import asyncio
import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.config import settings
from src.web.routes.auth import hash_password


@pytest.fixture
def logged_in_client(boss_user, db_pool):
    """Same pattern as G2: boss logs in via TestClient, fixture yields csrf token."""
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


async def _seed_model(pool, name: str, tier: str, capabilities: list[str]) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO models
              (name, provider, endpoint_kind, tier, ctx_max, capabilities, is_active)
            VALUES ($1, 'openai', 'openai_chat', $2, 128000, $3::jsonb, TRUE)
            RETURNING id
            """,
            name,
            tier,
            json.dumps(capabilities),
        )


@pytest.mark.asyncio
async def test_settings_ai_renders(logged_in_client):
    client, _, _ = logged_in_client
    r = client.get("/app/settings/ai")
    assert r.status_code == 200
    assert "smart" in r.text.lower() and "fast" in r.text.lower()


@pytest.mark.asyncio
async def test_settings_ai_save_slots_and_cap(logged_in_client, db_pool, boss_user):
    import uuid
    suf = uuid.uuid4().hex[:6]
    smart_id = await _seed_model(db_pool, f"s-{suf}", "smart", ["chat", "tools", "vision"])
    fast_id = await _seed_model(db_pool, f"f-{suf}", "fast", ["chat"])

    client, _, csrf = logged_in_client
    r = client.post(
        "/app/settings/ai",
        data={
            "smart_model_id": str(smart_id),
            "fast_model_id": str(fast_id),
            "vision_model_id": "",
            "cost_cap_usd_daily": "3.5",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT smart_model_id, fast_model_id, vision_model_id, cost_cap_usd_daily "
            "FROM users WHERE id=$1",
            boss_user["id"],
        )
    assert row["smart_model_id"] == smart_id
    assert row["fast_model_id"] == fast_id
    assert row["vision_model_id"] is None
    assert float(row["cost_cap_usd_daily"]) == 3.5


@pytest.mark.asyncio
async def test_settings_ai_save_keys_encrypted(logged_in_client, db_pool, boss_user):
    client, _, csrf = logged_in_client
    r = client.post(
        "/app/settings/ai/keys",
        data={
            "key_openai": "sk-test-12345",
            "key_groq": "",
            "key_gemini": "",
            "_csrf": csrf,
        },
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    async with db_pool.acquire() as c:
        blob = await c.fetchval(
            "SELECT api_keys_enc FROM users WHERE id=$1", boss_user["id"]
        )
    assert blob is not None
    f = Fernet(settings.FERNET_KEY.encode())
    data = json.loads(f.decrypt(bytes(blob)).decode())
    assert data == {"openai": "sk-test-12345"}


@pytest.mark.asyncio
async def test_settings_ai_clear_key(logged_in_client, db_pool, boss_user):
    client, _, csrf = logged_in_client
    # Save first.
    client.post(
        "/app/settings/ai/keys",
        data={"key_openai": "sk-x", "_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    # Now clear.
    r = client.post(
        "/app/settings/ai/keys",
        data={"clear_openai": "on", "_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    async with db_pool.acquire() as c:
        blob = await c.fetchval(
            "SELECT api_keys_enc FROM users WHERE id=$1", boss_user["id"]
        )
    f = Fernet(settings.FERNET_KEY.encode())
    data = json.loads(f.decrypt(bytes(blob)).decode())
    assert "openai" not in data


@pytest.mark.asyncio
async def test_test_key_invalid_provider(logged_in_client):
    client, _, csrf = logged_in_client
    r = client.post(
        "/api/ai/test-key",
        data={"provider": "bogus", "api_key": "x", "_csrf": csrf},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["status"] == "invalid_provider"
