"""Subscription payment seam: confirm_and_activate/reject — đường kích hoạt
DUY NHẤT cho manual duyệt tay lẫn webhook auto sau này.

Khoá các invariant: kích hoạt đúng gói + hạn theo billing_months; idempotent
(duyệt đúp / webhook bắn trùng chỉ kích hoạt 1 lần); provider fields ghi lại
nguồn xác nhận; notify theo ui_language của boss.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.services.subscription_payment import (
    RequestNotPending,
    confirm_and_activate,
    reject_request,
)


async def _boss(pool, email, ui_language="vi"):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role, ui_language) "
            "VALUES ($1, 'Sếp Pay', 'boss', $2) RETURNING id",
            email, ui_language,
        )


async def _plan(pool, name="paytest"):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO plans (name, label, limits_json, prices_json, sort_order)
            VALUES ($1, 'Pay Test', '{"max_active_groups": 9, "duration_days": 30}',
                    '{"1": 100000, "3": 270000, "12": 960000}', 99)
            ON CONFLICT (name) DO UPDATE SET label=EXCLUDED.label
            RETURNING id
            """,
            name,
        )


async def _request(pool, boss_id, plan_id, months=3):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO subscription_requests
              (boss_id, plan_id, status, billing_months, amount_paid_vnd, transfer_content)
            VALUES ($1, $2, 'pending', $3, 270000, $4)
            RETURNING id
            """,
            boss_id, plan_id, months, f"SMART PAYTEST U{boss_id}",
        )


@pytest.mark.asyncio
async def test_activate_sets_plan_expiry_and_provider(clean_db):
    boss = await _boss(clean_db, "pay1@x.test")
    plan = await _plan(clean_db)
    req = await _request(clean_db, boss, plan, months=3)

    out = await confirm_and_activate(clean_db, req)
    assert out == {"boss_id": boss, "plan_id": plan}

    async with clean_db.acquire() as c:
        user = await c.fetchrow(
            "SELECT plan_id, subscription_status, subscription_expiry FROM users WHERE id=$1",
            boss)
        r = await c.fetchrow(
            "SELECT status, payment_provider, provider_txn_id, reviewed_at "
            "FROM subscription_requests WHERE id=$1", req)
        notif = await c.fetchrow(
            "SELECT title FROM notifications WHERE boss_id=$1 ORDER BY id DESC LIMIT 1",
            boss)
    assert user["plan_id"] == plan
    # 3 tháng ≈ 90 ngày (calendar months) — kiểm tra khoảng hợp lý
    expiry = user["subscription_expiry"]
    days = (expiry - datetime.now(timezone.utc)).days
    assert 85 <= days <= 95, f"expiry {expiry} (~{days}d) không khớp 3 tháng"
    assert r["status"] == "approved"
    assert r["payment_provider"] == "manual_bank"
    assert r["reviewed_at"] is not None
    assert notif["title"] == "Gói đã được kích hoạt"  # boss ui_language=vi


@pytest.mark.asyncio
async def test_double_activation_is_idempotent(clean_db):
    """Webhook bắn trùng / duyệt đúp: lần 2 phải RequestNotPending, gói chỉ áp 1 lần."""
    boss = await _boss(clean_db, "pay2@x.test")
    plan = await _plan(clean_db)
    req = await _request(clean_db, boss, plan)

    await confirm_and_activate(clean_db, req, provider="sepay", provider_txn_id="TXN-1")
    with pytest.raises(RequestNotPending):
        await confirm_and_activate(clean_db, req, provider="sepay", provider_txn_id="TXN-1")

    async with clean_db.acquire() as c:
        r = await c.fetchrow(
            "SELECT payment_provider, provider_txn_id FROM subscription_requests WHERE id=$1",
            req)
        n_notif = await c.fetchval(
            "SELECT count(*) FROM notifications WHERE boss_id=$1", boss)
    assert r["payment_provider"] == "sepay" and r["provider_txn_id"] == "TXN-1"
    assert n_notif == 1


@pytest.mark.asyncio
async def test_reject_notifies_in_boss_language(clean_db):
    boss = await _boss(clean_db, "pay3@x.test", ui_language="en")
    plan = await _plan(clean_db)
    req = await _request(clean_db, boss, plan)

    await reject_request(clean_db, req, reviewer_note="Sai số tiền")
    with pytest.raises(RequestNotPending):
        await reject_request(clean_db, req)

    async with clean_db.acquire() as c:
        status = await c.fetchval(
            "SELECT status FROM subscription_requests WHERE id=$1", req)
        notif = await c.fetchrow(
            "SELECT title, body FROM notifications WHERE boss_id=$1", boss)
        user_plan = await c.fetchval("SELECT plan_id FROM users WHERE id=$1", boss)
    assert status == "rejected"
    assert notif["title"] == "Subscription request rejected"  # ui_language=en
    assert notif["body"] == "Sai số tiền"
    assert user_plan is None  # không áp gói


@pytest.mark.asyncio
async def test_activation_failure_releases_claim(clean_db, monkeypatch):
    """apply_plan fail giữa chừng → request nhả về pending, duyệt lại được
    (không kẹt 'approved' mà gói chưa áp)."""
    import src.services.subscription as sub_svc

    boss = await _boss(clean_db, "pay4@x.test")
    plan = await _plan(clean_db)
    req = await _request(clean_db, boss, plan)

    async def _boom(*a, **kw):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(sub_svc, "apply_plan_to_user", _boom)
    with pytest.raises(RuntimeError, match="db hiccup"):
        await confirm_and_activate(clean_db, req)

    async with clean_db.acquire() as c:
        status = await c.fetchval(
            "SELECT status FROM subscription_requests WHERE id=$1", req)
    assert status == "pending"
    # và sau khi hết lỗi thì duyệt lại được bình thường
    monkeypatch.undo()
    await confirm_and_activate(clean_db, req)
