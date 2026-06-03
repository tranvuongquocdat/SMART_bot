"""Tests for GET /api/v1/me."""
from __future__ import annotations


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
