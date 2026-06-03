"""Tests for GET /api/v1/me."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from src import main as main_mod
from src.web.security import SESSION_COOKIE, make_session


@pytest.fixture
def client(clean_db):
    with TestClient(main_mod.app) as c:
        yield c


@pytest.fixture
def logged_in_boss(client, clean_db):
    """Seed a boss user and inject a session cookie into the test client."""

    async def _seed():
        async with clean_db.acquire() as c:
            row = await c.fetchrow(
                "INSERT INTO users (email, name, role) VALUES ($1, $2, 'boss') RETURNING id",
                "boss-test@example.com",
                "Test Boss",
            )
            return int(row["id"])

    uid = asyncio.get_event_loop().run_until_complete(_seed())
    client.cookies.set(SESSION_COOKIE, make_session(uid))
    return type("Boss", (), {"boss_id": uid, "user_role": "boss"})()


@pytest.fixture
def logged_in_superadmin(client, clean_db):
    """Seed a superadmin user and inject a session cookie into the test client."""

    async def _seed():
        async with clean_db.acquire() as c:
            row = await c.fetchrow(
                "INSERT INTO users (email, name, role) VALUES ($1, $2, 'superadmin') RETURNING id",
                "superadmin-test@example.com",
                "Test Superadmin",
            )
            return int(row["id"])

    uid = asyncio.get_event_loop().run_until_complete(_seed())
    client.cookies.set(SESSION_COOKIE, make_session(uid))
    return type("Sup", (), {"boss_id": uid, "user_role": "superadmin"})()


def test_me_unauthenticated_returns_401(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401


def test_me_returns_user_with_roles_for_boss(client, logged_in_boss):
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == logged_in_boss.boss_id
    assert "boss" in body["roles"]
    assert "superadmin" not in body["roles"]


def test_me_returns_both_roles_for_superadmin(client, logged_in_superadmin):
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert set(body["roles"]) == {"boss", "superadmin"}
