"""Super-admin API endpoints for /api/v1/superadmin/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
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
# GET /bot-accounts/:id/messages — recent messages for a bot account
# Note: No dedicated per-account messages table exists yet; returns empty list.
# ---------------------------------------------------------------------------

@router.get("/bot-accounts/{account_id}/messages")
async def list_bot_account_messages(
    account_id: int,
    limit: int = 50,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        existing = await c.fetchrow("SELECT id FROM bot_accounts WHERE id = $1", account_id)
        if not existing:
            raise HTTPException(status_code=404, detail="bot account not found")
        # No per-account messages table exists yet; return empty list.
        # TODO(SP3+): query chat_messages or inbound_events filtered by bot_account_id.
    return []
