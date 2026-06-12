"""Super-admin API endpoints for /api/v1/superadmin/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from src.repositories.base import BossContext
from src.web.deps import get_db, require_superadmin
from src.web.security import verify_json_csrf

router = APIRouter(prefix="/api/v1/superadmin", tags=["superadmin"])

_SLOTS = ("smart", "fast", "vision")


# ---------------------------------------------------------------------------
# GET /model-slots
# ---------------------------------------------------------------------------

@router.get("/model-slots")
async def list_model_slots(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Return platform-default model for each slot (smart / fast / vision)."""
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, tier, name, provider
            FROM models
            WHERE tier = ANY($1::text[]) AND is_platform_default = TRUE AND is_active = TRUE
            ORDER BY tier
            """,
            list(_SLOTS),
        )

    by_tier: dict[str, dict] = {r["tier"]: dict(r) for r in rows}

    result: list[dict] = []
    for slot in _SLOTS:
        m = by_tier.get(slot)
        if m:
            status = "active"
            model_name = m["name"]
            provider = m["provider"]
            model_id = m["id"]
        else:
            model_name = None
            provider = None
            model_id = None
            status = "fallback" if slot == "vision" else "missing"
        result.append({
            "slot": slot,
            "model_id": model_id,
            "model": model_name,
            "provider": provider,
            "status": status,
        })
    return result


# ---------------------------------------------------------------------------
# PATCH /model-slots/:slot  — assign a model as platform default for a slot
# ---------------------------------------------------------------------------

class PatchSlotBody(BaseModel):
    model_id: int


@router.patch(
    "/model-slots/{slot}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_model_slot(
    slot: str,
    body: PatchSlotBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    """Assign a model as the platform default for a slot (tier).

    Clears is_platform_default from any previous model in that tier, then sets
    it on the requested model_id.
    """
    if slot not in _SLOTS:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")
    async with db.acquire() as c:
        # Verify target model exists with matching tier
        row = await c.fetchrow(
            "SELECT id, tier, name FROM models WHERE id = $1", body.model_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="model not found")
        if row["tier"] != slot:
            raise HTTPException(
                status_code=400,
                detail=f"Model tier '{row['tier']}' does not match slot '{slot}'",
            )
        # Clear current default for this slot
        await c.execute(
            "UPDATE models SET is_platform_default = FALSE, updated_at = NOW() WHERE tier = $1",
            slot,
        )
        # Set new default
        await c.execute(
            "UPDATE models SET is_platform_default = TRUE, updated_at = NOW() WHERE id = $1",
            body.model_id,
        )
    return {"slot": slot, "model_id": body.model_id, "model": row["name"]}


# ---------------------------------------------------------------------------
# GET /models — list all models
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM models ORDER BY tier, provider, name"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /models — create a model
# ---------------------------------------------------------------------------

class CreateModelBody(BaseModel):
    name: str
    provider: str
    endpoint_kind: str = "openai_chat"
    base_url: Optional[str] = None
    tier: str
    ctx_max: int = 8000
    capabilities: list[str] = []
    cost_per_1m_input_usd: Optional[float] = None
    cost_per_1m_output_usd: Optional[float] = None
    is_platform_default: bool = False
    is_active: bool = True
    notes: Optional[str] = None


@router.post(
    "/models",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_model(
    body: CreateModelBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        new_id = await c.fetchval(
            """
            INSERT INTO models
              (name, provider, endpoint_kind, base_url, tier, ctx_max,
               capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
               is_platform_default, is_active, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            body.name,
            body.provider,
            body.endpoint_kind,
            body.base_url,
            body.tier,
            body.ctx_max,
            json.dumps(body.capabilities),
            body.cost_per_1m_input_usd,
            body.cost_per_1m_output_usd,
            body.is_platform_default,
            body.is_active,
            body.notes,
        )
    return {"id": new_id}


# ---------------------------------------------------------------------------
# PATCH /models/:id — update a model
# ---------------------------------------------------------------------------

class PatchModelBody(BaseModel):
    tier: Optional[str] = None
    ctx_max: Optional[int] = None
    cost_per_1m_input_usd: Optional[float] = None
    cost_per_1m_output_usd: Optional[float] = None
    is_platform_default: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


@router.patch(
    "/models/{model_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_model(
    model_id: int,
    body: PatchModelBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT * FROM models WHERE id = $1", model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="model not found")
        await c.execute(
            """
            UPDATE models
            SET tier                     = COALESCE($2, tier),
                ctx_max                  = COALESCE($3, ctx_max),
                cost_per_1m_input_usd    = COALESCE($4, cost_per_1m_input_usd),
                cost_per_1m_output_usd   = COALESCE($5, cost_per_1m_output_usd),
                is_platform_default      = COALESCE($6, is_platform_default),
                is_active                = COALESCE($7, is_active),
                notes                    = COALESCE($8, notes),
                updated_at               = NOW()
            WHERE id = $1
            """,
            model_id,
            body.tier,
            body.ctx_max,
            body.cost_per_1m_input_usd,
            body.cost_per_1m_output_usd,
            body.is_platform_default,
            body.is_active,
            body.notes,
        )
    return {"id": model_id, "ok": True}


# ---------------------------------------------------------------------------
# DELETE /models/:id
# ---------------------------------------------------------------------------

@router.delete(
    "/models/{model_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_model(
    model_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM models WHERE id = $1", model_id)
        if not existing:
            raise HTTPException(status_code=404, detail="model not found")
        await c.execute("DELETE FROM models WHERE id = $1", model_id)


# ---------------------------------------------------------------------------
# GET /llm-routes
# ---------------------------------------------------------------------------

@router.get("/llm-routes")
async def list_llm_routes(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM llm_routes ORDER BY feature, weight DESC"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# PATCH /llm-routes/:id
# ---------------------------------------------------------------------------

class PatchLlmRouteBody(BaseModel):
    target_tier: Optional[str] = None
    fallback_chain: Optional[list] = None
    weight: Optional[int] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


@router.patch(
    "/llm-routes/{route_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_llm_route(
    route_id: int,
    body: PatchLlmRouteBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM llm_routes WHERE id = $1", route_id)
        if not existing:
            raise HTTPException(status_code=404, detail="llm_route not found")
        fallback_json = json.dumps(body.fallback_chain) if body.fallback_chain is not None else None
        await c.execute(
            """
            UPDATE llm_routes
            SET target_tier    = COALESCE($2, target_tier),
                fallback_chain = COALESCE($3::jsonb, fallback_chain),
                weight         = COALESCE($4, weight),
                is_active      = COALESCE($5, is_active),
                notes          = COALESCE($6, notes),
                updated_at     = NOW()
            WHERE id = $1
            """,
            route_id,
            body.target_tier,
            fallback_json,
            body.weight,
            body.is_active,
            body.notes,
        )
    return {"id": route_id, "ok": True}


# ---------------------------------------------------------------------------
# GET /feature-budgets
# ---------------------------------------------------------------------------

@router.get("/feature-budgets")
async def list_feature_budgets(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM feature_budgets ORDER BY feature"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# PATCH /feature-budgets/:feature
# ---------------------------------------------------------------------------

class PatchFeatureBudgetBody(BaseModel):
    max_input_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    compression_strategy: Optional[str] = None
    cache_prefix_hint: Optional[str] = None


@router.patch(
    "/feature-budgets/{feature}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_feature_budget(
    feature: str,
    body: PatchFeatureBudgetBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT feature FROM feature_budgets WHERE feature = $1", feature
        )
        if not existing:
            raise HTTPException(status_code=404, detail="feature_budget not found")
        await c.execute(
            """
            UPDATE feature_budgets
            SET max_input_tokens      = COALESCE($2, max_input_tokens),
                max_output_tokens     = COALESCE($3, max_output_tokens),
                compression_strategy  = COALESCE($4, compression_strategy),
                cache_prefix_hint     = COALESCE($5, cache_prefix_hint),
                updated_at            = NOW()
            WHERE feature = $1
            """,
            feature,
            body.max_input_tokens,
            body.max_output_tokens,
            body.compression_strategy,
            body.cache_prefix_hint,
        )
    return {"feature": feature, "ok": True}


# ---------------------------------------------------------------------------
# GET /bot-accounts
# ---------------------------------------------------------------------------

@router.get("/bot-accounts")
async def list_bot_accounts(
    range: str = "7d",
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Return all bot accounts with basic stats."""
    days = int(range.rstrip("d")) if range.endswith("d") else 7  # noqa: F841

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, provider, provider_user_id, display_name,
                   account_kind, ownership, status, last_seen_at,
                   msgs_received_total, msgs_sent_total
            FROM bot_accounts
            ORDER BY display_name
            """,
        )

    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for r in rows:
        last = r["last_seen_at"]
        if last is None:
            conn_status = "offline"
        elif (now - last) > timedelta(minutes=10):
            conn_status = "warn"
        else:
            conn_status = "online"

        out.append({
            "id": r["id"],
            "channel": r["provider"],
            "handle": r["provider_user_id"],
            "label": r["display_name"],
            "account_kind": r["account_kind"],
            "ownership": r["ownership"],
            "account_status": r["status"],
            "messages_in": r["msgs_received_total"],
            "messages_out": r["msgs_sent_total"],
            "status": conn_status,
            "last_seen_at": last.isoformat() if last else None,
        })
    return out


# ---------------------------------------------------------------------------
# POST /bot-accounts — create a new bot account connection record
# ---------------------------------------------------------------------------

class CreateBotAccountBody(BaseModel):
    provider: str  # zalo | telegram | lark
    label: str
    handle: str
    account_kind: str = "personal"  # personal | official
    ownership: Optional[str] = None


@router.post(
    "/bot-accounts",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_bot_account(
    body: CreateBotAccountBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    try:
        async with db.acquire() as c:
            new_id = await c.fetchval(
                """
                INSERT INTO bot_accounts
                  (provider, provider_user_id, display_name, account_kind, ownership, status)
                VALUES ($1, $2, $3, $4, $5, 'active')
                RETURNING id
                """,
                body.provider,
                body.handle,
                body.label,
                body.account_kind,
                body.ownership,
            )
    except asyncpg.UniqueViolationError as e:
        if "uq_boss_owned_one_per_provider" in str(e):
            raise HTTPException(409, "Boss này đã có một bot account cho nền tảng đó")
        raise HTTPException(409, "Tài khoản (provider + handle) đã tồn tại")
    return {"id": new_id}


# ---------------------------------------------------------------------------
# PATCH /bot-accounts/:id — update label, ownership, account_kind
# ---------------------------------------------------------------------------

class PatchBotAccountBody(BaseModel):
    label: Optional[str] = None
    ownership: Optional[str] = None
    account_kind: Optional[str] = None


@router.patch(
    "/bot-accounts/{account_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_bot_account(
    account_id: int,
    body: PatchBotAccountBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM bot_accounts WHERE id = $1", account_id)
        if not existing:
            raise HTTPException(status_code=404, detail="bot account not found")
        await c.execute(
            """
            UPDATE bot_accounts
            SET display_name  = COALESCE($2, display_name),
                ownership     = COALESCE($3, ownership),
                account_kind  = COALESCE($4, account_kind),
                updated_at    = NOW()
            WHERE id = $1
            """,
            account_id,
            body.label,
            body.ownership,
            body.account_kind,
        )
    return {"id": account_id, "ok": True}


# ---------------------------------------------------------------------------
# DELETE /bot-accounts/:id
# ---------------------------------------------------------------------------

@router.delete(
    "/bot-accounts/{account_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_bot_account(
    account_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM bot_accounts WHERE id = $1", account_id)
        if not existing:
            raise HTTPException(status_code=404, detail="bot account not found")
        await c.execute("DELETE FROM bot_accounts WHERE id = $1", account_id)


# ---------------------------------------------------------------------------
# GET /bosses — list users with role boss/superadmin
# ---------------------------------------------------------------------------

@router.get("/bosses")
async def list_bosses(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT u.id, u.email, u.name, u.role, u.subscription_status,
                   u.subscription_expiry, u.tz, u.created_at,
                   p.label AS plan_label, p.name AS plan_name,
                   (SELECT COUNT(*) FROM group_notes g
                     WHERE g.boss_id=u.id AND g.is_active=TRUE)        AS active_groups,
                   (SELECT COUNT(*) FROM bot_account_assignments baa
                     WHERE baa.boss_id=u.id AND baa.status='active'
                       AND baa.provider <> 'web')                      AS active_channels,
                   (SELECT MAX(m.ts) FROM messages m
                     WHERE m.boss_id=u.id)                             AS last_message_at
            FROM users u
            LEFT JOIN plans p ON p.id = u.plan_id
            WHERE u.role IN ('boss', 'superadmin')
            ORDER BY u.created_at DESC
            """
        )
    return [
        {
            "id": r["id"],
            "email": r["email"],
            "name": r["name"],
            "role": r["role"],
            "subscription_status": r["subscription_status"],
            "subscription_expiry": r["subscription_expiry"].isoformat()
            if r["subscription_expiry"]
            else None,
            "plan_label": r["plan_label"],
            "plan_name": r["plan_name"],
            "active_groups": int(r["active_groups"]),
            "active_channels": int(r["active_channels"]),
            "last_message_at": r["last_message_at"].isoformat()
            if r["last_message_at"]
            else None,
            "tz": r["tz"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /bosses — create a user with role boss/superadmin
# ---------------------------------------------------------------------------

class CreateBossBody(BaseModel):
    email: str
    name: Optional[str] = None
    role: str = "boss"


@router.post(
    "/bosses",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_boss(
    body: CreateBossBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    if body.role not in ("boss", "superadmin"):
        raise HTTPException(status_code=400, detail="role must be boss or superadmin")
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM users WHERE email = $1", body.email.lower())
        if existing:
            raise HTTPException(status_code=409, detail="email already exists")
        new_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            body.email.lower(),
            body.name,
            body.role,
        )
        if body.role == "boss":
            from src.services.subscription import provision_new_boss

            await provision_new_boss(c, new_id)
    return {"id": new_id}


# ---------------------------------------------------------------------------
# PATCH /bosses/:id — update name, role, or timezone
# ---------------------------------------------------------------------------

class PatchBossBody(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    tz: Optional[str] = None


@router.patch(
    "/bosses/{boss_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_boss(
    boss_id: int,
    body: PatchBossBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    if body.role is not None and body.role not in ("boss", "superadmin"):
        raise HTTPException(status_code=400, detail="role must be boss or superadmin")
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM users WHERE id = $1", boss_id)
        if not existing:
            raise HTTPException(status_code=404, detail="user not found")
        await c.execute(
            """
            UPDATE users
            SET name       = COALESCE($2, name),
                role       = COALESCE($3, role),
                tz         = COALESCE($4, tz)
            WHERE id = $1
            """,
            boss_id,
            body.name,
            body.role,
            body.tz,
        )
    return {"id": boss_id, "ok": True}


# ---------------------------------------------------------------------------
# DELETE /bosses/:id — delete (self-delete blocked)
# ---------------------------------------------------------------------------

@router.delete(
    "/bosses/{boss_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_boss(
    boss_id: int,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_superadmin),
) -> None:
    if boss_id == ctx.boss_id:
        raise HTTPException(status_code=400, detail="cannot delete yourself")
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM users WHERE id = $1", boss_id)
        if not existing:
            raise HTTPException(status_code=404, detail="user not found")
        await c.execute("DELETE FROM users WHERE id = $1", boss_id)


# ---------------------------------------------------------------------------
# GET /bot-accounts/:id/messages — recent messages for a bot account
# Messages map to accounts qua bot_account_assignments (boss_id, provider) —
# tin nhắn cũ trước khi đổi acc sẽ tính cho acc hiện tại (chấp nhận cho v1).
# ---------------------------------------------------------------------------

@router.get("/bot-accounts/{account_id}/messages")
async def list_bot_account_messages(
    account_id: int,
    limit: int = Query(50, le=200),
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM bot_accounts WHERE id = $1", account_id)
        if not existing:
            raise HTTPException(status_code=404, detail="bot account not found")
        rows = await c.fetch(
            """
            SELECT m.id, m.boss_id, u.email AS boss_email,
                   m.chat_id, m.chat_type, m.sender_name, m.text, m.ts
            FROM messages m
            JOIN bot_account_assignments baa
              ON baa.boss_id = m.boss_id AND baa.provider = m.provider
            JOIN users u ON u.id = m.boss_id
            WHERE baa.bot_account_id = $1
            ORDER BY m.ts DESC
            LIMIT $2
            """,
            account_id,
            limit,
        )
    return [
        {
            "id": r["id"],
            "boss_id": r["boss_id"],
            "boss_email": r["boss_email"],
            "chat_id": r["chat_id"],
            "chat_type": r["chat_type"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "ts": r["ts"].isoformat(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Bot account: chi tiết, đăng nhập QR (Zalo), thống kê tin nhắn theo ngày
#   GET  /bot-accounts/{id}/detail
#   POST /bot-accounts/{id}/qr-login
#   GET  /bot-accounts/qr-login/{login_id}
#   GET  /bot-accounts/{id}/stats/daily?days=30
#
# Tin nhắn map về account qua bot_account_assignments (boss_id, provider) —
# tin cũ trước khi đổi acc tính cho acc hiện tại (chấp nhận cho v1).
# ---------------------------------------------------------------------------


@router.get("/bot-accounts/{account_id}/detail")
async def bot_account_detail(
    account_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        acc = await c.fetchrow(
            """
            SELECT id, provider, provider_user_id, display_name, account_kind,
                   ownership, owner_boss_id, status, status_reason,
                   max_assigned_bosses, last_seen_at,
                   msgs_received_total, msgs_sent_total, notes, created_at,
                   (credentials_blob_enc IS NOT NULL) AS has_credentials
            FROM bot_accounts WHERE id=$1
            """,
            account_id,
        )
        if not acc:
            raise HTTPException(404, "bot account not found")
        assignments = await c.fetch(
            """
            SELECT baa.boss_id, baa.status, baa.assigned_at,
                   u.email AS boss_email, u.name AS boss_name
            FROM bot_account_assignments baa
            JOIN users u ON u.id = baa.boss_id
            WHERE baa.bot_account_id = $1
            ORDER BY baa.assigned_at DESC
            """,
            account_id,
        )
    d = dict(acc)
    for f in ("last_seen_at", "created_at"):
        if d.get(f):
            d[f] = d[f].isoformat()
    d["assignments"] = [
        {
            "boss_id": a["boss_id"],
            "boss_email": a["boss_email"],
            "boss_name": a["boss_name"],
            "status": a["status"],
            "assigned_at": a["assigned_at"].isoformat() if a["assigned_at"] else None,
        }
        for a in assignments
    ]
    return d


@router.post("/bot-accounts/{account_id}/qr-login", dependencies=[Depends(verify_json_csrf)])
async def bot_account_qr_login_start(
    account_id: int,
    request: Request,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_superadmin),
) -> dict:
    """Mở phiên QR để đăng nhập acc Zalo cho bot account này (login mới / re-login)."""
    async with db.acquire() as c:
        provider = await c.fetchval(
            "SELECT provider FROM bot_accounts WHERE id=$1", account_id
        )
    if provider is None:
        raise HTTPException(404, "bot account not found")
    if provider != "zalo":
        raise HTTPException(422, "Chỉ kênh Zalo dùng đăng nhập QR")
    manager = getattr(request.app.state, "zalo_qr_login", None)
    if manager is None:
        raise HTTPException(503, "Zalo QR login chưa sẵn sàng")
    sess = await manager.start_for_account(account_id, actor_user_id=ctx.boss_id)
    return {"login_id": sess.login_id, "status": sess.status}


@router.get("/bot-accounts/qr-login/{login_id}")
async def bot_account_qr_login_status(
    login_id: str,
    request: Request,
    _: BossContext = Depends(require_superadmin),
) -> dict:
    manager = getattr(request.app.state, "zalo_qr_login", None)
    sess = manager.get_by_login_id(login_id) if manager else None
    # Chỉ trả phiên do superadmin mở (mode account_login) — không lộ phiên của boss
    if sess is None or sess.target_account_id is None:
        raise HTTPException(404, "Phiên đăng nhập không tồn tại")
    return {
        "status": sess.status,
        "qr_image_b64": sess.qr_image_b64 if sess.status == "qr" else None,
        "display_name": sess.display_name,
        "error": sess.error,
        "bot_account_id": sess.bot_account_id,
        "expires_in_s": sess.expires_in_s,
    }


@router.get("/bot-accounts/{account_id}/stats/daily")
async def bot_account_daily_stats(
    account_id: int,
    days: int = Query(30, ge=1, le=365),
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Số tin nhận/gửi theo ngày (đủ ngày, kể cả ngày 0 tin), mới nhất trước."""
    async with db.acquire() as c:
        existing = await c.fetchval(
            "SELECT 1 FROM bot_accounts WHERE id=$1", account_id
        )
        if not existing:
            raise HTTPException(404, "bot account not found")
        rows = await c.fetch(
            """
            WITH days AS (
              SELECT (CURRENT_DATE - offs) AS day
              FROM generate_series(0, $2 - 1) AS offs
            ),
            recv AS (
              SELECT m.ts::date AS day, COUNT(*) AS n
              FROM messages m
              JOIN bot_account_assignments baa
                ON baa.boss_id = m.boss_id AND baa.provider = m.provider
              WHERE baa.bot_account_id = $1
                AND m.ts >= CURRENT_DATE - ($2 - 1)
              GROUP BY 1
            ),
            sent AS (
              SELECT o.sent_at::date AS day, COUNT(*) AS n
              FROM outbound_messages o
              JOIN bot_account_assignments baa
                ON baa.boss_id = o.boss_id AND baa.provider = o.provider
              WHERE baa.bot_account_id = $1
                AND o.status <> 'failed'
                AND o.sent_at >= CURRENT_DATE - ($2 - 1)
              GROUP BY 1
            )
            SELECT d.day,
                   COALESCE(r.n, 0) AS received,
                   COALESCE(s.n, 0) AS sent
            FROM days d
            LEFT JOIN recv r ON r.day = d.day
            LEFT JOIN sent s ON s.day = d.day
            ORDER BY d.day DESC
            """,
            account_id,
            days,
        )
    return [
        {
            "date": r["day"].isoformat(),
            "received": int(r["received"]),
            "sent": int(r["sent"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Proxy pool — IP dân cư gán per-boss
#   GET/POST /proxies   PATCH/DELETE /proxies/{id}   POST /proxies/{id}/test
# ---------------------------------------------------------------------------


@router.get("/proxies")
async def list_proxies_sa(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    from src.services import proxy_pool

    return await proxy_pool.list_proxies(db)


@router.post("/proxies", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_proxy_sa(
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import proxy_pool

    if not payload.get("url"):
        raise HTTPException(422, "url required")
    try:
        new_id = await proxy_pool.create_proxy(
            db,
            label=payload.get("label", ""),
            url=payload["url"],
            region=payload.get("region"),
            max_bosses=payload.get("max_bosses", 1),
            notes=payload.get("notes"),
        )
    except proxy_pool.ProxyError as e:
        raise HTTPException(e.status, e.message)
    return {"id": new_id}


@router.patch("/proxies/{proxy_id}", dependencies=[Depends(verify_json_csrf)])
async def update_proxy_sa(
    proxy_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import proxy_pool

    try:
        await proxy_pool.update_proxy(db, proxy_id, payload)
    except proxy_pool.ProxyError as e:
        raise HTTPException(e.status, e.message)
    return {"updated": 1}


@router.delete("/proxies/{proxy_id}", dependencies=[Depends(verify_json_csrf)])
async def delete_proxy_sa(
    proxy_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    from src.services import proxy_pool

    try:
        await proxy_pool.delete_proxy(db, proxy_id)
    except proxy_pool.ProxyError as e:
        raise HTTPException(e.status, e.message)
    return {"deleted": 1}


@router.post("/proxies/{proxy_id}/test", dependencies=[Depends(verify_json_csrf)])
async def test_proxy_sa(
    proxy_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    """Gọi thử qua proxy lấy IP công khai để kiểm tra còn sống."""
    from src.services import proxy_pool

    async with db.acquire() as c:
        blob = await c.fetchval("SELECT url_enc FROM proxies WHERE id=$1", proxy_id)
    if blob is None:
        raise HTTPException(404, "proxy not found")
    url = proxy_pool.decrypt_url(blob)
    if not url:
        raise HTTPException(500, "không giải mã được url proxy")
    return await proxy_pool.test_proxy(url)


# ---------------------------------------------------------------------------
# GET /usage — platform-wide token usage analytics
# ---------------------------------------------------------------------------

@router.get("/usage")
async def platform_usage(
    range: str = Query("30d", pattern=r"^\d+d$"),
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    days = max(1, min(int(range.rstrip("d")), 365))
    async with db.acquire() as c:
        totals = await c.fetchrow(
            """
            SELECT COALESCE(SUM(tokens_in), 0)::bigint              AS tokens_in,
                   COALESCE(SUM(tokens_out), 0)::bigint             AS tokens_out,
                   COALESCE(SUM(tokens_in + tokens_out), 0)::bigint AS tokens,
                   COUNT(*)::bigint                                 AS calls,
                   COALESCE(SUM(cost_usd), 0.0)::float              AS cost_usd
            FROM token_usage
            WHERE called_at > NOW() - ($1 || ' days')::INTERVAL
            """,
            str(days),
        )
        daily = await c.fetch(
            """
            SELECT DATE(called_at AT TIME ZONE 'UTC') AS day,
                   SUM(tokens_in + tokens_out)::bigint AS tokens,
                   COUNT(*)::bigint                    AS calls,
                   SUM(cost_usd)::float                AS cost_usd
            FROM token_usage
            WHERE called_at > NOW() - ($1 || ' days')::INTERVAL
            GROUP BY day ORDER BY day DESC
            """,
            str(days),
        )
        by_boss = await c.fetch(
            """
            SELECT t.boss_id, u.email, u.name,
                   SUM(t.tokens_in + t.tokens_out)::bigint AS tokens,
                   COUNT(*)::bigint                        AS calls,
                   SUM(t.cost_usd)::float                  AS cost_usd
            FROM token_usage t
            JOIN users u ON u.id = t.boss_id
            WHERE t.called_at > NOW() - ($1 || ' days')::INTERVAL
            GROUP BY t.boss_id, u.email, u.name
            ORDER BY SUM(t.cost_usd) DESC
            LIMIT 50
            """,
            str(days),
        )
        by_feature = await c.fetch(
            """
            SELECT feature,
                   SUM(tokens_in + tokens_out)::bigint AS tokens,
                   COUNT(*)::bigint                    AS calls,
                   SUM(cost_usd)::float                AS cost_usd
            FROM token_usage
            WHERE called_at > NOW() - ($1 || ' days')::INTERVAL
            GROUP BY feature ORDER BY SUM(cost_usd) DESC
            """,
            str(days),
        )
    return {
        "range_days": days,
        "totals": dict(totals),
        "daily": [{**dict(r), "day": str(r["day"])} for r in daily],
        "by_boss": [dict(r) for r in by_boss],
        "by_feature": [dict(r) for r in by_feature],
    }


# ===========================================================================
# Prompts  (versioned — each key has many rows; one has is_active=TRUE)
# ===========================================================================

@router.get("/prompts")
async def list_prompts(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Return all prompt rows ordered by key / version desc."""
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, key, version, is_active, notes, created_at FROM prompts ORDER BY key, version DESC"
        )
    return [
        {
            "id": r["id"],
            "key": r["key"],
            "version": r["version"],
            "is_active": r["is_active"],
            "notes": r["notes"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        row = await c.fetchrow("SELECT * FROM prompts WHERE id = $1", prompt_id)
    if not row:
        raise HTTPException(status_code=404, detail="prompt not found")
    return {
        "id": row["id"],
        "key": row["key"],
        "version": row["version"],
        "body": row["body"],
        "is_active": row["is_active"],
        "notes": row["notes"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "created_by": row["created_by"],
    }


class CreatePromptBody(BaseModel):
    key: str
    body: str
    notes: Optional[str] = None


@router.post(
    "/prompts",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_prompt(
    body: CreatePromptBody,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        max_ver = await c.fetchval(
            "SELECT COALESCE(MAX(version), 0) FROM prompts WHERE key = $1", body.key
        )
        new_id = await c.fetchval(
            """
            INSERT INTO prompts (key, version, body, is_active, notes, created_by)
            VALUES ($1, $2, $3, FALSE, $4, $5)
            RETURNING id
            """,
            body.key,
            int(max_ver or 0) + 1,
            body.body,
            body.notes,
            ctx.boss_id,
        )
    return {"id": new_id}


class PatchPromptBody(BaseModel):
    body: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch(
    "/prompts/{prompt_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_prompt(
    prompt_id: int,
    body: PatchPromptBody,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_superadmin),
) -> dict:
    """Update body/notes in place, OR activate (deactivates all siblings for same key)."""
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT * FROM prompts WHERE id = $1", prompt_id)
        if not existing:
            raise HTTPException(status_code=404, detail="prompt not found")

        if body.is_active is True:
            # Deactivate all versions for same key first
            await c.execute(
                "UPDATE prompts SET is_active = FALSE WHERE key = $1", existing["key"]
            )
            await c.execute("UPDATE prompts SET is_active = TRUE WHERE id = $1", prompt_id)

        updates: list[str] = []
        params: list = [prompt_id]
        if body.body is not None:
            params.append(body.body)
            updates.append(f"body = ${len(params)}")
        if body.notes is not None:
            params.append(body.notes)
            updates.append(f"notes = ${len(params)}")

        if updates:
            await c.execute(
                f"UPDATE prompts SET {', '.join(updates)} WHERE id = $1",
                *params,
            )
    return {"id": prompt_id, "ok": True}


@router.delete(
    "/prompts/{prompt_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_prompt(
    prompt_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM prompts WHERE id = $1", prompt_id)
        if not existing:
            raise HTTPException(status_code=404, detail="prompt not found")
        await c.execute("DELETE FROM prompts WHERE id = $1", prompt_id)


# ===========================================================================
# Note templates
# ===========================================================================

@router.get("/note-templates")
async def list_note_templates(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM note_templates ORDER BY name")
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "is_system": r["is_system"],
            "owner_boss_id": r["owner_boss_id"],
            "sections_json": r["sections_json"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


class CreateNoteTemplateBody(BaseModel):
    name: str
    description: Optional[str] = None
    is_system: bool = False
    sections_json: list = []


@router.post(
    "/note-templates",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_note_template(
    body: CreateNoteTemplateBody,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        new_id = await c.fetchval(
            """
            INSERT INTO note_templates (name, description, is_system, owner_boss_id, sections_json)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING id
            """,
            body.name,
            body.description,
            body.is_system,
            ctx.boss_id if not body.is_system else None,
            json.dumps(body.sections_json),
        )
    return {"id": new_id}


class PatchNoteTemplateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sections_json: Optional[list] = None


@router.patch(
    "/note-templates/{template_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_note_template(
    template_id: int,
    body: PatchNoteTemplateBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM note_templates WHERE id = $1", template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="note_template not found")
        sections_json_str = json.dumps(body.sections_json) if body.sections_json is not None else None
        await c.execute(
            """
            UPDATE note_templates
            SET name          = COALESCE($2, name),
                description   = COALESCE($3, description),
                sections_json = COALESCE($4::jsonb, sections_json),
                updated_at    = NOW()
            WHERE id = $1
            """,
            template_id,
            body.name,
            body.description,
            sections_json_str,
        )
    return {"id": template_id, "ok": True}


@router.delete(
    "/note-templates/{template_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_note_template(
    template_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM note_templates WHERE id = $1", template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="note_template not found")
        await c.execute("DELETE FROM note_templates WHERE id = $1", template_id)


# ===========================================================================
# Agent triggers
# ===========================================================================

@router.get("/agent-triggers")
async def list_agent_triggers(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM agent_triggers ORDER BY op_name")
    return [
        {
            "id": r["id"],
            "op_name": r["op_name"],
            "event_name": r["event_name"],
            "debounce_json": r["debounce_json"],
            "threshold_json": r["threshold_json"],
            "enabled": r["enabled"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


class CreateAgentTriggerBody(BaseModel):
    op_name: str
    event_name: str
    debounce_json: Optional[dict] = None
    threshold_json: Optional[dict] = None
    enabled: bool = True


@router.post(
    "/agent-triggers",
    dependencies=[Depends(verify_json_csrf)],
    status_code=201,
)
async def create_agent_trigger(
    body: CreateAgentTriggerBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        new_id = await c.fetchval(
            """
            INSERT INTO agent_triggers (op_name, event_name, debounce_json, threshold_json, enabled)
            VALUES ($1, $2, $3::jsonb, $4::jsonb, $5)
            RETURNING id
            """,
            body.op_name,
            body.event_name,
            json.dumps(body.debounce_json) if body.debounce_json is not None else None,
            json.dumps(body.threshold_json) if body.threshold_json is not None else None,
            body.enabled,
        )
    return {"id": new_id}


class PatchAgentTriggerBody(BaseModel):
    debounce_json: Optional[dict] = None
    threshold_json: Optional[dict] = None
    enabled: Optional[bool] = None


@router.patch(
    "/agent-triggers/{trigger_id}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_agent_trigger(
    trigger_id: int,
    body: PatchAgentTriggerBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM agent_triggers WHERE id = $1", trigger_id)
        if not existing:
            raise HTTPException(status_code=404, detail="agent_trigger not found")
        debounce_str = json.dumps(body.debounce_json) if body.debounce_json is not None else None
        threshold_str = json.dumps(body.threshold_json) if body.threshold_json is not None else None
        await c.execute(
            """
            UPDATE agent_triggers
            SET enabled        = COALESCE($2, enabled),
                debounce_json  = COALESCE($3::jsonb, debounce_json),
                threshold_json = COALESCE($4::jsonb, threshold_json),
                updated_at     = NOW()
            WHERE id = $1
            """,
            trigger_id,
            body.enabled,
            debounce_str,
            threshold_str,
        )
    return {"id": trigger_id, "ok": True}


@router.delete(
    "/agent-triggers/{trigger_id}",
    dependencies=[Depends(verify_json_csrf)],
    status_code=204,
)
async def delete_agent_trigger(
    trigger_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM agent_triggers WHERE id = $1", trigger_id)
        if not existing:
            raise HTTPException(status_code=404, detail="agent_trigger not found")
        await c.execute("DELETE FROM agent_triggers WHERE id = $1", trigger_id)


# ---------------------------------------------------------------------------
# GET /audit-log  — paginated read-only (cursor-based on created_at)
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def list_audit_log(
    cursor: Optional[str] = None,
    limit: int = 50,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    limit = min(max(limit, 1), 200)

    conditions = []
    params: list = []
    idx = 1

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid cursor")
        conditions.append(f"al.created_at < ${idx}")
        params.append(cursor_dt)
        idx += 1

    if actor:
        conditions.append(f"(u.email ILIKE ${idx} OR u.name ILIKE ${idx})")
        params.append(f"%{actor}%")
        idx += 1

    if action:
        conditions.append(f"al.action ILIKE ${idx}")
        params.append(f"%{action}%")
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit + 1)

    query = f"""
        SELECT al.id, al.actor_user_id, al.action, al.target_kind, al.target_id,
               al.reason, al.payload_json, al.created_at,
               u.email AS actor_email, u.name AS actor_name
        FROM admin_audit_log al
        LEFT JOIN users u ON u.id = al.actor_user_id
        {where}
        ORDER BY al.created_at DESC
        LIMIT ${idx}
    """

    async with db.acquire() as c:
        rows = await c.fetch(query, *params)

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        next_cursor = items[-1]["created_at"].isoformat()

    return {
        "items": [
            {
                "id": r["id"],
                "actor_user_id": r["actor_user_id"],
                "actor_email": r["actor_email"],
                "actor_name": r["actor_name"],  # users.name
                "action": r["action"],
                "target_kind": r["target_kind"],
                "target_id": r["target_id"],
                "reason": r["reason"],
                "payload_json": json.loads(r["payload_json"]) if r["payload_json"] else None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in items
        ],
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# GET /retrieval-pipelines  — list all pipeline configs
# ---------------------------------------------------------------------------

@router.get("/retrieval-pipelines")
async def list_retrieval_pipelines(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM retrieval_pipelines ORDER BY feature")
    return [
        {
            "feature": r["feature"],
            "stages_json": json.loads(r["stages_json"]) if r["stages_json"] else [],
            "description": r["description"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


class PatchRetrievalPipelineBody(BaseModel):
    stages_json: Optional[list] = None
    description: Optional[str] = None


@router.patch(
    "/retrieval-pipelines/{feature}",
    dependencies=[Depends(verify_json_csrf)],
)
async def patch_retrieval_pipeline(
    feature: str,
    body: PatchRetrievalPipelineBody,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT feature FROM retrieval_pipelines WHERE feature = $1", feature
        )
        if not existing:
            raise HTTPException(status_code=404, detail="retrieval_pipeline not found")
        stages_str = json.dumps(body.stages_json) if body.stages_json is not None else None
        await c.execute(
            """
            UPDATE retrieval_pipelines
            SET stages_json = COALESCE($2::jsonb, stages_json),
                description = COALESCE($3, description),
                updated_at  = NOW()
            WHERE feature = $1
            """,
            feature,
            stages_str,
            body.description,
        )
    return {"feature": feature, "ok": True}


# ===========================================================================
# Subscription Requests — superadmin review
# ===========================================================================

import json as _json  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402

from src.services.subscription import apply_plan_to_user  # noqa: E402


@router.get("/subscription-requests")
async def list_subscription_requests_sa(
    status: str | None = None,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        if status:
            rows = await c.fetch(
                """
                SELECT sr.id, sr.status, sr.note, sr.amount_paid_vnd, sr.transfer_content,
                       sr.billing_months,
                       sr.reviewer_note, sr.refund_requested, sr.refund_qr_path,
                       sr.created_at, sr.reviewed_at, sr.cancelled_at,
                       p.name AS plan_name, p.label AS plan_label,
                       u.email AS boss_email, u.name AS boss_name,
                       cp.name AS current_plan_name
                FROM subscription_requests sr
                JOIN plans p ON p.id = sr.plan_id
                JOIN users u ON u.id = sr.boss_id
                LEFT JOIN plans cp ON cp.id = u.plan_id
                WHERE sr.status = $1
                ORDER BY sr.created_at DESC
                """,
                status,
            )
        else:
            rows = await c.fetch(
                """
                SELECT sr.id, sr.status, sr.note, sr.amount_paid_vnd, sr.transfer_content,
                       sr.billing_months,
                       sr.reviewer_note, sr.refund_requested, sr.refund_qr_path,
                       sr.created_at, sr.reviewed_at, sr.cancelled_at,
                       p.name AS plan_name, p.label AS plan_label,
                       u.email AS boss_email, u.name AS boss_name,
                       cp.name AS current_plan_name
                FROM subscription_requests sr
                JOIN plans p ON p.id = sr.plan_id
                JOIN users u ON u.id = sr.boss_id
                LEFT JOIN plans cp ON cp.id = u.plan_id
                ORDER BY sr.created_at DESC
                """
            )
    result = []
    for r in rows:
        d = dict(r)
        for f in ("created_at", "reviewed_at", "cancelled_at"):
            if d.get(f):
                d[f] = d[f].isoformat()
        result.append(d)
    return result


@router.get("/subscription-requests/{req_id}")
async def get_subscription_request_sa(
    req_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT sr.*, p.name AS plan_name, p.label AS plan_label,
                   p.limits_json AS plan_limits,
                   u.email AS boss_email, u.name AS boss_name,
                   u.subscription_status AS current_status,
                   cp.name AS current_plan_name
            FROM subscription_requests sr
            JOIN plans p ON p.id = sr.plan_id
            JOIN users u ON u.id = sr.boss_id
            LEFT JOIN plans cp ON cp.id = u.plan_id
            WHERE sr.id = $1
            """,
            req_id,
        )
    if not row:
        raise HTTPException(404, "Request not found")
    d = dict(row)
    for f in ("created_at", "reviewed_at", "cancelled_at"):
        if d.get(f):
            d[f] = d[f].isoformat()
    return d


@router.post(
    "/subscription-requests/{req_id}/approve",
    dependencies=[Depends(verify_json_csrf)],
)
async def approve_subscription_request(
    req_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        req = await c.fetchrow(
            "SELECT boss_id, plan_id, status, billing_months FROM subscription_requests WHERE id=$1",
            req_id,
        )
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(400, "Request is not pending")

    overrides = payload.get("overrides") or {}
    await apply_plan_to_user(
        db, req["boss_id"], req["plan_id"], overrides,
        billing_months=req["billing_months"],
    )

    async with db.acquire() as c:
        await c.execute(
            "UPDATE subscription_requests SET status='approved', reviewed_at=NOW() WHERE id=$1",
            req_id,
        )
    return {"status": "approved", "request_id": req_id}


@router.post(
    "/subscription-requests/{req_id}/reject",
    dependencies=[Depends(verify_json_csrf)],
)
async def reject_subscription_request(
    req_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        req = await c.fetchrow(
            "SELECT status FROM subscription_requests WHERE id=$1", req_id
        )
        if not req or req["status"] != "pending":
            raise HTTPException(400, "Request not pending or not found")
        await c.execute(
            """
            UPDATE subscription_requests
            SET status='rejected', reviewed_at=NOW(), reviewer_note=$2
            WHERE id=$1
            """,
            req_id,
            payload.get("reviewer_note", ""),
        )
    return {"status": "rejected", "request_id": req_id}


@router.get("/payment-proof/{filename}")
async def get_payment_proof(
    filename: str,
    _: BossContext = Depends(require_superadmin),
) -> FileResponse:
    from pathlib import Path

    safe_name = Path(filename).name
    for subdir in ("payment_proofs", "refund_qr"):
        candidate = Path("uploads") / subdir / safe_name
        if candidate.exists():
            return FileResponse(str(candidate))
    raise HTTPException(404, "File not found")


# ===========================================================================
# Plans CRUD — superadmin
# ===========================================================================


@router.get("/plans")
async def list_plans_superadmin(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, label, limits_json, prices_json, is_active, sort_order FROM plans ORDER BY sort_order"
        )
    return [dict(r) for r in rows]


@router.post("/plans", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_plan_sa(
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    required = {"name", "label", "limits_json"}
    if not required.issubset(payload):
        raise HTTPException(400, f"Required fields: {required}")
    async with db.acquire() as c:
        try:
            row = await c.fetchrow(
                """
                INSERT INTO plans (name, label, limits_json, prices_json, sort_order)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, COALESCE($5, 99))
                RETURNING id, name
                """,
                payload["name"],
                payload["label"],
                _json.dumps(payload["limits_json"]),
                _json.dumps(payload.get("prices_json") or {}),
                payload.get("sort_order"),
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(409, "Plan name already exists")
            raise
    return {"id": row["id"], "name": row["name"]}


@router.patch("/plans/{plan_id}", dependencies=[Depends(verify_json_csrf)])
async def update_plan_sa(
    plan_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    allowed_fields = {"label", "limits_json", "prices_json", "is_active", "sort_order"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    async with db.acquire() as c:
        if updates.get("is_active") is False:
            count = await c.fetchval(
                "SELECT COUNT(*) FROM users WHERE plan_id=$1", plan_id
            )
            if count > 0:
                raise HTTPException(
                    400, f"Cannot deactivate plan: {count} users are on it"
                )
        sets = []
        vals = [plan_id]
        for i, (k, v) in enumerate(updates.items(), start=2):
            if k in ("limits_json", "prices_json"):
                sets.append(f"{k}=${i}::jsonb")
                vals.append(_json.dumps(v))
            else:
                sets.append(f"{k}=${i}")
                vals.append(v)
        sets.append("updated_at=NOW()")
        await c.execute(
            f"UPDATE plans SET {', '.join(sets)} WHERE id=$1",
            *vals,
        )
    return {"updated": 1}


# ---------------------------------------------------------------------------
# MCP catalog — danh mục integration đã kiểm duyệt
# ---------------------------------------------------------------------------


@router.get("/mcp-catalog")
async def list_mcp_catalog(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, description, url, icon_url, is_active, created_at FROM mcp_catalog ORDER BY name"
        )
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]


@router.post("/mcp-catalog", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_mcp_catalog(
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()
    if not name or not url:
        raise HTTPException(400, "name and url required")
    async with db.acquire() as c:
        new_id = await c.fetchval(
            """
            INSERT INTO mcp_catalog (name, description, url, icon_url)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            name, payload.get("description"), url, payload.get("icon_url"),
        )
    return {"id": new_id, "name": name}


@router.patch("/mcp-catalog/{item_id}", dependencies=[Depends(verify_json_csrf)])
async def update_mcp_catalog(
    item_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    allowed = {"name", "description", "url", "icon_url", "is_active"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid fields")
    sets, vals = [], [item_id]
    for i, (k, v) in enumerate(updates.items(), start=2):
        sets.append(f"{k}=${i}")
        vals.append(v)
    async with db.acquire() as c:
        await c.execute(f"UPDATE mcp_catalog SET {', '.join(sets)} WHERE id=$1", *vals)
    return {"updated": 1}


@router.delete("/mcp-catalog/{item_id}", status_code=204, dependencies=[Depends(verify_json_csrf)])
async def delete_mcp_catalog(
    item_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> None:
    async with db.acquire() as c:
        used = await c.fetchval(
            "SELECT COUNT(*) FROM mcp_servers WHERE catalog_id=$1", item_id
        )
        if used:
            raise HTTPException(400, f"Đang có {used} boss dùng integration này")
        await c.execute("DELETE FROM mcp_catalog WHERE id=$1", item_id)
