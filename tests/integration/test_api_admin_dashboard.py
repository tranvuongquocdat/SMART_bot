"""Tests for SP2-13 boss dashboard endpoint: GET /api/v1/admin/dashboard."""
from __future__ import annotations

import asyncio
import pytest


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_dashboard_requires_auth(client):
    resp = client.get("/api/v1/admin/dashboard")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Happy path — empty data set
# ---------------------------------------------------------------------------


def test_dashboard_returns_expected_shape(client, logged_in_boss):
    resp = client.get("/api/v1/admin/dashboard")
    assert resp.status_code == 200
    body = resp.json()

    # Top-level keys
    assert "recent_groups" in body
    assert "today_items" in body
    assert "stats_30d" in body
    assert "recent_activity" in body

    # Lists
    assert isinstance(body["recent_groups"], list)
    assert isinstance(body["today_items"], list)
    assert isinstance(body["recent_activity"], list)

    # stats_30d shape
    stats = body["stats_30d"]
    assert "messages" in stats
    assert "tasks" in stats
    assert "reminders" in stats
    assert "decisions" in stats
    assert all(isinstance(stats[k], int) for k in ("messages", "tasks", "reminders", "decisions"))

    # stats_prev_30d shape — counts for 60→30 days ago
    prev = body["stats_prev_30d"]
    assert "messages" in prev
    assert "tasks" in prev
    assert "reminders" in prev
    assert "decisions" in prev
    assert all(isinstance(prev[k], int) for k in ("messages", "tasks", "reminders", "decisions"))
    assert all(prev[k] >= 0 for k in ("messages", "tasks", "reminders", "decisions"))

    # With fresh DB everything is empty / zero
    assert body["recent_groups"] == []
    assert body["today_items"] == []
    assert stats["messages"] == 0
    assert stats["tasks"] == 0
    assert stats["reminders"] == 0


# ---------------------------------------------------------------------------
# Happy path — with seeded data
# ---------------------------------------------------------------------------


def test_dashboard_returns_seeded_data(client, logged_in_boss, clean_db):
    """Seed a group + action item and confirm they surface in the response."""

    def _seed():
        async def _async():
            async with clean_db.acquire() as c:
                gid = await c.fetchval(
                    """
                    INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                    VALUES ($1, 'zalo', 'zalo-dash-001', 'Nhóm Test Dashboard')
                    RETURNING id
                    """,
                    logged_in_boss.boss_id,
                )
                await c.execute(
                    """
                    INSERT INTO action_items (boss_id, group_note_id, text, status, source)
                    VALUES ($1, $2, 'Làm báo cáo tuần', 'open', 'manual')
                    """,
                    logged_in_boss.boss_id,
                    gid,
                )

        asyncio.get_event_loop().run_until_complete(_async())

    _seed()

    resp = client.get("/api/v1/admin/dashboard")
    assert resp.status_code == 200
    body = resp.json()

    groups = body["recent_groups"]
    assert len(groups) >= 1
    assert any(g["name"] == "Nhóm Test Dashboard" for g in groups)
    g = next(g for g in groups if g["name"] == "Nhóm Test Dashboard")
    assert g["provider"] == "zalo"
    assert "updated_at" in g

    items = body["today_items"]
    assert len(items) >= 1
    assert any(i["text"] == "Làm báo cáo tuần" for i in items)

    assert body["stats_30d"]["tasks"] >= 1
