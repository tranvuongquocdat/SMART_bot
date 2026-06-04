"""Tests for verify_json_csrf dep used by SPA mutation endpoints."""
import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient, ASGITransport

from src.web.security import verify_json_csrf, CSRF_COOKIE

pytestmark = pytest.mark.asyncio


def _mk_app():
    app = FastAPI()

    @app.post("/_probe")
    async def probe(_: None = Depends(verify_json_csrf)):
        return {"ok": True}

    @app.get("/_probe_get")
    async def probe_get(_: None = Depends(verify_json_csrf)):
        return {"ok": True}

    return app


async def test_post_without_csrf_rejected():
    app = _mk_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/_probe")
        assert r.status_code == 403


async def test_post_with_mismatching_csrf_rejected():
    app = _mk_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set(CSRF_COOKIE, "tokA")
        r = await c.post("/_probe", headers={"X-CSRF-Token": "tokB"})
        assert r.status_code == 403


async def test_post_with_matching_csrf_passes():
    app = _mk_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.cookies.set(CSRF_COOKIE, "tok123")
        r = await c.post("/_probe", headers={"X-CSRF-Token": "tok123"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}


async def test_get_skips_csrf_check():
    app = _mk_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/_probe_get")
        assert r.status_code == 200
