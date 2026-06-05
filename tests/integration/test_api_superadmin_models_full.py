"""Tests for SP2-8 superadmin endpoints:
  GET  /api/v1/superadmin/models
  POST /api/v1/superadmin/models
  PATCH /api/v1/superadmin/models/:id
  DELETE /api/v1/superadmin/models/:id
  PATCH /api/v1/superadmin/model-slots/:slot
  GET  /api/v1/superadmin/llm-routes
  PATCH /api/v1/superadmin/llm-routes/:id
  GET  /api/v1/superadmin/feature-budgets
  PATCH /api/v1/superadmin/feature-budgets/:feature
"""
from __future__ import annotations

import asyncio

import pytest

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-superadmin-models"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_model(clean_db):
    """Insert a model row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            mid = await c.fetchval(
                """
                INSERT INTO models
                  (name, provider, endpoint_kind, tier, ctx_max, capabilities,
                   is_platform_default, is_active)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8)
                RETURNING id
                """,
                "test-model-gpt4",
                "openai",
                "openai_chat",
                "smart",
                8000,
                "[]",
                False,
                True,
            )
            return int(mid)

    mid = asyncio.get_event_loop().run_until_complete(_async())
    return type("Model", (), {"id": mid})()


@pytest.fixture
def seed_llm_route(clean_db):
    """Insert a llm_route row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            rid = await c.fetchval(
                """
                INSERT INTO llm_routes
                  (feature, target_tier, fallback_chain, weight, is_active)
                VALUES ($1,$2,$3::jsonb,$4,$5)
                RETURNING id
                """,
                "chat_test",
                "smart",
                "[]",
                100,
                True,
            )
            return int(rid)

    rid = asyncio.get_event_loop().run_until_complete(_async())
    return type("LlmRoute", (), {"id": rid})()


@pytest.fixture
def seed_feature_budget(clean_db):
    """Upsert a feature_budget row and return the feature key."""
    async def _async():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO feature_budgets
                  (feature, max_input_tokens, max_output_tokens, trim_policy_json,
                   compression_strategy)
                VALUES ($1,$2,$3,$4::jsonb,$5)
                ON CONFLICT (feature) DO UPDATE
                  SET max_input_tokens = EXCLUDED.max_input_tokens,
                      max_output_tokens = EXCLUDED.max_output_tokens
                """,
                "budget_test",
                4096,
                1024,
                "{}",
                "none",
            )

    asyncio.get_event_loop().run_until_complete(_async())
    return "budget_test"


# ---------------------------------------------------------------------------
# GET /api/v1/superadmin/models
# ---------------------------------------------------------------------------

def test_list_models_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/models")
    assert r.status_code == 403


def test_list_models_returns_list(client, logged_in_superadmin, seed_model):
    r = client.get("/api/v1/superadmin/models")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = [m["id"] for m in data]
    assert seed_model.id in ids
    # Check expected fields
    row = next(m for m in data if m["id"] == seed_model.id)
    assert row["name"] == "test-model-gpt4"
    assert row["provider"] == "openai"
    assert row["tier"] == "smart"


# ---------------------------------------------------------------------------
# POST /api/v1/superadmin/models
# ---------------------------------------------------------------------------

def test_create_model_requires_superadmin(client, logged_in_boss):
    headers = _csrf(client)
    r = client.post("/api/v1/superadmin/models", json={
        "name": "x", "provider": "openai", "tier": "fast",
    }, headers=headers)
    assert r.status_code == 403


def test_create_model_succeeds(client, logged_in_superadmin, clean_db):
    headers = _csrf(client)
    r = client.post("/api/v1/superadmin/models", json={
        "name": "new-test-model",
        "provider": "groq",
        "tier": "fast",
        "ctx_max": 4096,
        "endpoint_kind": "openai_chat",
    }, headers=headers)
    assert r.status_code == 201
    assert "id" in r.json()


# ---------------------------------------------------------------------------
# PATCH /api/v1/superadmin/models/:id
# ---------------------------------------------------------------------------

def test_patch_model_requires_superadmin(client, logged_in_boss, seed_model):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/models/{seed_model.id}", json={
        "is_active": False,
    }, headers=headers)
    assert r.status_code == 403


def test_patch_model_updates_fields(client, logged_in_superadmin, seed_model, clean_db):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/models/{seed_model.id}", json={
        "notes": "patched-note",
        "is_active": False,
    }, headers=headers)
    assert r.status_code == 200
    # Verify via list
    lr = client.get("/api/v1/superadmin/models")
    row = next(m for m in lr.json() if m["id"] == seed_model.id)
    assert row["notes"] == "patched-note"
    assert row["is_active"] is False


# ---------------------------------------------------------------------------
# DELETE /api/v1/superadmin/models/:id
# ---------------------------------------------------------------------------

def test_delete_model_requires_superadmin(client, logged_in_boss, seed_model):
    headers = _csrf(client)
    r = client.delete(f"/api/v1/superadmin/models/{seed_model.id}", headers=headers)
    assert r.status_code == 403


def test_delete_model_succeeds(client, logged_in_superadmin, seed_model, clean_db):
    headers = _csrf(client)
    r = client.delete(f"/api/v1/superadmin/models/{seed_model.id}", headers=headers)
    assert r.status_code == 204
    # Should not appear in list
    lr = client.get("/api/v1/superadmin/models")
    ids = [m["id"] for m in lr.json()]
    assert seed_model.id not in ids


# ---------------------------------------------------------------------------
# PATCH /api/v1/superadmin/model-slots/:slot
# ---------------------------------------------------------------------------

def test_patch_slot_requires_superadmin(client, logged_in_boss, seed_model):
    headers = _csrf(client)
    r = client.patch("/api/v1/superadmin/model-slots/smart", json={
        "model_id": seed_model.id,
    }, headers=headers)
    assert r.status_code == 403


def test_patch_slot_sets_platform_default(client, logged_in_superadmin, seed_model, clean_db):
    headers = _csrf(client)
    r = client.patch("/api/v1/superadmin/model-slots/smart", json={
        "model_id": seed_model.id,
    }, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["slot"] == "smart"
    assert data["model_id"] == seed_model.id
    # Verify model-slots endpoint now returns it as active
    sr = client.get("/api/v1/superadmin/model-slots")
    smart_slot = next(s for s in sr.json() if s["slot"] == "smart")
    assert smart_slot["status"] == "active"
    assert smart_slot["model_id"] == seed_model.id


# ---------------------------------------------------------------------------
# GET /api/v1/superadmin/llm-routes
# ---------------------------------------------------------------------------

def test_list_llm_routes_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/llm-routes")
    assert r.status_code == 403


def test_list_llm_routes_returns_list(client, logged_in_superadmin, seed_llm_route):
    r = client.get("/api/v1/superadmin/llm-routes")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = [row["id"] for row in data]
    assert seed_llm_route.id in ids
    row = next(row for row in data if row["id"] == seed_llm_route.id)
    assert row["feature"] == "chat_test"
    assert row["target_tier"] == "smart"


# ---------------------------------------------------------------------------
# PATCH /api/v1/superadmin/llm-routes/:id
# ---------------------------------------------------------------------------

def test_patch_llm_route_requires_superadmin(client, logged_in_boss, seed_llm_route):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/llm-routes/{seed_llm_route.id}", json={
        "weight": 50,
    }, headers=headers)
    assert r.status_code == 403


def test_patch_llm_route_updates_fields(client, logged_in_superadmin, seed_llm_route, clean_db):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/llm-routes/{seed_llm_route.id}", json={
        "weight": 75,
        "is_active": False,
        "notes": "patched-route",
    }, headers=headers)
    assert r.status_code == 200
    # Verify via list
    lr = client.get("/api/v1/superadmin/llm-routes")
    row = next(row for row in lr.json() if row["id"] == seed_llm_route.id)
    assert row["weight"] == 75
    assert row["is_active"] is False
    assert row["notes"] == "patched-route"


# ---------------------------------------------------------------------------
# GET /api/v1/superadmin/feature-budgets
# ---------------------------------------------------------------------------

def test_list_feature_budgets_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/feature-budgets")
    assert r.status_code == 403


def test_list_feature_budgets_returns_list(client, logged_in_superadmin, seed_feature_budget):
    r = client.get("/api/v1/superadmin/feature-budgets")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    features = [row["feature"] for row in data]
    assert seed_feature_budget in features
    row = next(row for row in data if row["feature"] == seed_feature_budget)
    assert row["max_input_tokens"] == 4096
    assert row["max_output_tokens"] == 1024


# ---------------------------------------------------------------------------
# PATCH /api/v1/superadmin/feature-budgets/:feature
# ---------------------------------------------------------------------------

def test_patch_feature_budget_requires_superadmin(client, logged_in_boss, seed_feature_budget):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/feature-budgets/{seed_feature_budget}", json={
        "max_input_tokens": 8192,
    }, headers=headers)
    assert r.status_code == 403


def test_patch_feature_budget_updates_fields(
    client, logged_in_superadmin, seed_feature_budget, clean_db
):
    headers = _csrf(client)
    r = client.patch(f"/api/v1/superadmin/feature-budgets/{seed_feature_budget}", json={
        "max_input_tokens": 8192,
        "max_output_tokens": 2048,
        "compression_strategy": "truncate",
    }, headers=headers)
    assert r.status_code == 200
    # Verify via list
    lr = client.get("/api/v1/superadmin/feature-budgets")
    row = next(row for row in lr.json() if row["feature"] == seed_feature_budget)
    assert row["max_input_tokens"] == 8192
    assert row["max_output_tokens"] == 2048
    assert row["compression_strategy"] == "truncate"
