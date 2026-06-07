"""Tests for GET /api/v1/auth/csrf."""
from __future__ import annotations


def test_csrf_bootstrap_returns_200_and_sets_cookie(client):
    r = client.get("/api/v1/auth/csrf")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # The smart_csrf cookie must be present after the call
    assert "smart_csrf" in r.cookies


def test_csrf_bootstrap_idempotent_with_existing_cookie(client):
    # First call sets the cookie
    r1 = client.get("/api/v1/auth/csrf")
    assert r1.status_code == 200
    token1 = r1.cookies.get("smart_csrf")
    assert token1

    # Second call with the cookie already present should still return 200
    r2 = client.get("/api/v1/auth/csrf", cookies={"smart_csrf": token1})
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}
