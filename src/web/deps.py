"""FastAPI dependencies for web routes."""

from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request

from src.config import settings
from src.repositories.base import BossContext
from src.web.security import SESSION_COOKIE, read_session


async def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


async def get_current_boss(request: Request) -> BossContext:
    """Resolve session cookie → BossContext.

    Raises 401 if not logged in or user row missing. Promotes to
    'superadmin' role if email is in SUPERADMIN_EMAILS env.
    """
    cookie = request.cookies.get(SESSION_COOKIE)
    uid = read_session(cookie)
    if not uid:
        raise HTTPException(status_code=401, detail="not logged in")
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, email, role, ui_language FROM users WHERE id=$1", uid
        )
    if not row:
        raise HTTPException(status_code=401, detail="user not found")
    # Superadmin promotion: env-allowlisted email OR explicit role column.
    # The role column path lets the web test channel mint a superadmin without
    # touching env (dev-mode convenience; see ENABLE_WEB_TEST_CHANNEL gate).
    db_role = row["role"]
    role = (
        "superadmin"
        if row["email"].lower() in settings.superadmin_emails_set
        or db_role == "superadmin"
        else db_role
    )
    ctx = BossContext(
        boss_id=int(row["id"]),
        user_role=role,
        ui_language=(row["ui_language"] or "vi"),
    )
    request.state.boss = ctx
    return ctx


async def get_optional_boss(request: Request) -> BossContext | None:
    """Same as get_current_boss but returns None instead of raising 401."""
    try:
        return await get_current_boss(request)
    except HTTPException:
        return None


async def require_superadmin(
    ctx: BossContext = Depends(get_current_boss),
) -> BossContext:
    if ctx.user_role != "superadmin":
        raise HTTPException(status_code=403, detail="superadmin only")
    return ctx


async def require_boss(
    ctx: BossContext = Depends(get_current_boss),
) -> BossContext:
    """Allow boss or superadmin (superadmin implies boss permissions)."""
    if ctx.user_role not in ("boss", "superadmin"):
        raise HTTPException(status_code=403, detail="boss only")
    return ctx
