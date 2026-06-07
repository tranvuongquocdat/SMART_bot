"""Tests for SP2-12 audit log + retrieval pipelines API endpoints."""
from __future__ import annotations

import asyncio
import json

import pytest

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-ar"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_audit_log(clean_db, logged_in_superadmin):
    """Insert an audit log entry using the seeded superadmin user id."""
    async def _async():
        async with clean_db.acquire() as c:
            # Get a valid user id (the superadmin)
            uid = await c.fetchval("SELECT id FROM users LIMIT 1")
            await c.execute(
                """
                INSERT INTO admin_audit_log (actor_user_id, action, target_kind, target_id)
                VALUES ($1, 'update_model', 'models', '42')
                """,
                uid,
            )
    asyncio.get_event_loop().run_until_complete(_async())


@pytest.fixture
def seed_retrieval_pipeline(clean_db):
    """Insert a retrieval pipeline row and return its feature key."""
    async def _async():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO retrieval_pipelines (feature, stages_json, description)
                VALUES ('test_search', '[{"name":"bm25","k":50}]'::jsonb, 'seed pipeline')
                ON CONFLICT (feature) DO NOTHING
                """
            )
    asyncio.get_event_loop().run_until_complete(_async())
    return "test_search"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def test_audit_log_requires_superadmin(client, logged_in_boss):
    resp = client.get("/api/v1/superadmin/audit-log")
    assert resp.status_code == 403


def test_audit_log_returns_list(client, logged_in_superadmin, seed_audit_log):
    resp = client.get("/api/v1/superadmin/audit-log")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "next_cursor" in body
    assert isinstance(body["items"], list)
    # At least one item from seed
    assert len(body["items"]) >= 1
    item = body["items"][0]
    assert "action" in item
    assert "created_at" in item
    assert "actor_user_id" in item


def test_audit_log_filter_by_action(client, logged_in_superadmin, seed_audit_log):
    resp = client.get("/api/v1/superadmin/audit-log?action=update_model")
    assert resp.status_code == 200
    body = resp.json()
    assert all("update_model" in i["action"] for i in body["items"])


def test_audit_log_pagination_cursor(client, logged_in_superadmin, seed_audit_log):
    # Fetch with limit=1 to force a next_cursor if multiple rows exist
    resp = client.get("/api/v1/superadmin/audit-log?limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    # cursor may or may not be present depending on total rows — just assert structure
    assert "next_cursor" in body


# ---------------------------------------------------------------------------
# Retrieval pipelines — list
# ---------------------------------------------------------------------------

def test_list_retrieval_pipelines_requires_superadmin(client, logged_in_boss):
    resp = client.get("/api/v1/superadmin/retrieval-pipelines")
    assert resp.status_code == 403


def test_list_retrieval_pipelines_returns_list(client, logged_in_superadmin, seed_retrieval_pipeline):
    resp = client.get("/api/v1/superadmin/retrieval-pipelines")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    features = [r["feature"] for r in body]
    assert "test_search" in features
    row = next(r for r in body if r["feature"] == "test_search")
    assert "stages_json" in row
    assert "description" in row
    assert "updated_at" in row


# ---------------------------------------------------------------------------
# Retrieval pipelines — patch
# ---------------------------------------------------------------------------

def test_patch_retrieval_pipeline_requires_superadmin(client, logged_in_boss, seed_retrieval_pipeline):
    resp = client.patch(
        "/api/v1/superadmin/retrieval-pipelines/test_search",
        json={"description": "hacked"},
        headers=_csrf(client),
    )
    assert resp.status_code == 403


def test_patch_retrieval_pipeline_success(client, logged_in_superadmin, seed_retrieval_pipeline, clean_db):
    new_stages = [{"name": "rrf", "k": 20}]
    resp = client.patch(
        "/api/v1/superadmin/retrieval-pipelines/test_search",
        json={"stages_json": new_stages, "description": "updated desc"},
        headers=_csrf(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    # Verify DB updated
    async def _check():
        async with clean_db.acquire() as c:
            row = await c.fetchrow(
                "SELECT stages_json, description FROM retrieval_pipelines WHERE feature = 'test_search'"
            )
            return row
    row = asyncio.get_event_loop().run_until_complete(_check())
    assert row is not None
    assert json.loads(row["stages_json"]) == new_stages
    assert row["description"] == "updated desc"


def test_patch_retrieval_pipeline_not_found(client, logged_in_superadmin):
    resp = client.patch(
        "/api/v1/superadmin/retrieval-pipelines/nonexistent_feature",
        json={"description": "x"},
        headers=_csrf(client),
    )
    assert resp.status_code == 404
