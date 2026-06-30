"""Google OAuth login via authlib."""

from __future__ import annotations

import logging

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.config import settings
from src.security.middleware import rate_check
from src.web.security import SESSION_COOKIE, SESSION_TTL, make_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oauth")

oauth = OAuth()
if settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET:
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("google_callback"))


@router.get("/google/login")
async def google_login(request: Request):
    if "google" not in oauth._clients:
        raise HTTPException(503, "Google OAuth not configured")
    redirect_uri = _redirect_uri(request)
    if redirect_uri not in settings.redirect_whitelist:
        raise HTTPException(400, f"redirect not allowed: {redirect_uri}")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    if "google" not in oauth._clients:
        raise HTTPException(503, "Google OAuth not configured")
    # H1: 30 callbacks / minute per source IP — protects against OAuth replay.
    ip = request.client.host if request.client else "unknown"
    await rate_check(request, f"oauth_cb:{ip}", limit=30, window_sec=60)
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("oauth callback failed: %s", e)
        raise HTTPException(400, "oauth callback failed") from e

    info = token.get("userinfo")
    if not info or not info.get("email"):
        raise HTTPException(400, "userinfo missing")
    if info.get("email_verified") is False:
        raise HTTPException(400, "email not verified")

    email = info["email"].lower()
    sub = info.get("sub")
    name = info.get("name")

    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT id FROM users WHERE google_sub=$1 OR email=$2",
            sub,
            email,
        )
        if row:
            uid = int(row["id"])
            await c.execute(
                "UPDATE users SET google_sub=COALESCE($1, google_sub), name=COALESCE($2, name) WHERE id=$3",
                sub,
                name,
                uid,
            )
        else:
            uid = int(
                await c.fetchval(
                    """
                    INSERT INTO users (email, name, google_sub, role)
                    VALUES ($1, $2, $3, 'boss') RETURNING id
                    """,
                    email,
                    name,
                    sub,
                )
            )
            from src.services.subscription import provision_new_boss

            await provision_new_boss(c, uid)

    response = RedirectResponse("/app", status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        make_session(uid),
        max_age=SESSION_TTL,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response
