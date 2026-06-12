"""Superadmin quản lý sâu boss: overview, subscription, AI hộ sếp, chat history."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-sa-bosses"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _seed_boss(clean_db, email="deep-boss@test.local") -> int:
    async def _():
        async with clean_db.acquire() as c:
            boss_id = await c.fetchval(
                """
                INSERT INTO users (email, name, role)
                VALUES ($1, 'Deep Boss', 'boss')
                ON CONFLICT (email) DO UPDATE SET role='boss'
                RETURNING id
                """,
                email,
            )
            await c.execute(
                """
                UPDATE users SET plan_id=(SELECT id FROM plans WHERE name='starter')
                WHERE id=$1
                """,
                boss_id,
            )
            return boss_id

    return _run(_())


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def test_overview_requires_superadmin(client, logged_in_boss):
    r = client.get(f"/api/v1/superadmin/bosses/{logged_in_boss.boss_id}/overview")
    assert r.status_code in (401, 403)


def test_overview_shape(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.get(f"/api/v1/superadmin/bosses/{boss_id}/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "deep-boss@test.local"
    assert body["subscription"]["plan_name"] == "starter"
    for key in ("groups", "tools", "channels", "mcp"):
        assert "used" in body["usage"][key]
        assert "limit" in body["usage"][key]
    assert "cost_today_usd" in body["usage"]
    assert "msgs_in_30d" in body["usage"]


def test_overview_404(client, logged_in_superadmin):
    r = client.get("/api/v1/superadmin/bosses/999999/overview")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Subscription edit
# ---------------------------------------------------------------------------


def test_patch_subscription_overrides_take_effect(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.patch(
        f"/api/v1/superadmin/bosses/{boss_id}/subscription",
        json={
            "subscription_status": "active",
            "subscription_expiry": "2027-01-15T00:00:00+00:00",
            "overrides": {"max_active_groups": 99, "cost_cap_usd_daily": 9.5},
        },
        headers=_csrf(client),
    )
    assert r.status_code == 200, r.text

    # Limit hiệu lực phải phản ánh override
    from src.services.subscription import get_effective_limits

    limits = _run(get_effective_limits(clean_db, boss_id))
    assert limits.max_active_groups == 99
    assert limits.cost_cap_usd_daily == 9.5

    body = client.get(f"/api/v1/superadmin/bosses/{boss_id}/overview").json()
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["expiry"].startswith("2027-01-15")

    # Audit row được ghi
    async def _audit_count():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                SELECT COUNT(*) FROM admin_audit_log
                WHERE action='boss.subscription_updated' AND target_id=$1
                """,
                str(boss_id),
            )

    assert _run(_audit_count()) >= 1


def test_patch_subscription_clear_expiry(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.patch(
        f"/api/v1/superadmin/bosses/{boss_id}/subscription",
        json={"clear_expiry": True},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    body = client.get(f"/api/v1/superadmin/bosses/{boss_id}/overview").json()
    assert body["subscription"]["expiry"] is None


def test_patch_subscription_rejects_unknown_override(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.patch(
        f"/api/v1/superadmin/bosses/{boss_id}/subscription",
        json={"overrides": {"hack_key": 1}},
        headers=_csrf(client),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AI hộ sếp
# ---------------------------------------------------------------------------


def test_ai_settings_and_slot_on_behalf(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.get(f"/api/v1/superadmin/bosses/{boss_id}/ai")
    assert r.status_code == 200
    body = r.json()
    assert {s["slot"] for s in body["slots"]} == {"smart", "fast", "vision"}
    assert "keys" in body

    # Seed 1 model platform rồi gán hộ
    async def _seed_model():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO models (name, provider, endpoint_kind, tier, ctx_max, is_active)
                VALUES ('sa-test-model', 'groq', 'openai_compat', 'fast', 4096, TRUE)
                ON CONFLICT DO NOTHING RETURNING id
                """
            )

    mid = _run(_seed_model())
    if mid:
        r2 = client.patch(
            f"/api/v1/superadmin/bosses/{boss_id}/ai",
            json={"slot": "fast", "model_id": mid},
            headers=_csrf(client),
        )
        assert r2.status_code == 200
        body2 = client.get(f"/api/v1/superadmin/bosses/{boss_id}/ai").json()
        fast = next(s for s in body2["slots"] if s["slot"] == "fast")
        assert fast["model_id"] == mid


def test_ai_key_clear_on_behalf_audited_no_key_value(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    # clear không cần validate key sống
    r = client.patch(
        f"/api/v1/superadmin/bosses/{boss_id}/ai/keys",
        json={"provider": "groq", "clear": True},
        headers=_csrf(client),
    )
    assert r.status_code == 200

    async def _audit_payloads():
        async with clean_db.acquire() as c:
            rows = await c.fetch(
                """
                SELECT payload_json::text AS p FROM admin_audit_log
                WHERE action='boss.ai_key_updated' AND target_id=$1
                """,
                str(boss_id),
            )
            return [r["p"] for r in rows]

    payloads = _run(_audit_payloads())
    assert payloads
    assert all("api_key" not in (p or "") for p in payloads)


def test_own_model_on_behalf_requires_boss_key(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    r = client.post(
        f"/api/v1/superadmin/bosses/{boss_id}/ai/models",
        json={"provider": "groq", "name": "llama-3.3-70b-versatile", "tier": "fast"},
        headers=_csrf(client),
    )
    assert r.status_code == 409  # boss chưa có key groq


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


def _seed_chat(clean_db, boss_id: int):
    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name, content, is_active)
                VALUES ($1, 'telegram', 'g-100', 'Nhóm Dự Án X', '', TRUE)
                ON CONFLICT DO NOTHING
                """,
                boss_id,
            )
            await c.execute(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type,
                                      sender_provider_id, sender_name, text, ts)
                VALUES
                  ($1,'telegram','g-100','group','u1','Anh Tân','task A nhé', NOW() - INTERVAL '2 days'),
                  ($1,'telegram','g-100','group','u2','Chị Hoa','ok anh',     NOW() - INTERVAL '1 day')
                """,
                boss_id,
            )
            await c.execute(
                """
                INSERT INTO outbound_messages (boss_id, provider, chat_id, content, trigger, status)
                VALUES ($1, 'telegram', 'g-100', 'Đã ghi nhận task A', 'group', 'sent')
                """,
                boss_id,
            )

    _run(_())


def test_conversations_grouped_and_titled(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    _seed_chat(clean_db, boss_id)
    r = client.get(f"/api/v1/superadmin/bosses/{boss_id}/conversations")
    assert r.status_code == 200, r.text
    convs = r.json()
    assert len(convs) == 1
    conv = convs[0]
    assert conv["title"] == "Nhóm Dự Án X"
    assert conv["provider"] == "telegram"
    assert conv["msg_count"] == 3  # 2 in + 1 out

    # Mở xem chat phải được audit
    async def _audited():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                """
                SELECT COUNT(*) FROM admin_audit_log
                WHERE action='boss.chat_viewed' AND target_id=$1
                """,
                str(boss_id),
            )

    assert _run(_audited()) >= 1


def test_messages_order_directions_and_cursor(client, logged_in_superadmin, clean_db):
    boss_id = _seed_boss(clean_db)
    _seed_chat(clean_db, boss_id)
    r = client.get(
        f"/api/v1/superadmin/bosses/{boss_id}/messages",
        params={"provider": "telegram", "chat_id": "g-100"},
    )
    assert r.status_code == 200
    body = r.json()
    msgs = body["messages"]
    assert len(msgs) == 3
    # Cũ → mới, đủ cả 2 chiều, rõ người gửi
    assert msgs[0]["sender_name"] == "Anh Tân"
    assert msgs[-1]["direction"] == "out"
    ts_list = [m["ts"] for m in msgs]
    assert ts_list == sorted(ts_list)

    # Cursor: limit 2 → next_before trỏ tin cũ nhất của trang
    r2 = client.get(
        f"/api/v1/superadmin/bosses/{boss_id}/messages",
        params={"provider": "telegram", "chat_id": "g-100", "limit": 2},
    )
    body2 = r2.json()
    assert len(body2["messages"]) == 2
    assert body2["next_before"] == body2["messages"][0]["ts"]
