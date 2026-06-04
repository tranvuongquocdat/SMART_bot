"""Tests for /api/v1/admin/settings/* endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-token-settings"


def _csrf_headers():
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# /settings/account
# ---------------------------------------------------------------------------


def test_account_get_unauthenticated(client: TestClient):
    r = client.get("/api/v1/admin/settings/account")
    assert r.status_code == 401


def test_account_get_returns_profile(client: TestClient, logged_in_boss):
    r = client.get("/api/v1/admin/settings/account")
    assert r.status_code == 200
    body = r.json()
    assert "email" in body
    assert "name" in body
    assert "role" in body
    assert "google_linked" in body
    assert "subscription_status" in body
    assert "cost_cap_usd_daily" in body
    # Keys must NOT appear in account response
    assert "api_keys_enc" not in body


def test_account_patch_updates_name(client: TestClient, logged_in_boss):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    r = client.patch(
        "/api/v1/admin/settings/account",
        json={"name": "Updated Name"},
        headers=_csrf_headers(),
    )
    assert r.status_code == 200
    # Verify it was saved
    r2 = client.get("/api/v1/admin/settings/account")
    assert r2.json()["name"] == "Updated Name"


def test_account_patch_rejects_unknown_fields(client: TestClient, logged_in_boss):
    """Whitelist enforcement: unknown fields should be silently ignored (updated=0)."""
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    r = client.patch(
        "/api/v1/admin/settings/account",
        json={"role": "superadmin"},  # not in whitelist
        headers=_csrf_headers(),
    )
    assert r.status_code == 200
    # Role must not change
    r2 = client.get("/api/v1/admin/settings/account")
    assert r2.json()["role"] == "boss"


def test_account_patch_csrf_required(client: TestClient, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/settings/account",
        json={"name": "No CSRF"},
        # No CSRF header or cookie
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /settings/ai
# ---------------------------------------------------------------------------


def test_ai_get_unauthenticated(client: TestClient):
    r = client.get("/api/v1/admin/settings/ai")
    assert r.status_code == 401


def test_ai_get_returns_slots_and_masked_keys(client: TestClient, logged_in_boss):
    r = client.get("/api/v1/admin/settings/ai")
    assert r.status_code == 200
    body = r.json()
    assert "slots" in body
    assert "keys" in body
    assert "models" in body
    # Slots must have smart/fast/vision
    slot_names = {s["slot"] for s in body["slots"]}
    assert slot_names == {"smart", "fast", "vision"}
    # Keys shape: each provider has {present: bool}
    for prov, info in body["keys"].items():
        assert "present" in info
        assert "api_keys_enc" not in body  # raw key never exposed


def test_ai_patch_updates_slot(client: TestClient, logged_in_boss, clean_db):
    import asyncio

    # Seed a model in DB so we can reference it by id
    async def _seed():
        async with clean_db.acquire() as c:
            mid = await c.fetchval(
                """
                INSERT INTO models (name, provider, endpoint_kind, tier, ctx_max, is_active, is_platform_default)
                VALUES ($1, $2, $3, $4, $5, TRUE, FALSE)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                "test-fast-model",
                "groq",
                "openai_compat",
                "fast",
                4096,
            )
            return mid

    mid = asyncio.get_event_loop().run_until_complete(_seed())
    if mid is None:
        pytest.skip("model seed conflict — skip slot patch test")

    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    r = client.patch(
        "/api/v1/admin/settings/ai",
        json={"slot": "fast", "model_id": mid},
        headers=_csrf_headers(),
    )
    assert r.status_code == 200


def test_ai_patch_csrf_required(client: TestClient, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/settings/ai",
        json={"slot": "fast", "model_id": 1},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# /settings/ai/keys
# ---------------------------------------------------------------------------


def test_ai_keys_patch_saves_and_masks(client: TestClient, logged_in_boss):
    """Saving a key then reading back should show present=True, last_4 correct."""
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    r = client.patch(
        "/api/v1/admin/settings/ai/keys",
        json={"provider": "openai", "api_key": "sk-testABCD"},
        headers=_csrf_headers(),
    )
    assert r.status_code == 200
    # Now GET settings/ai and check key presence
    r2 = client.get("/api/v1/admin/settings/ai")
    keys = r2.json()["keys"]
    assert "openai" in keys
    assert keys["openai"]["present"] is True
    assert keys["openai"]["last_4"] == "ABCD"
    # Full key must not be present
    assert "sk-testABCD" not in str(keys)


def test_ai_keys_clear_removes_key(client: TestClient, logged_in_boss):
    """Clearing a key should remove it."""
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    # First save
    client.patch(
        "/api/v1/admin/settings/ai/keys",
        json={"provider": "groq", "api_key": "gsk_test1234"},
        headers=_csrf_headers(),
    )
    # Then clear
    r = client.patch(
        "/api/v1/admin/settings/ai/keys",
        json={"provider": "groq", "clear": True},
        headers=_csrf_headers(),
    )
    assert r.status_code == 200
    r2 = client.get("/api/v1/admin/settings/ai")
    keys = r2.json()["keys"]
    assert keys.get("groq", {}).get("present", False) is False


# ---------------------------------------------------------------------------
# /settings/general
# ---------------------------------------------------------------------------


def test_general_get_unauthenticated(client: TestClient):
    r = client.get("/api/v1/admin/settings/general")
    assert r.status_code == 401


def test_general_get_returns_fields(client: TestClient, logged_in_boss):
    r = client.get("/api/v1/admin/settings/general")
    assert r.status_code == 200
    body = r.json()
    assert "name" in body
    assert "tz" in body
    assert "language" in body


def test_general_patch_updates_tz(client: TestClient, logged_in_boss):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    r = client.patch(
        "/api/v1/admin/settings/general",
        json={"tz": "UTC", "language": "en"},
        headers=_csrf_headers(),
    )
    assert r.status_code == 200
    r2 = client.get("/api/v1/admin/settings/general")
    body = r2.json()
    assert body["tz"] == "UTC"
    assert body["language"] == "en"


def test_general_patch_csrf_required(client: TestClient, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/settings/general",
        json={"tz": "UTC"},
    )
    assert r.status_code == 403
