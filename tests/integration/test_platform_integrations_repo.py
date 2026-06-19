import asyncpg
import pytest

from src.repositories.platform_integrations import PlatformIntegrationsRepo

DSN = "postgresql://smart:smart@localhost:5433/smart_bot"


@pytest.mark.asyncio
async def test_set_get_key_cost_and_usage():
    pool = await asyncpg.create_pool(DSN)
    try:
        await pool.execute("DELETE FROM integration_usage WHERE provider='tavily_test'")
        await pool.execute("DELETE FROM platform_integrations WHERE provider='tavily_test'")
        repo = PlatformIntegrationsRepo(pool)

        await repo.set_config("tavily_test", api_key="secret123", unit_cost_usd=0.008)
        cfg = await repo.get("tavily_test")
        assert cfg["unit_cost_usd"] == 0.008
        assert cfg["has_key"] is True
        assert await repo.get_api_key("tavily_test") == "secret123"  # decrypted

        await repo.set_status("tavily_test", False, "bad key")
        cfg = await repo.get("tavily_test")
        assert cfg["status"]["ok"] is False

        await repo.record_usage("tavily_test", boss_id=1, cost_usd=0.008)
        await repo.record_usage("tavily_test", boss_id=1, cost_usd=0.008)
        totals = await repo.usage_totals("tavily_test")
        assert totals["count"] == 2
        assert round(totals["cost"], 4) == 0.016

        daily = await repo.usage_daily("tavily_test", days=30)
        assert daily and daily[0]["count"] == 2
    finally:
        await pool.execute("DELETE FROM integration_usage WHERE provider='tavily_test'")
        await pool.execute("DELETE FROM platform_integrations WHERE provider='tavily_test'")
        await pool.close()
