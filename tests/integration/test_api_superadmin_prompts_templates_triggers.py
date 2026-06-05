"""Tests for SP2-11 prompts, note-templates, agent-triggers CRUD endpoints."""
from __future__ import annotations

import asyncio
import json

import pytest

from src.web.security import CSRF_COOKIE

CSRF_TOK = "test-csrf-ptt"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF_TOK)
    return {"X-CSRF-Token": CSRF_TOK}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_prompt(clean_db):
    """Insert a prompt row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            pid = await c.fetchval(
                """
                INSERT INTO prompts (key, version, body, is_active, notes)
                VALUES ('test_key', 1, 'hello world', FALSE, 'seed note')
                RETURNING id
                """
            )
            return int(pid)
    return asyncio.get_event_loop().run_until_complete(_async())


@pytest.fixture
def seed_note_template(clean_db):
    """Insert a note_template row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            tid = await c.fetchval(
                """
                INSERT INTO note_templates (name, description, is_system, sections_json)
                VALUES ('Tmpl A', 'desc', FALSE, '[]'::jsonb)
                RETURNING id
                """
            )
            return int(tid)
    return asyncio.get_event_loop().run_until_complete(_async())


@pytest.fixture
def seed_agent_trigger(clean_db):
    """Insert an agent_trigger row and return its id."""
    async def _async():
        async with clean_db.acquire() as c:
            tid = await c.fetchval(
                """
                INSERT INTO agent_triggers (op_name, event_name, enabled)
                VALUES ('analyze', 'msg_received', TRUE)
                RETURNING id
                """
            )
            return int(tid)
    return asyncio.get_event_loop().run_until_complete(_async())


# ===========================================================================
# Prompts
# ===========================================================================

# GET /prompts

def test_list_prompts_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/prompts")
    assert r.status_code == 403


def test_list_prompts_returns_list(client, logged_in_superadmin, seed_prompt):
    r = client.get("/api/v1/superadmin/prompts")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    ids = [row["id"] for row in data]
    assert seed_prompt in ids
    row = next(x for x in data if x["id"] == seed_prompt)
    assert row["key"] == "test_key"
    assert row["version"] == 1


# GET /prompts/:id

def test_get_prompt_detail(client, logged_in_superadmin, seed_prompt):
    r = client.get(f"/api/v1/superadmin/prompts/{seed_prompt}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["body"] == "hello world"
    assert data["key"] == "test_key"


def test_get_prompt_not_found(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/prompts/999999")
    assert r.status_code == 404


# POST /prompts

def test_create_prompt_requires_superadmin(client, logged_in_boss):
    r = client.post(
        "/api/v1/superadmin/prompts",
        json={"key": "k1", "body": "body text"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_create_prompt_success(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/prompts",
        json={"key": "new_key", "body": "body text", "notes": "v1"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data
    assert isinstance(data["id"], int)


def test_create_prompt_auto_increments_version(client, logged_in_superadmin, seed_prompt, clean_db):
    # seed_prompt already has version=1 for key 'test_key'; new post should get version=2
    r = client.post(
        "/api/v1/superadmin/prompts",
        json={"key": "test_key", "body": "v2 body"},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    r2 = client.get(f"/api/v1/superadmin/prompts/{new_id}")
    assert r2.json()["version"] == 2


# PATCH /prompts/:id

def test_patch_prompt_requires_superadmin(client, logged_in_boss, seed_prompt):
    r = client.patch(
        f"/api/v1/superadmin/prompts/{seed_prompt}",
        json={"notes": "x"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_patch_prompt_update_notes(client, logged_in_superadmin, seed_prompt):
    r = client.patch(
        f"/api/v1/superadmin/prompts/{seed_prompt}",
        json={"notes": "updated note"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_patch_prompt_activate(client, logged_in_superadmin, seed_prompt):
    r = client.patch(
        f"/api/v1/superadmin/prompts/{seed_prompt}",
        json={"is_active": True},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/v1/superadmin/prompts/{seed_prompt}")
    assert r2.json()["is_active"] is True


def test_patch_prompt_not_found(client, logged_in_superadmin):
    r = client.patch(
        "/api/v1/superadmin/prompts/999999",
        json={"notes": "x"},
        headers=_csrf(client),
    )
    assert r.status_code == 404


# DELETE /prompts/:id

def test_delete_prompt_requires_superadmin(client, logged_in_boss, seed_prompt):
    r = client.delete(f"/api/v1/superadmin/prompts/{seed_prompt}", headers=_csrf(client))
    assert r.status_code == 403


def test_delete_prompt_success(client, logged_in_superadmin, seed_prompt):
    r = client.delete(f"/api/v1/superadmin/prompts/{seed_prompt}", headers=_csrf(client))
    assert r.status_code == 204


def test_delete_prompt_not_found(client, logged_in_superadmin):
    r = client.delete("/api/v1/superadmin/prompts/999999", headers=_csrf(client))
    assert r.status_code == 404


# ===========================================================================
# Note templates
# ===========================================================================

# GET /note-templates

def test_list_note_templates_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/note-templates")
    assert r.status_code == 403


def test_list_note_templates_returns_list(client, logged_in_superadmin, seed_note_template):
    r = client.get("/api/v1/superadmin/note-templates")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    ids = [row["id"] for row in data]
    assert seed_note_template in ids


# POST /note-templates

def test_create_note_template_requires_superadmin(client, logged_in_boss):
    r = client.post(
        "/api/v1/superadmin/note-templates",
        json={"name": "T1"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_create_note_template_success(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/note-templates",
        json={"name": "New Template", "description": "desc", "sections_json": []},
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data


# PATCH /note-templates/:id

def test_patch_note_template_requires_superadmin(client, logged_in_boss, seed_note_template):
    r = client.patch(
        f"/api/v1/superadmin/note-templates/{seed_note_template}",
        json={"name": "X"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_patch_note_template_success(client, logged_in_superadmin, seed_note_template):
    r = client.patch(
        f"/api/v1/superadmin/note-templates/{seed_note_template}",
        json={"name": "Renamed", "description": "new desc"},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_patch_note_template_not_found(client, logged_in_superadmin):
    r = client.patch(
        "/api/v1/superadmin/note-templates/999999",
        json={"name": "X"},
        headers=_csrf(client),
    )
    assert r.status_code == 404


# DELETE /note-templates/:id

def test_delete_note_template_requires_superadmin(client, logged_in_boss, seed_note_template):
    r = client.delete(
        f"/api/v1/superadmin/note-templates/{seed_note_template}",
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_delete_note_template_success(client, logged_in_superadmin, seed_note_template):
    r = client.delete(
        f"/api/v1/superadmin/note-templates/{seed_note_template}",
        headers=_csrf(client),
    )
    assert r.status_code == 204


def test_delete_note_template_not_found(client, logged_in_superadmin):
    r = client.delete("/api/v1/superadmin/note-templates/999999", headers=_csrf(client))
    assert r.status_code == 404


# ===========================================================================
# Agent triggers
# ===========================================================================

# GET /agent-triggers

def test_list_agent_triggers_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/agent-triggers")
    assert r.status_code == 403


def test_list_agent_triggers_returns_list(client, logged_in_superadmin, seed_agent_trigger):
    r = client.get("/api/v1/superadmin/agent-triggers")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    ids = [row["id"] for row in data]
    assert seed_agent_trigger in ids
    row = next(x for x in data if x["id"] == seed_agent_trigger)
    assert row["op_name"] == "analyze"
    assert row["enabled"] is True


# POST /agent-triggers

def test_create_agent_trigger_requires_superadmin(client, logged_in_boss):
    r = client.post(
        "/api/v1/superadmin/agent-triggers",
        json={"op_name": "op", "event_name": "evt"},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_create_agent_trigger_success(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/agent-triggers",
        json={
            "op_name": "summarize",
            "event_name": "daily_tick",
            "enabled": True,
            "debounce_json": {"window_s": 30},
        },
        headers=_csrf(client),
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "id" in data


# PATCH /agent-triggers/:id

def test_patch_agent_trigger_requires_superadmin(client, logged_in_boss, seed_agent_trigger):
    r = client.patch(
        f"/api/v1/superadmin/agent-triggers/{seed_agent_trigger}",
        json={"enabled": False},
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_patch_agent_trigger_toggle(client, logged_in_superadmin, seed_agent_trigger):
    r = client.patch(
        f"/api/v1/superadmin/agent-triggers/{seed_agent_trigger}",
        json={"enabled": False},
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_patch_agent_trigger_not_found(client, logged_in_superadmin):
    r = client.patch(
        "/api/v1/superadmin/agent-triggers/999999",
        json={"enabled": False},
        headers=_csrf(client),
    )
    assert r.status_code == 404


# DELETE /agent-triggers/:id

def test_delete_agent_trigger_requires_superadmin(client, logged_in_boss, seed_agent_trigger):
    r = client.delete(
        f"/api/v1/superadmin/agent-triggers/{seed_agent_trigger}",
        headers=_csrf(client),
    )
    assert r.status_code == 403


def test_delete_agent_trigger_success(client, logged_in_superadmin, seed_agent_trigger):
    r = client.delete(
        f"/api/v1/superadmin/agent-triggers/{seed_agent_trigger}",
        headers=_csrf(client),
    )
    assert r.status_code == 204


def test_delete_agent_trigger_not_found(client, logged_in_superadmin):
    r = client.delete("/api/v1/superadmin/agent-triggers/999999", headers=_csrf(client))
    assert r.status_code == 404
