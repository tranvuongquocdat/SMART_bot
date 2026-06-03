"""Tests for /api/v1/admin/groups/* endpoints."""
from __future__ import annotations


def test_group_detail_unauthenticated(client):
    r = client.get("/api/v1/admin/groups/1")
    assert r.status_code == 401


def test_group_detail_forbidden_for_non_owner(
    client, logged_in_boss, seed_group_owned_by_other
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_other.id}")
    assert r.status_code == 403


def test_group_detail_returns_meta(
    client, logged_in_boss, seed_group_owned_by_boss
):
    g = seed_group_owned_by_boss
    r = client.get(f"/api/v1/admin/groups/{g.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == g.id
    assert body["name"] == g.name
    assert "channel" in body
    assert "members_count" in body
    assert "messages_30d" in body
    assert "last_active_at" in body


def test_group_stats_returns_four_metrics(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/stats?range=7d")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"messages", "tasks", "reminders", "decisions"}


def test_group_members_returns_list(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/members")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_group_timeline_returns_messages_shape(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/timeline?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert "messages" in body
    assert "next_cursor" in body
    assert isinstance(body["messages"], list)


def test_group_summary_returns_body_shape(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/summary?date=today")
    assert r.status_code == 200
    body = r.json()
    assert "body" in body and "updated_at" in body


def test_group_items_returns_list(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/items?date=today")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_group_files_returns_list(
    client, logged_in_boss, seed_group_owned_by_boss
):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/files?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
