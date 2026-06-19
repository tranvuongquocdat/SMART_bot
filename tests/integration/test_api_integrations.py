"""Superadmin integration (search provider) key/cost/usage endpoints."""

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-integrations"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_integrations_requires_superadmin(client, logged_in_boss):
    r = client.get("/api/v1/superadmin/integrations")
    assert r.status_code == 403


def test_set_get_and_usage(client, logged_in_superadmin, clean_db):
    r = client.put(
        "/api/v1/superadmin/integrations/tavily",
        json={"api_key": "secret-key", "unit_cost_usd": 0.008},
        headers=_csrf(client),
    )
    assert r.status_code == 200

    data = client.get("/api/v1/superadmin/integrations").json()
    tav = next(i for i in data if i["provider"] == "tavily")
    assert tav["has_key"] is True
    assert tav["unit_cost_usd"] == 0.008

    usage = client.get("/api/v1/superadmin/integrations/tavily/usage?range=30").json()
    assert "totals" in usage and "daily" in usage


def test_test_key_marks_status(client, logged_in_superadmin, clean_db, monkeypatch):
    client.put(
        "/api/v1/superadmin/integrations/tavily",
        json={"api_key": "secret-key", "unit_cost_usd": 0.0},
        headers=_csrf(client),
    )

    async def _ok_search(self, query, *, max_results=5):
        return []

    monkeypatch.setattr("src.search.tavily.TavilyProvider.search", _ok_search)
    r = client.post("/api/v1/superadmin/integrations/tavily/test", headers=_csrf(client))
    assert r.status_code == 200
    assert r.json()["ok"] is True

    data = client.get("/api/v1/superadmin/integrations").json()
    tav = next(i for i in data if i["provider"] == "tavily")
    assert tav["status"]["ok"] is True
