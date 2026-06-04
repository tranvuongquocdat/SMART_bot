"""Tests for new SP2-4 endpoints:
  GET  /api/v1/admin/groups          (list)
  POST /api/v1/admin/groups          (create)
  DELETE /api/v1/admin/groups/:id    (delete)
  POST /api/v1/admin/groups/:id/members   (add member)
  DELETE /api/v1/admin/groups/:id/members/:mid  (remove member)
  GET  /api/v1/admin/people?q=       (user search)
"""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-groups-list"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups  (list)
# ---------------------------------------------------------------------------

def test_groups_list_unauthenticated(client):
    r = client.get("/api/v1/admin/groups")
    assert r.status_code == 401


def test_groups_list_returns_own_groups(client, logged_in_boss, seed_group_owned_by_boss):
    r = client.get("/api/v1/admin/groups")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    ids = [g["id"] for g in body]
    assert seed_group_owned_by_boss.id in ids
    # check shape
    g = next(x for x in body if x["id"] == seed_group_owned_by_boss.id)
    assert "name" in g
    assert "channel" in g
    assert "members_count" in g


def test_groups_list_excludes_other_boss_groups(
    client, logged_in_boss, seed_group_owned_by_other
):
    r = client.get("/api/v1/admin/groups")
    assert r.status_code == 200
    ids = [g["id"] for g in r.json()]
    assert seed_group_owned_by_other.id not in ids


# ---------------------------------------------------------------------------
# POST /api/v1/admin/groups  (create)
# ---------------------------------------------------------------------------

def test_create_group_no_csrf(client):
    """Without CSRF cookie+header the mutation is rejected (403)."""
    r = client.post(
        "/api/v1/admin/groups",
        json={"name": "Test", "channel": "zalo"},
    )
    assert r.status_code == 403


def test_create_group_happy_path(client, logged_in_boss, clean_db):
    headers = _csrf(client)
    r = client.post(
        "/api/v1/admin/groups",
        json={"name": "Nhóm Mới", "channel": "zalo"},
        headers=headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Nhóm Mới"
    assert body["channel"] == "zalo"
    assert "id" in body
    # verify DB row exists
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT group_name FROM group_notes WHERE id=$1", body["id"]
            )
    name = asyncio.get_event_loop().run_until_complete(_check())
    assert name == "Nhóm Mới"


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/groups/:id
# ---------------------------------------------------------------------------

def test_delete_group_no_csrf(client, seed_group_owned_by_boss):
    """Without CSRF cookie+header the mutation is rejected (403)."""
    r = client.delete(
        f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}",
    )
    assert r.status_code == 403


def test_delete_group_happy_path(client, logged_in_boss, seed_group_owned_by_boss, clean_db):
    headers = _csrf(client)
    gid = seed_group_owned_by_boss.id
    r = client.delete(
        f"/api/v1/admin/groups/{gid}",
        headers=headers,
    )
    assert r.status_code == 204
    # verify gone
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT id FROM group_notes WHERE id=$1", gid
            )
    assert asyncio.get_event_loop().run_until_complete(_check()) is None


# ---------------------------------------------------------------------------
# POST /api/v1/admin/groups/:id/members  (add member)
# ---------------------------------------------------------------------------

def test_add_member_no_csrf(client):
    """Without CSRF cookie+header the mutation is rejected (403)."""
    r = client.post(
        "/api/v1/admin/groups/1/members",
        json={"display_name": "Alice"},
    )
    assert r.status_code == 403


def test_add_member_happy_path(client, logged_in_boss, seed_group_owned_by_boss, clean_db):
    headers = _csrf(client)
    gid = seed_group_owned_by_boss.id
    r = client.post(
        f"/api/v1/admin/groups/{gid}/members",
        json={"display_name": "Alice", "external_id": "ext-001", "role": "admin"},
        headers=headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["display_name"] == "Alice"
    assert body["role"] == "admin"
    assert "id" in body
    # verify in DB
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT display_name FROM group_members WHERE id=$1", body["id"]
            )
    assert asyncio.get_event_loop().run_until_complete(_check()) == "Alice"


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/groups/:id/members/:mid
# ---------------------------------------------------------------------------

def test_remove_member_no_csrf(client):
    """Without CSRF cookie+header the mutation is rejected (403)."""
    r = client.delete(
        "/api/v1/admin/groups/1/members/1",
    )
    assert r.status_code == 403


def test_remove_member_happy_path(client, logged_in_boss, seed_group_owned_by_boss, clean_db):
    headers = _csrf(client)
    gid = seed_group_owned_by_boss.id
    # First add a member
    r = client.post(
        f"/api/v1/admin/groups/{gid}/members",
        json={"display_name": "Bob"},
        headers=headers,
    )
    assert r.status_code == 201
    mid = r.json()["id"]
    # Now remove
    r2 = client.delete(
        f"/api/v1/admin/groups/{gid}/members/{mid}",
        headers=headers,
    )
    assert r2.status_code == 204
    # verify gone
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT id FROM group_members WHERE id=$1", mid
            )
    assert asyncio.get_event_loop().run_until_complete(_check()) is None


# ---------------------------------------------------------------------------
# GET /api/v1/admin/people?q=  (user search)
# ---------------------------------------------------------------------------

def test_people_search_unauthenticated(client):
    r = client.get("/api/v1/admin/people?q=alice")
    assert r.status_code == 401


def test_people_search_returns_matching_users(client, logged_in_boss, clean_db):
    # Seed a user to search for
    async def _seed():
        async with clean_db.acquire() as c:
            await c.execute(
                "INSERT INTO users (email, name, role) VALUES ($1, $2, 'boss') ON CONFLICT DO NOTHING",
                "searchable-alice@example.com",
                "Alice Searchable",
            )
    asyncio.get_event_loop().run_until_complete(_seed())

    r = client.get("/api/v1/admin/people?q=Alice")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = [u["display_name"] for u in body]
    assert any("Alice" in n for n in names)
    # check shape
    u = body[0]
    assert "id" in u
    assert "display_name" in u
