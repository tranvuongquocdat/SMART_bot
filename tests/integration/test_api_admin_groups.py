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


# ---------------------------------------------------------------------------
# PATCH /groups/:id/toggle-active
# ---------------------------------------------------------------------------

def test_toggle_group_active_off_and_on(client, logged_in_boss, seed_group_owned_by_boss):
    from src.web.security import CSRF_COOKIE

    client.cookies.set(CSRF_COOKIE, "csrf-group-toggle")
    headers = {"X-CSRF-Token": "csrf-group-toggle"}

    r = client.patch(
        f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/toggle-active",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r2 = client.patch(
        f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/toggle-active",
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["is_active"] is True

    # list reflects state
    r3 = client.get("/api/v1/admin/groups")
    g = next(x for x in r3.json() if x["id"] == seed_group_owned_by_boss.id)
    assert g["is_active"] is True


def test_toggle_group_active_respects_limit(client, logged_in_boss, seed_group_owned_by_boss, clean_db):
    import asyncio
    from src.web.security import CSRF_COOKIE

    async def _setup():
        async with clean_db.acquire() as c:
            pid = await c.fetchval(
                "INSERT INTO plans (name,label,limits_json) VALUES "
                "('tiny-grp','Tiny','{\"max_active_groups\": 1}'::jsonb) "
                "ON CONFLICT (name) DO UPDATE SET limits_json=EXCLUDED.limits_json RETURNING id"
            )
            await c.execute(
                "UPDATE users SET plan_id=$2 WHERE id=$1",
                logged_in_boss.boss_id, pid,
            )
            # group 1 inactive; group 2 active (fills the quota)
            await c.execute(
                "UPDATE group_notes SET is_active=FALSE WHERE id=$1",
                seed_group_owned_by_boss.id,
            )
            await c.execute(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name, is_active)
                VALUES ($1, 'zalo', 'zalo-group-test-002', 'Phòng 2', TRUE)
                ON CONFLICT (boss_id, provider, chat_id) DO UPDATE SET is_active=TRUE
                """,
                logged_in_boss.boss_id,
            )

    asyncio.get_event_loop().run_until_complete(_setup())

    client.cookies.set(CSRF_COOKIE, "csrf-group-limit")
    r = client.patch(
        f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/toggle-active",
        headers={"X-CSRF-Token": "csrf-group-limit"},
    )
    assert r.status_code == 400
    assert "giới hạn" in r.json()["detail"]


def test_toggle_group_active_other_boss_404(client, logged_in_boss, seed_group_owned_by_other):
    from src.web.security import CSRF_COOKIE

    client.cookies.set(CSRF_COOKIE, "csrf-group-404")
    r = client.patch(
        f"/api/v1/admin/groups/{seed_group_owned_by_other.id}/toggle-active",
        headers={"X-CSRF-Token": "csrf-group-404"},
    )
    assert r.status_code == 404
