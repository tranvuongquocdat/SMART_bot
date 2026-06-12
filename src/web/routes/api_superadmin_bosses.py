"""Superadmin — quản lý sâu từng boss: /api/v1/superadmin/bosses/{id}/*

  - overview        : usage tổng hợp (nhóm/tools/kênh/MCP/chi phí/tin nhắn)
  - subscription    : đổi gói, hạn, trạng thái, override limit per-boss
  - ai*             : config model hộ sếp (slots, BYO keys, model riêng)
  - conversations   : danh sách hội thoại của boss
  - messages        : tin nhắn một hội thoại (cursor theo ts, phân ngày ở FE)

Mọi thao tác ghi + mở xem chat đều ghi ``admin_audit_log`` (không log giá trị
key). Quyền: superadmin chỉnh hộ toàn quyền theo quyết định vận hành.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.repositories.admin_audit_log import AdminAuditLogRepo
from src.repositories.base import BossContext
from src.services.boss_ai_config import AiConfigError
from src.web.deps import get_db, require_superadmin
from src.web.security import verify_json_csrf

router = APIRouter(prefix="/api/v1/superadmin/bosses", tags=["superadmin"])

OVERRIDE_KEYS = (
    "max_active_groups",
    "max_active_tools",
    "max_active_channels",
    "mcp_slots",
    "cost_cap_usd_daily",
)


async def _require_boss_user(db: asyncpg.Pool, boss_id: int) -> asyncpg.Record:
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM users WHERE id=$1 AND role IN ('boss', 'superadmin')",
            boss_id,
        )
    if not row:
        raise HTTPException(404, "boss not found")
    return row


async def _audit(
    db: asyncpg.Pool,
    actor: BossContext,
    action: str,
    boss_id: int,
    payload: dict[str, Any] | None = None,
) -> None:
    await AdminAuditLogRepo(db, actor).insert(
        action=action,
        target_kind="boss",
        target_id=str(boss_id),
        payload=payload,
    )


def _ai_err(e: AiConfigError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.message)


# ---------------------------------------------------------------------------
# Tổng quan
# ---------------------------------------------------------------------------


@router.get("/{boss_id}/overview")
async def boss_overview(
    boss_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services.subscription import get_effective_limits

    user = await _require_boss_user(db, boss_id)
    limits = await get_effective_limits(db, boss_id)

    async with db.acquire() as c:
        groups = await c.fetchval(
            "SELECT COUNT(*) FROM group_notes WHERE boss_id=$1 AND is_active=TRUE", boss_id
        )
        tools = await c.fetchval(
            "SELECT COUNT(*) FROM boss_active_tools WHERE boss_id=$1", boss_id
        )
        mcp = await c.fetchval(
            "SELECT COUNT(*) FROM mcp_servers WHERE boss_id=$1 AND enabled=TRUE", boss_id
        )
        channels = await c.fetch(
            """
            SELECT baa.provider, baa.status, ba.display_name
            FROM bot_account_assignments baa
            JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE baa.boss_id=$1 AND baa.status='active' AND baa.provider <> 'web'
            """,
            boss_id,
        )
        msgs = await c.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM messages
                WHERE boss_id=$1 AND ts > NOW() - INTERVAL '30 days') AS msgs_in_30d,
              (SELECT COUNT(*) FROM outbound_messages
                WHERE boss_id=$1 AND sent_at > NOW() - INTERVAL '30 days') AS msgs_out_30d,
              (SELECT MAX(ts) FROM messages WHERE boss_id=$1) AS last_message_at
            """,
            boss_id,
        )
        usage = await c.fetchrow(
            """
            SELECT
              COALESCE(SUM(cost_usd) FILTER (
                WHERE called_at::date = (NOW() AT TIME ZONE 'utc')::date), 0) AS cost_today_usd,
              COALESCE(SUM(cost_usd) FILTER (
                WHERE called_at > NOW() - INTERVAL '30 days'), 0)             AS cost_30d_usd,
              COALESCE(SUM(tokens_in + tokens_out) FILTER (
                WHERE called_at > NOW() - INTERVAL '30 days'), 0)             AS tokens_30d
            FROM token_usage WHERE boss_id=$1
            """,
            boss_id,
        )
        plan = await c.fetchrow(
            "SELECT id, name, label FROM plans WHERE id=$1", user["plan_id"]
        )

    overrides = user["plan_overrides_json"]
    if isinstance(overrides, str):
        overrides = json.loads(overrides)

    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "tz": user["tz"],
        "created_at": user["created_at"].isoformat() if user["created_at"] else None,
        "subscription": {
            "plan_id": plan["id"] if plan else None,
            "plan_name": plan["name"] if plan else None,
            "plan_label": plan["label"] if plan else None,
            "status": user["subscription_status"],
            "expiry": user["subscription_expiry"].isoformat()
            if user["subscription_expiry"]
            else None,
            "overrides": overrides or {},
        },
        "usage": {
            "groups": {"used": groups, "limit": limits.max_active_groups},
            "tools": {"used": tools, "limit": limits.max_active_tools},
            "channels": {"used": len(channels), "limit": limits.max_active_channels},
            "mcp": {"used": mcp, "limit": limits.mcp_slots},
            "channel_list": [
                {"provider": ch["provider"], "display_name": ch["display_name"]}
                for ch in channels
            ],
            "cost_today_usd": float(usage["cost_today_usd"]),
            "cost_cap_usd_daily": limits.cost_cap_usd_daily,
            "cost_30d_usd": float(usage["cost_30d_usd"]),
            "tokens_30d": int(usage["tokens_30d"]),
            "msgs_in_30d": int(msgs["msgs_in_30d"]),
            "msgs_out_30d": int(msgs["msgs_out_30d"]),
            "last_message_at": msgs["last_message_at"].isoformat()
            if msgs["last_message_at"]
            else None,
        },
    }


# ---------------------------------------------------------------------------
# Gói & giới hạn
# ---------------------------------------------------------------------------


class PatchSubscriptionBody(BaseModel):
    plan_id: Optional[int] = None
    subscription_status: Optional[str] = None
    # Sentinel: field vắng mặt = không đổi; null tường minh = xoá hạn (vô hạn)
    subscription_expiry: Optional[str] = None
    clear_expiry: bool = False
    overrides: Optional[dict] = None


@router.patch("/{boss_id}/subscription", dependencies=[Depends(verify_json_csrf)])
async def patch_boss_subscription(
    boss_id: int,
    body: PatchSubscriptionBody,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    await _require_boss_user(db, boss_id)
    changes: dict[str, Any] = {}

    async with db.acquire() as c:
        if body.plan_id is not None:
            ok = await c.fetchval("SELECT 1 FROM plans WHERE id=$1", body.plan_id)
            if not ok:
                raise HTTPException(404, "plan not found")
            await c.execute(
                "UPDATE users SET plan_id=$2 WHERE id=$1", boss_id, body.plan_id
            )
            changes["plan_id"] = body.plan_id

        if body.subscription_status is not None:
            if body.subscription_status not in (
                "trial", "active", "expired_grace", "expired", "canceled"
            ):
                raise HTTPException(422, "invalid subscription_status")
            await c.execute(
                "UPDATE users SET subscription_status=$2 WHERE id=$1",
                boss_id,
                body.subscription_status,
            )
            changes["subscription_status"] = body.subscription_status

        if body.clear_expiry:
            await c.execute(
                "UPDATE users SET subscription_expiry=NULL WHERE id=$1", boss_id
            )
            changes["subscription_expiry"] = None
        elif body.subscription_expiry is not None:
            try:
                expiry = datetime.fromisoformat(body.subscription_expiry)
            except ValueError:
                raise HTTPException(422, "invalid subscription_expiry (ISO date)")
            await c.execute(
                "UPDATE users SET subscription_expiry=$2 WHERE id=$1", boss_id, expiry
            )
            changes["subscription_expiry"] = expiry.isoformat()

        if body.overrides is not None:
            unknown = set(body.overrides) - set(OVERRIDE_KEYS)
            if unknown:
                raise HTTPException(422, f"unknown override keys: {sorted(unknown)}")
            # Chỉ giữ key có giá trị — bỏ key = quay về theo gói
            cleaned = {k: v for k, v in body.overrides.items() if v is not None}
            await c.execute(
                "UPDATE users SET plan_overrides_json=$2::jsonb WHERE id=$1",
                boss_id,
                json.dumps(cleaned),
            )
            changes["overrides"] = cleaned

    if changes:
        await _audit(db, actor, "boss.subscription_updated", boss_id, changes)
    return {"updated": len(changes), "changes": changes}


# ---------------------------------------------------------------------------
# Models AI hộ sếp
# ---------------------------------------------------------------------------


@router.get("/{boss_id}/ai")
async def boss_ai_settings(
    boss_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    try:
        return await boss_ai_config.get_ai_settings(db, boss_id)
    except AiConfigError as e:
        raise _ai_err(e)


@router.patch("/{boss_id}/ai", dependencies=[Depends(verify_json_csrf)])
async def patch_boss_ai(
    boss_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    slot = payload.get("slot")
    cap = payload.get("cost_cap_usd_daily")
    try:
        if slot:
            await boss_ai_config.set_model_slot(db, boss_id, slot, payload.get("model_id"))
            await _audit(db, actor, "boss.ai_slot_updated", boss_id, {
                "slot": slot, "model_id": payload.get("model_id"),
            })
            return {"updated": 1}
        if cap is not None:
            await boss_ai_config.set_cost_cap(db, boss_id, cap)
            await _audit(db, actor, "boss.cost_cap_updated", boss_id, {"cost_cap": cap})
            return {"updated": 1}
    except AiConfigError as e:
        raise _ai_err(e)
    return {"updated": 0}


@router.patch("/{boss_id}/ai/keys", dependencies=[Depends(verify_json_csrf)])
async def patch_boss_ai_keys(
    boss_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    """Nhập/xoá BYO key hộ sếp. Key mới validate liveness trước khi lưu.
    Audit chỉ ghi provider + hành động — KHÔNG ghi giá trị key."""
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    provider = payload.get("provider", "")
    try:
        if payload.get("clear"):
            await boss_ai_config.clear_api_key(db, boss_id, provider)
            action = "cleared"
        else:
            await boss_ai_config.set_api_key(
                db, boss_id, provider, payload.get("api_key") or "", validate=True
            )
            action = "set"
    except AiConfigError as e:
        raise _ai_err(e)
    await _audit(db, actor, "boss.ai_key_updated", boss_id, {
        "provider": provider, "action": action,
    })
    return {"updated": 1}


@router.post("/{boss_id}/ai/models", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def create_boss_own_model(
    boss_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    try:
        new_id = await boss_ai_config.create_own_model(db, actor, boss_id, payload)
    except AiConfigError as e:
        raise _ai_err(e)
    await _audit(db, actor, "boss.own_model_added", boss_id, {
        "model_id": new_id,
        "provider": payload.get("provider"),
        "name": payload.get("name"),
    })
    return {"id": new_id}


@router.delete("/{boss_id}/ai/models/{model_id}", dependencies=[Depends(verify_json_csrf)])
async def delete_boss_own_model(
    boss_id: int,
    model_id: int,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    try:
        await boss_ai_config.delete_own_model(db, boss_id, model_id)
    except AiConfigError as e:
        raise _ai_err(e)
    await _audit(db, actor, "boss.own_model_deleted", boss_id, {"model_id": model_id})
    return {"deleted": 1}


@router.get("/{boss_id}/ai/provider-models")
async def boss_provider_models(
    boss_id: int,
    provider: str = Query(...),
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import boss_ai_config

    await _require_boss_user(db, boss_id)
    return await boss_ai_config.list_provider_models(db, boss_id, provider)


# ---------------------------------------------------------------------------
# Lịch sử chat
# ---------------------------------------------------------------------------


@router.get("/{boss_id}/conversations")
async def boss_conversations(
    boss_id: int,
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Hội thoại của boss, gộp inbound + outbound theo (provider, chat_id).

    Tên hội thoại: nhóm → group_notes.group_name; DM web → tên hội thoại web
    (web_users.name); DM kênh khác → tên người gửi gần nhất.
    """
    await _require_boss_user(db, boss_id)
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            WITH merged AS (
              SELECT provider, chat_id, chat_type, ts, sender_name
              FROM messages WHERE boss_id=$1
              UNION ALL
              SELECT provider, chat_id, 'unknown' AS chat_type, sent_at AS ts,
                     NULL AS sender_name
              FROM outbound_messages WHERE boss_id=$1
            ),
            agg AS (
              SELECT provider, chat_id,
                     MAX(ts) AS last_ts,
                     COUNT(*) AS msg_count,
                     MAX(chat_type) FILTER (WHERE chat_type <> 'unknown') AS chat_type
              FROM merged
              GROUP BY provider, chat_id
            )
            SELECT a.provider, a.chat_id, a.chat_type, a.last_ts, a.msg_count,
                   gn.group_name,
                   CASE WHEN a.provider = 'web' AND a.chat_id LIKE 'dm:%'
                        THEN (SELECT wu.name FROM web_users wu
                              WHERE wu.id = substring(a.chat_id from 4))
                   END AS web_name,
                   (SELECT m.sender_name FROM messages m
                     WHERE m.boss_id=$1 AND m.provider=a.provider
                       AND m.chat_id=a.chat_id AND m.sender_name IS NOT NULL
                     ORDER BY m.ts DESC LIMIT 1) AS last_sender_name
            FROM agg a
            LEFT JOIN group_notes gn
              ON gn.boss_id=$1 AND gn.provider=a.provider AND gn.chat_id=a.chat_id
            ORDER BY a.last_ts DESC
            """,
            boss_id,
        )

    # Mở danh sách hội thoại của boss = bắt đầu xem chat → audit một lần ở đây
    await _audit(db, actor, "boss.chat_viewed", boss_id, None)

    result = []
    for r in rows:
        chat_type = r["chat_type"] or ("dm" if str(r["chat_id"]).startswith("dm:") else "group")
        if r["group_name"]:
            title = r["group_name"]
        elif r["web_name"]:
            title = r["web_name"]
        elif chat_type == "dm":
            title = r["last_sender_name"] or f"DM {r['chat_id']}"
        else:
            title = f"Nhóm {r['chat_id']}"
        result.append(
            {
                "provider": r["provider"],
                "chat_id": r["chat_id"],
                "chat_type": chat_type,
                "title": title,
                "msg_count": int(r["msg_count"]),
                "last_ts": r["last_ts"].isoformat() if r["last_ts"] else None,
            }
        )
    return result


@router.get("/{boss_id}/messages")
async def boss_conversation_messages(
    boss_id: int,
    provider: str = Query(...),
    chat_id: str = Query(...),
    before: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: asyncpg.Pool = Depends(get_db),
    actor: BossContext = Depends(require_superadmin),
) -> dict:
    """Tin nhắn một hội thoại (mới → cũ, cursor ``before`` theo ts ISO).

    FE đảo lại và chèn separator theo ngày.
    """
    await _require_boss_user(db, boss_id)
    before_ts = None
    if before:
        try:
            before_ts = datetime.fromisoformat(before)
        except ValueError:
            raise HTTPException(422, "invalid before cursor")

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT * FROM (
              SELECT 'in'::text AS direction, m.id, m.sender_name, m.text,
                     m.media_kind, m.media_url, m.ts
              FROM messages m
              WHERE m.boss_id=$1 AND m.provider=$2 AND m.chat_id=$3
              UNION ALL
              SELECT 'out'::text AS direction, o.id, 'Bot' AS sender_name,
                     o.content AS text, 'text' AS media_kind, NULL AS media_url,
                     o.sent_at AS ts
              FROM outbound_messages o
              WHERE o.boss_id=$1 AND o.provider=$2 AND o.chat_id=$3
                AND o.status <> 'failed'
            ) merged
            WHERE ($4::timestamptz IS NULL OR ts < $4)
            ORDER BY ts DESC
            LIMIT $5
            """,
            boss_id,
            provider,
            chat_id,
            before_ts,
            limit,
        )

    messages = [
        {
            "direction": r["direction"],
            "id": r["id"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "media_kind": r["media_kind"],
            "media_url": r["media_url"],
            "ts": r["ts"].isoformat(),
        }
        for r in reversed(rows)
    ]
    next_before = messages[0]["ts"] if len(rows) == limit and messages else None
    return {"messages": messages, "next_before": next_before}
