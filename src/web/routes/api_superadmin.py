"""Super-admin API endpoints for /api/v1/superadmin/*."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends

from src.repositories.base import BossContext
from src.web.deps import get_db, require_superadmin

router = APIRouter(prefix="/api/v1/superadmin", tags=["superadmin"])

_SLOTS = ("smart", "fast", "vision")


@router.get("/model-slots")
async def list_model_slots(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Return platform-default model for each slot (smart / fast / vision).

    Model data lives in the `models` table, not in env vars.  The slot name
    maps directly to the `tier` column.  If no platform-default model is
    registered for a slot the entry is returned with status "missing" (or
    "fallback" for the vision slot, which can fall back to smart).
    """
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT tier, name, provider
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
        else:
            model_name = None
            provider = None
            status = "fallback" if slot == "vision" else "missing"
        result.append({
            "slot": slot,
            "model": model_name,
            "provider": provider,
            "status": status,
        })
    return result


@router.get("/bot-accounts")
async def list_bot_accounts(
    range: str = "7d",
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    """Return all bot accounts with basic stats.

    SP1: no `bot_message` table exists yet — messages_in / messages_out are
    hardcoded to 0.  Online status is derived from `last_seen_at`.
    """
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
