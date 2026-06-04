"""Session + CSRF helpers.

- Session: signed cookie via itsdangerous (URLSafeTimedSerializer), TTL 30d.
- CSRF: double-submit cookie + header (X-CSRF-Token) validation.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.config import settings

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)

SESSION_COOKIE = "smart_session"
CSRF_COOKIE = "smart_csrf"
SESSION_TTL = 30 * 24 * 3600  # 30 days


def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session(cookie: str | None) -> int | None:
    if not cookie:
        return None
    try:
        data = _serializer.loads(cookie, max_age=SESSION_TTL)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    uid = data.get("uid")
    return int(uid) if uid is not None else None


def set_session_cookie(response: Response, uid: int, secure: bool = False) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session(uid),
        max_age=SESSION_TTL,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def ensure_csrf(request: Request) -> str:
    """Return existing CSRF cookie or mint a new token.

    The actual cookie is set by middleware on the response. Templates inject
    this value into the `csrf-token` meta tag so HTMX echoes it back.
    """
    tok = request.cookies.get(CSRF_COOKIE)
    if not tok:
        tok = secrets.token_urlsafe(16)
        # Stash so middleware can persist it on the response.
        request.state.csrf_token = tok
    return tok


def verify_csrf(request: Request) -> None:
    """Validate X-CSRF-Token header matches CSRF cookie. Form fallback also OK."""
    cookie_tok = request.cookies.get(CSRF_COOKIE)
    header_tok = request.headers.get("X-CSRF-Token")
    if cookie_tok and header_tok and cookie_tok == header_tok:
        return
    # Form-encoded fallback: check `_csrf` field in form body cache (set by route).
    form_tok = getattr(request.state, "form_csrf_token", None)
    if cookie_tok and form_tok and cookie_tok == form_tok:
        return
    raise HTTPException(status_code=403, detail="CSRF check failed")


def verify_json_csrf(request: Request) -> None:
    """For JSON API mutation endpoints. Checks X-CSRF-Token header
    against the smart_csrf cookie. Safe methods pass through."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="invalid csrf token")


async def csrf_middleware(request: Request, call_next):
    """Persist CSRF cookie + bridge form `_csrf` field into request.state.

    Idempotent: only sets cookie if (a) absent and (b) ensure_csrf was called.
    """
    # Capture form-encoded CSRF before the route reads the body (peek-lite).
    ctype = request.headers.get("content-type", "")
    if request.method == "POST" and "application/x-www-form-urlencoded" in ctype:
        # We do NOT consume the body here; the route reads via request.form().
        # The route or verify_csrf() will fall back to header check.
        pass
    response = await call_next(request)
    if CSRF_COOKIE not in request.cookies:
        # If a handler called ensure_csrf(), it set request.state.csrf_token.
        tok = getattr(request.state, "csrf_token", None)
        if tok:
            response.set_cookie(
                CSRF_COOKIE,
                tok,
                max_age=SESSION_TTL,
                httponly=False,  # readable by JS for header echo
                secure=request.url.scheme == "https",
                samesite="lax",
            )
    return response
