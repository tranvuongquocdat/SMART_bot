"""Integration tests for reminders CRUD endpoints.

  GET    /api/v1/admin/reminders          (list)
  POST   /api/v1/admin/reminders          (create)
  PATCH  /api/v1/admin/reminders/:id      (update due_at / status)
  DELETE /api/v1/admin/reminders/:id      (hard delete)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-reminders"
DUE_AT = "2030-12-31T10:00:00Z"
DUE_AT_SNOOZE = "2031-01-01T11:00:00Z"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


_DUE_AT_DT = datetime(2030, 12, 31, 10, 0, 0, tzinfo=timezone.utc)
_DUE_AT_SNOOZE_DT = datetime(2031, 1, 1, 11, 0, 0, tzinfo=timezone.utc)


def _seed_reminder(clean_db, boss_id: int, text: str = "Test reminder") -> int:
    """Insert a reminder row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO scheduled_reminders
                  (boss_id, text, due_at, scope, status, created_by_op)
                VALUES ($1, $2, $3, 'dm', 'pending', 'test')
                RETURNING id
                """,
                boss_id, text, _DUE_AT_DT,
            )
    return asyncio.get_event_loop().run_until_complete(_async())


# ---------------------------------------------------------------------------
# GET /api/v1/admin/reminders
# ---------------------------------------------------------------------------

def test_list_reminders_unauthenticated(client):
    r = client.get("/api/v1/admin/reminders")
    assert r.status_code == 401


def test_list_reminders_returns_own(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id, "My reminder")
    r = client.get("/api/v1/admin/reminders?status=pending")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    ids = [x["id"] for x in body]
    assert rid in ids
    item = next(x for x in body if x["id"] == rid)
    assert item["text"] == "My reminder"
    assert item["status"] == "pending"
    assert "due_at" in item


# ---------------------------------------------------------------------------
# POST /api/v1/admin/reminders
# ---------------------------------------------------------------------------

def test_create_reminder_no_csrf(client, logged_in_boss):
    r = client.post(
        "/api/v1/admin/reminders",
        json={"text": "Hello", "due_at": DUE_AT},
    )
    assert r.status_code == 403


def test_create_reminder_happy_path(client, logged_in_boss, clean_db):
    headers = _csrf(client)
    r = client.post(
        "/api/v1/admin/reminders",
        json={"text": "Nhắc họp", "due_at": DUE_AT, "scope": "dm"},
        headers=headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["text"] == "Nhắc họp"
    assert body["status"] == "pending"
    assert "id" in body

    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT text FROM scheduled_reminders WHERE id=$1", body["id"]
            )
    assert asyncio.get_event_loop().run_until_complete(_check()) == "Nhắc họp"


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/reminders/:id
# ---------------------------------------------------------------------------

def test_patch_reminder_no_csrf(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id)
    r = client.patch(
        f"/api/v1/admin/reminders/{rid}",
        json={"status": "done"},
    )
    assert r.status_code == 403


def test_patch_reminder_mark_done(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id)
    headers = _csrf(client)
    r = client.patch(
        f"/api/v1/admin/reminders/{rid}",
        json={"status": "done"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_patch_reminder_snooze(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id)
    headers = _csrf(client)
    r = client.patch(
        f"/api/v1/admin/reminders/{rid}",
        json={"due_at": DUE_AT_SNOOZE},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert "2031" in body["due_at"]


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/reminders/:id
# ---------------------------------------------------------------------------

def test_delete_reminder_no_csrf(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id)
    r = client.delete(f"/api/v1/admin/reminders/{rid}")
    assert r.status_code == 403


def test_delete_reminder_happy_path(client, logged_in_boss, clean_db):
    rid = _seed_reminder(clean_db, logged_in_boss.boss_id)
    headers = _csrf(client)
    r = client.delete(f"/api/v1/admin/reminders/{rid}", headers=headers)
    assert r.status_code == 204

    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT id FROM scheduled_reminders WHERE id=$1", rid
            )
    assert asyncio.get_event_loop().run_until_complete(_check()) is None
