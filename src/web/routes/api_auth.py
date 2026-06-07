"""Auth utility endpoints for the SPA (CSRF bootstrap, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.web.security import CSRF_COOKIE, ensure_csrf

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/csrf")
async def get_csrf(request: Request, response: Response) -> dict:
    """Ensure the smart_csrf cookie is set before the SPA submits the login form.

    The actual cookie is written by csrf_middleware on the way out — calling
    ensure_csrf() here stamps request.state.csrf_token so the middleware picks
    it up when the cookie is absent.
    """
    tok = ensure_csrf(request)
    # If the cookie is already present, ensure_csrf returns its value but does
    # NOT set request.state.csrf_token (middleware won't overwrite).  We still
    # want to confirm the value for the caller.
    if CSRF_COOKIE not in request.cookies:
        # Middleware will set it; we expose it eagerly too so the client can
        # use it immediately without a round-trip cookie parse race.
        response.set_cookie(
            CSRF_COOKIE,
            tok,
            max_age=30 * 24 * 3600,
            httponly=False,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
    return {"ok": True}
