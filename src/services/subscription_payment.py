"""Subscription payment confirmation — đường kích hoạt DUY NHẤT cho mọi kênh.

User chốt (2026-07-02): thanh toán MANUAL (chuyển khoản + superadmin duyệt)
nhưng kiến trúc mở đường auto đa kênh. Hợp đồng cho provider tương lai:

    Webhook (SePay/Casso/PayOS...) nhận biến động/giao dịch
      → match ``transfer_content`` (SMART <PLAN> U<boss_id>) ra request pending
      → gọi ``confirm_and_activate(pool, req_id, provider='sepay',
                                   provider_txn_id=<mã gd>)``

Cùng một hàm với nút Duyệt của superadmin (provider='manual_bank') — mọi
side-effect (áp gói, hạn theo billing_months, notify) ở MỘT chỗ. Idempotency:
UPDATE có điều kiện ``status='pending'`` — webhook bắn trùng / duyệt đúp chỉ
kích hoạt một lần; unique index (provider, txn_id) chặn replay khác request.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MANUAL_PROVIDER = "manual_bank"


class RequestNotPending(Exception):
    """Request không tồn tại hoặc đã được xử lý (idempotent guard)."""


async def _notify_vi_en(pool, boss_id: int, *, title_vi, title_en, body_vi, body_en, link):
    """Notify theo ui_language CỦA BOSS (không phải của actor)."""
    from src.services import notifications

    async with pool.acquire() as c:
        lang = await c.fetchval("SELECT ui_language FROM users WHERE id=$1", boss_id)
    en = lang == "en"
    await notifications.notify_boss(
        pool, boss_id, kind="subscription",
        title=title_en if en else title_vi,
        body=body_en if en else body_vi,
        link=link,
    )


async def confirm_and_activate(
    pool,
    req_id: int,
    *,
    provider: str = MANUAL_PROVIDER,
    provider_txn_id: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """Xác nhận thanh toán + kích hoạt gói cho một request pending.

    Trả {boss_id, plan_id}. Raise ``RequestNotPending`` nếu request không ở
    trạng thái pending (đã duyệt/từ chối/không tồn tại) — caller webhook nên
    nuốt lỗi này (retry/trùng là bình thường), endpoint manual trả 400.
    """
    from src.services.subscription import apply_plan_to_user

    async with pool.acquire() as c:
        # Claim trước (idempotent) — race duyệt đúp / webhook trùng chỉ một
        # bên thắng; bên thua thấy 0 row.
        req = await c.fetchrow(
            """
            UPDATE subscription_requests
               SET status='approved', reviewed_at=NOW(),
                   payment_provider=$2, provider_txn_id=$3
             WHERE id=$1 AND status='pending'
            RETURNING boss_id, plan_id, billing_months
            """,
            req_id, provider, provider_txn_id,
        )
    if req is None:
        raise RequestNotPending(f"request {req_id} not pending")

    try:
        await apply_plan_to_user(
            pool, req["boss_id"], req["plan_id"], overrides or {},
            billing_months=req["billing_months"],
        )
    except Exception:
        # Áp gói fail sau khi đã claim → nhả về pending để duyệt lại được,
        # không kẹt request ở 'approved' mà gói chưa áp.
        async with pool.acquire() as c:
            await c.execute(
                "UPDATE subscription_requests SET status='pending', reviewed_at=NULL, "
                "payment_provider=$2, provider_txn_id=NULL WHERE id=$1",
                req_id, MANUAL_PROVIDER,
            )
        raise
    async with pool.acquire() as c:
        plan_label = await c.fetchval(
            "SELECT label FROM plans WHERE id=$1", req["plan_id"])
    await _notify_vi_en(
        pool, req["boss_id"],
        title_vi="Gói đã được kích hoạt",
        title_en="Plan subscription approved",
        body_vi=f"Gói {plan_label or ''} của bạn đã được kích hoạt.".strip(),
        body_en=f"Your plan {plan_label or ''} has been activated.".strip(),
        link="/app/admin/subscription",
    )
    log.info("subscription activated req=%s boss=%s provider=%s txn=%s",
             req_id, req["boss_id"], provider, provider_txn_id)
    return {"boss_id": req["boss_id"], "plan_id": req["plan_id"]}


async def reject_request(pool, req_id: int, *, reviewer_note: str = "") -> dict:
    """Từ chối một request pending + notify boss (vi/en)."""
    async with pool.acquire() as c:
        req = await c.fetchrow(
            """
            UPDATE subscription_requests
               SET status='rejected', reviewed_at=NOW(), reviewer_note=$2
             WHERE id=$1 AND status='pending'
            RETURNING boss_id
            """,
            req_id, reviewer_note,
        )
    if req is None:
        raise RequestNotPending(f"request {req_id} not pending")

    note = (reviewer_note or "").strip()
    await _notify_vi_en(
        pool, req["boss_id"],
        title_vi="Yêu cầu đăng ký gói bị từ chối",
        title_en="Subscription request rejected",
        body_vi=note or "Vui lòng kiểm tra lại thông tin chuyển khoản và gửi lại.",
        body_en=note or "Please double-check your payment details and submit again.",
        link="/app/admin/subscription",
    )
    return {"boss_id": req["boss_id"]}
