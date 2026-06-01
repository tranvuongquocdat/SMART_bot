"""Settings → AI helpers (test BYO key)."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Form, Request

from src.security.middleware import rate_check
from src.web.deps import get_current_boss
from src.web.security import verify_csrf

router = APIRouter(prefix="/api/ai")
logger = logging.getLogger(__name__)


@router.post("/test-key")
async def test_key(
    request: Request,
    provider: str = Form(...),
    api_key: str = Form(...),
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    """Send a single 1-token completion request to verify the key works.

    Returns a small JSON `{ok, status, message}`. Never logs the key value.
    """
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)

    # H1: 60 BYO-key tests / minute per boss.
    await rate_check(request, f"test_key:{ctx.boss_id}", limit=60, window_sec=60)

    provider = provider.lower().strip()
    if provider not in ("openai", "groq", "gemini"):
        return {"ok": False, "status": "invalid_provider", "message": "Provider không hợp lệ"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == "openai":
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            elif provider == "groq":
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            else:  # gemini
                r = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key},
                )
    except httpx.RequestError as e:
        logger.warning("test_key network err provider=%s: %s", provider, e)
        return {"ok": False, "status": "network_error", "message": "Không gọi được provider"}

    if r.status_code == 200:
        return {"ok": True, "status": "ok", "message": "Key hợp lệ"}
    if r.status_code in (401, 403):
        return {"ok": False, "status": "unauthorized", "message": "Key sai hoặc hết hạn"}
    return {
        "ok": False,
        "status": f"http_{r.status_code}",
        "message": f"Provider trả về {r.status_code}",
    }
