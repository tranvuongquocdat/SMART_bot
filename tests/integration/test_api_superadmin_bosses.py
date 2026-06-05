"""Tests for SP2-10 bosses CRUD endpoints:
  GET    /api/v1/superadmin/bosses
  POST   /api/v1/superadmin/bosses
  PATCH  /api/v1/superadmin/bosses/:id
  DELETE /api/v1/superadmin/bosses/:id
"""
from __future__ import annotations

import asyncio

import pytest

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-bosses"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_boss(clean_db):
    """Insert a boss user (not the logged-in superadmin) and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            uid = await c.fetchval(
                """
                INSERT INTO users (email, name, role)
                VALUES ($1, $2, 'boss')
                RETURNING id
                """,
                "seeded-boss@example.com",
                "Seeded Boss",
            )
            return int(uid)

    uid = asyncio.get_event_loop().run_until_complete(_async())
    return type("BossUser", (), {"id": uid})()


# ---------------------------------------------------------------------------
# GET /bosses
# ---------------------------------------------------------------------------

def test_list_bosses_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/bosses")
    assert r.status_code == 403


def test_list_bosses_returns_list(client, logged_in_superadmin, seed_boss):
    r = client.get("/api/v1/superadmin/bosses")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    # logged_in_superadmin + seed_boss should both appear
    assert len(data) >= 2
    ids = {row["id"] for row in data}
    assert logged_in_superadmin.boss_id in ids
    assert seed_boss.id in ids
    row = next(x for x in data if x["id"] == seed_boss.id)
    assert row["email"] == "seeded-boss@example.com"
    assert row["role"] == "boss"
    assert "created_at" in row


# ---------------------------------------------------------------------------
# POST /bosses
# ---------------------------------------------------------------------------

def test_create_boss_requires_superadmin(client, logged_in_boss):
    r = client.post(
        "/api/v1/superadmin/bosses",
        json={"email": "new@example.com", "name": "New Boss", "role": "boss"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_create_boss_success(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/bosses",
        json={"email": "newboss@example.com", "name": "New Boss", "role": "boss"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert isinstance(data["id"], int)


def test_create_boss_duplicate_email(client, logged_in_superadmin, seed_boss):
    r = client.post(
        "/api/v1/superadmin/bosses",
        json={"email": "seeded-boss@example.com", "role": "boss"},
        headers=_csrf(client),
    )
    assert r.status_code == 409


def test_create_boss_invalid_role(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/bosses",
        json={"email": "role-bad@example.com", "role": "member"},
        headers=_csrf(client),
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /bosses/:id
# ---------------------------------------------------------------------------

def test_patch_boss_requires_superadmin(client, logged_in_boss, seed_boss):
    r = client.patch(
        f"/api/v1/superadmin/bosses/{seed_boss.id}",
        json={"name": "Renamed"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_patch_boss_success(client, logged_in_superadmin, seed_boss):
    r = client.patch(
        f"/api/v1/superadmin/bosses/{seed_boss.id}",
        json={"name": "Renamed Boss", "tz": "Asia/Tokyo"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["id"] == seed_boss.id


def test_patch_boss_not_found(client, logged_in_superadmin):
    r = client.patch(
        "/api/v1/superadmin/bosses/999999",
        json={"name": "Ghost"},
        headers=_csrf(client),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /bosses/:id
# ---------------------------------------------------------------------------

def test_delete_boss_requires_superadmin(client, logged_in_boss, seed_boss):
    r = client.delete(
        f"/api/v1/superadmin/bosses/{seed_boss.id}",
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_delete_boss_success(client, logged_in_superadmin, seed_boss):
    r = client.delete(
        f"/api/v1/superadmin/bosses/{seed_boss.id}",
        headers=_csrf(client),
    )
    assert r.status_code == 204


def test_delete_boss_not_found(client, logged_in_superadmin):
    r = client.delete(
        "/api/v1/superadmin/bosses/999999",
        headers=_csrf(client),
    )
    assert r.status_code == 404


def test_delete_boss_self_delete_blocked(client, logged_in_superadmin):
    r = client.delete(
        f"/api/v1/superadmin/bosses/{logged_in_superadmin.boss_id}",
        headers=_csrf(client),
    )
    assert r.status_code == 400
