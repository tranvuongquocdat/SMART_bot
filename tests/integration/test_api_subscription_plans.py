"""Tests for subscription plan listing, request create/cancel, limits endpoint."""
from __future__ import annotations

import asyncio
import io

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-sub"


def _csrf_headers(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _get_plan_id(clean_db, name: str) -> int:
    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval("SELECT id FROM plans WHERE name=$1", name)

    return asyncio.get_event_loop().run_until_complete(_())


def _set_boss_plan(clean_db, boss_id, plan_name):
    async def _():
        async with clean_db.acquire() as c:
            pid = await c.fetchval("SELECT id FROM plans WHERE name=$1", plan_name)
            await c.execute("UPDATE users SET plan_id=$2 WHERE id=$1", boss_id, pid)

    asyncio.get_event_loop().run_until_complete(_())


# ---------------------------------------------------------------------------
# GET /api/v1/admin/subscription/plans
# ---------------------------------------------------------------------------


def test_list_plans_unauthenticated(client):
    r = client.get("/api/v1/admin/subscription/plans")
    assert r.status_code == 401


def test_list_plans_returns_active_plans(client, logged_in_boss):
    r = client.get("/api/v1/admin/subscription/plans")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 4
    names = [p["name"] for p in body]
    assert "trial" in names and "pro" in names and "custom" in names
    plan = next(p for p in body if p["name"] == "trial")
    assert "label" in plan and "limits" in plan
    assert "max_active_groups" in plan["limits"]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/subscription/limits
# ---------------------------------------------------------------------------


def test_get_limits_unauthenticated(client):
    r = client.get("/api/v1/admin/subscription/limits")
    assert r.status_code == 401


def test_get_limits_returns_effective(client, logged_in_boss, clean_db):
    _set_boss_plan(clean_db, logged_in_boss.boss_id, "starter")

    # Fixture seeds all registry tools (17) — trim under starter's limit of 10
    # so the boss is not over-limit in this test.
    import asyncio as _asyncio

    async def _trim():
        async with clean_db.acquire() as c:
            await c.execute(
                """
                DELETE FROM boss_active_tools
                WHERE boss_id=$1 AND tool_name NOT IN (
                  SELECT tool_name FROM boss_active_tools
                  WHERE boss_id=$1 ORDER BY tool_name LIMIT 5
                )
                """,
                logged_in_boss.boss_id,
            )

    _asyncio.get_event_loop().run_until_complete(_trim())
    r = client.get("/api/v1/admin/subscription/limits")
    assert r.status_code == 200
    body = r.json()
    assert body["max_active_groups"] == 5
    assert body["max_active_tools"] == 10
    assert "over_limit" in body
    assert body["over_limit"]["any_over"] is False


# ---------------------------------------------------------------------------
# GET /api/v1/admin/subscription/requests
# ---------------------------------------------------------------------------


def test_list_requests_unauthenticated(client):
    r = client.get("/api/v1/admin/subscription/requests")
    assert r.status_code == 401


def test_list_requests_returns_empty_list(client, logged_in_boss):
    r = client.get("/api/v1/admin/subscription/requests")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# POST /api/v1/admin/subscription/requests
# ---------------------------------------------------------------------------


def test_create_request_no_csrf(client, logged_in_boss, clean_db):
    starter_id = _get_plan_id(clean_db, "starter")
    proof = io.BytesIO(b"fake image data")
    r = client.post(
        "/api/v1/admin/subscription/requests",
        data={"plan_id": starter_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
        files={"payment_proof": ("proof.jpg", proof, "image/jpeg")},
    )
    assert r.status_code == 403


def test_create_request_happy_path(client, logged_in_boss, clean_db):
    starter_id = _get_plan_id(clean_db, "starter")
    proof = io.BytesIO(b"fake image data")
    r = client.post(
        "/api/v1/admin/subscription/requests",
        data={
            "plan_id": starter_id,
            "note": "Muon nang cap",
            "amount_paid_vnd": 490000,
            "transfer_content": "SMART STARTER test",
        },
        files={"payment_proof": ("proof.jpg", proof, "image/jpeg")},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["plan_name"] == "starter"


def test_create_request_invalid_plan(client, logged_in_boss, clean_db):
    proof = io.BytesIO(b"fake")
    r = client.post(
        "/api/v1/admin/subscription/requests",
        data={"plan_id": 99999, "amount_paid_vnd": 1, "transfer_content": "X"},
        files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 404


def test_create_request_duplicate_pending(client, logged_in_boss, clean_db):
    starter_id = _get_plan_id(clean_db, "starter")

    def _submit():
        proof = io.BytesIO(b"fake")
        return client.post(
            "/api/v1/admin/subscription/requests",
            data={"plan_id": starter_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
            files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
            headers=_csrf_headers(client),
        )

    r1 = _submit()
    assert r1.status_code == 201
    r2 = _submit()
    assert r2.status_code == 409


def test_list_requests_after_creation(client, logged_in_boss, clean_db):
    starter_id = _get_plan_id(clean_db, "starter")
    proof = io.BytesIO(b"fake")
    client.post(
        "/api/v1/admin/subscription/requests",
        data={"plan_id": starter_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
        files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
        headers=_csrf_headers(client),
    )
    r = client.get("/api/v1/admin/subscription/requests")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["status"] == "pending"
    assert body[0]["plan_name"] == "starter"


# ---------------------------------------------------------------------------
# POST /api/v1/admin/subscription/requests/:id/cancel
# ---------------------------------------------------------------------------


def _create_pending(client, clean_db, plan_name="starter") -> int:
    plan_id = _get_plan_id(clean_db, plan_name)
    proof = io.BytesIO(b"fake")
    r = client.post(
        "/api/v1/admin/subscription/requests",
        data={"plan_id": plan_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
        files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_cancel_request_no_csrf(client, logged_in_boss, clean_db):
    req_id = _create_pending(client, clean_db)
    r = client.post(f"/api/v1/admin/subscription/requests/{req_id}/cancel")
    assert r.status_code == 403


def test_cancel_request_simple(client, logged_in_boss, clean_db):
    req_id = _create_pending(client, clean_db)
    r = client.post(
        f"/api/v1/admin/subscription/requests/{req_id}/cancel",
        data={"cancel_reason": "doi y", "refund_requested": "false"},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["refund_requested"] is False


def test_cancel_request_with_refund_qr(client, logged_in_boss, clean_db):
    req_id = _create_pending(client, clean_db)
    qr = io.BytesIO(b"qr image data")
    r = client.post(
        f"/api/v1/admin/subscription/requests/{req_id}/cancel",
        data={"cancel_reason": "doi y", "refund_requested": "true"},
        files={"refund_qr": ("qr.png", qr, "image/png")},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["refund_requested"] is True


def test_cancel_nonexistent_request(client, logged_in_boss):
    r = client.post(
        "/api/v1/admin/subscription/requests/99999/cancel",
        data={"cancel_reason": "test"},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 404


def test_cancel_already_cancelled(client, logged_in_boss, clean_db):
    req_id = _create_pending(client, clean_db)
    client.post(
        f"/api/v1/admin/subscription/requests/{req_id}/cancel",
        data={"cancel_reason": "first"},
        headers=_csrf_headers(client),
    )
    r = client.post(
        f"/api/v1/admin/subscription/requests/{req_id}/cancel",
        data={"cancel_reason": "second"},
        headers=_csrf_headers(client),
    )
    assert r.status_code == 400
