"""Current user info + notifications endpoints for the SPA."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from src.repositories.base import BossContext
from src.web.deps import get_current_boss, get_db
from src.web.security import verify_json_csrf

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me")
async def get_me(ctx: BossContext = Depends(get_current_boss)) -> dict:
    roles = ["boss"]
    if ctx.user_role == "superadmin":
        roles.append("superadmin")
    return {
        "id": ctx.boss_id,
        "roles": roles,
    }


@router.get("/me/notifications")
async def my_notifications(
    ctx: BossContext = Depends(get_current_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.services import notifications

    return await notifications.list_for_user(db, ctx.boss_id)


@router.post("/me/notifications/read", dependencies=[Depends(verify_json_csrf)])
async def read_notifications(
    payload: dict | None = None,
    ctx: BossContext = Depends(get_current_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Đánh dấu đã đọc: {id} cho một thông báo, không có id = tất cả."""
    from src.services import notifications

    nid = (payload or {}).get("id")
    n = await notifications.mark_read(db, ctx.boss_id, int(nid) if nid else None)
    return {"marked": n}
