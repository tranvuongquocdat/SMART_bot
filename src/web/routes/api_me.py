"""Current user info endpoint for the SPA."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.repositories.base import BossContext
from src.web.deps import get_current_boss

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
