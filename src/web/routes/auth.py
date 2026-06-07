"""Email/password login + logout (Google OAuth lives in oauth.py)."""

from __future__ import annotations

from pathlib import Path as _Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import bcrypt as _bcrypt

from src.config import settings
from src.security.middleware import rate_check
from src.web.deps import get_optional_boss
from src.web.security import (
    SESSION_COOKIE,
    SESSION_TTL,
    clear_session_cookie,
    ensure_csrf,
    make_session,
    verify_csrf,
)

router = APIRouter()

_SPA_INDEX = _Path("src/web/static/app/index.html")
_SPA_MISSING = _Path("src/web/templates/spa-missing.html")


def hash_password(plain: str) -> str:
    """Bcrypt-hash a password. Truncates to 72 bytes (bcrypt limit)."""
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(plain.encode("utf-8")[:72], salt).decode("utf-8")


def _safe_next(raw: str | None, fallback: str = "/app") -> str:
    """Only allow same-origin redirects beginning with a single '/'."""
    if not raw or not raw.startswith("/") or raw.startswith("//") or raw.startswith("/\\"):
        return fallback
    return raw


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: str | None = None,
    next: str | None = None,
    boss=Depends(get_optional_boss),
):
    target = _safe_next(next)
    if boss is not None:
        return RedirectResponse(target, status_code=303)
    # Mint the CSRF cookie so the React login form can read it.
    ensure_csrf(request)
    # Serve the React SPA; the client-side router handles /login.
    if _SPA_INDEX.exists():
        return FileResponse(_SPA_INDEX)
    return FileResponse(_SPA_MISSING, status_code=503)


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/app"),
    csrf_field: str = Form("", alias="_csrf"),
):
    # Form-field CSRF for non-HTMX form posts.
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)

    # H1: 5 login attempts / 5 minutes per source IP.
    ip = request.client.host if request.client else "unknown"
    await rate_check(request, f"login:{ip}", limit=5, window_sec=300)

    target = _safe_next(next)

    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, password_hash FROM users WHERE email=$1", email.lower()
        )
    if not row or not row["password_hash"]:
        return RedirectResponse(
            f"/login?error=sai+thong+tin&next={target}", status_code=303
        )
    try:
        pw_bytes = password.encode("utf-8")[:72]
        hash_bytes = row["password_hash"].encode("utf-8") if isinstance(
            row["password_hash"], str
        ) else bytes(row["password_hash"])
        ok = _bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        ok = False
    if not ok:
        return RedirectResponse(
            f"/login?error=sai+thong+tin&next={target}", status_code=303
        )

    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        make_session(int(row["id"])),
        max_age=SESSION_TTL,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout(request: Request, csrf_field: str = Form("", alias="_csrf")):
    request.state.form_csrf_token = csrf_field
    try:
        verify_csrf(request)
    except HTTPException:
        # Best-effort: even on CSRF fail, clear the session cookie.
        pass
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
