"""Integration tests for Projects + Action Items CRUD endpoints.

  GET    /api/v1/admin/projects
  POST   /api/v1/admin/projects
  DELETE /api/v1/admin/projects/:id
  GET    /api/v1/admin/action-items (with filters)
  PATCH  /api/v1/admin/action-items/:id
"""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-projects"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_project(clean_db, boss_id: int, name: str = "Test Project") -> int:
    async def _a():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "INSERT INTO projects (boss_id, name) VALUES ($1, $2) RETURNING id",
                boss_id, name,
            )
    return asyncio.get_event_loop().run_until_complete(_a())


def _seed_group(clean_db, boss_id: int) -> int:
    async def _a():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                VALUES ($1, 'zalo', 'zalo-proj-test-1', 'Proj Group')
                ON CONFLICT (boss_id, provider, chat_id) DO UPDATE
                  SET group_name = EXCLUDED.group_name
                RETURNING id
                """,
                boss_id,
            )
    return asyncio.get_event_loop().run_until_complete(_a())


def _seed_action_item(clean_db, boss_id: int, group_id: int,
                      text: str = "Do something", status: str = "open",
                      project_id: int | None = None) -> int:
    async def _a():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO action_items
                  (boss_id, group_note_id, text, status, source, project_id)
                VALUES ($1, $2, $3, $4, 'test', $5)
                RETURNING id
                """,
                boss_id, group_id, text, status, project_id,
            )
    return asyncio.get_event_loop().run_until_complete(_a())


# ===========================================================================
# GET /api/v1/admin/projects
# ===========================================================================

def test_list_projects_unauthenticated(client):
    r = client.get("/api/v1/admin/projects")
    assert r.status_code == 401


def test_list_projects_returns_own(client, logged_in_boss, clean_db):
    _seed_project(clean_db, logged_in_boss.boss_id, "Alpha")
    _seed_project(clean_db, logged_in_boss.boss_id, "Beta")
    r = client.get("/api/v1/admin/projects")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Alpha" in names and "Beta" in names


# ===========================================================================
# POST /api/v1/admin/projects
# ===========================================================================

def test_create_project_ok(client, logged_in_boss, clean_db):
    r = client.post(
        "/api/v1/admin/projects",
        json={"name": "New Project", "description": "desc"},
        headers=_csrf(client),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "New Project"
    assert body["description"] == "desc"
    assert body["items_count"] == 0


def test_create_project_csrf_required(client, logged_in_boss, clean_db):
    r = client.post("/api/v1/admin/projects", json={"name": "X"})
    assert r.status_code == 403


# ===========================================================================
# DELETE /api/v1/admin/projects/:id
# ===========================================================================

def test_delete_project_ok(client, logged_in_boss, clean_db):
    pid = _seed_project(clean_db, logged_in_boss.boss_id, "ToDelete")
    r = client.delete(f"/api/v1/admin/projects/{pid}", headers=_csrf(client))
    assert r.status_code == 204
    # Confirm gone
    r2 = client.get("/api/v1/admin/projects")
    ids = [p["id"] for p in r2.json()]
    assert pid not in ids


def test_delete_project_not_found(client, logged_in_boss, clean_db):
    r = client.delete("/api/v1/admin/projects/999999", headers=_csrf(client))
    assert r.status_code == 404


# ===========================================================================
# GET /api/v1/admin/action-items
# ===========================================================================

def test_list_action_items_unauthenticated(client):
    r = client.get("/api/v1/admin/action-items")
    assert r.status_code == 401


def test_list_action_items_filter_done(client, logged_in_boss, clean_db):
    gid = _seed_group(clean_db, logged_in_boss.boss_id)
    _seed_action_item(clean_db, logged_in_boss.boss_id, gid, "Task open", "open")
    _seed_action_item(clean_db, logged_in_boss.boss_id, gid, "Task done", "done")

    r = client.get("/api/v1/admin/action-items?done=true")
    assert r.status_code == 200
    statuses = [x["status"] for x in r.json()]
    assert all(s == "done" for s in statuses)
    assert any(x["text"] == "Task done" for x in r.json())

    r2 = client.get("/api/v1/admin/action-items?done=false")
    statuses2 = [x["status"] for x in r2.json()]
    assert all(s == "open" for s in statuses2)


def test_list_action_items_filter_project(client, logged_in_boss, clean_db):
    gid = _seed_group(clean_db, logged_in_boss.boss_id)
    pid = _seed_project(clean_db, logged_in_boss.boss_id, "ProjFilter")
    _seed_action_item(clean_db, logged_in_boss.boss_id, gid, "In project", project_id=pid)
    _seed_action_item(clean_db, logged_in_boss.boss_id, gid, "No project")

    r = client.get(f"/api/v1/admin/action-items?project_id={pid}")
    assert r.status_code == 200
    texts = [x["text"] for x in r.json()]
    assert "In project" in texts
    assert "No project" not in texts


# ===========================================================================
# PATCH /api/v1/admin/action-items/:id
# ===========================================================================

def test_patch_action_item_done(client, logged_in_boss, clean_db):
    gid = _seed_group(clean_db, logged_in_boss.boss_id)
    iid = _seed_action_item(clean_db, logged_in_boss.boss_id, gid, "Toggle me")
    r = client.patch(
        f"/api/v1/admin/action-items/{iid}",
        json={"done": True},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_patch_action_item_not_found(client, logged_in_boss, clean_db):
    r = client.patch(
        "/api/v1/admin/action-items/999999",
        json={"done": True},
        headers=_csrf(client),
    )
    assert r.status_code == 404
