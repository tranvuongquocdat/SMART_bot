"""web_search tool — pluggable provider (Tavily default), key from superadmin DB.

Key + unit cost live in ``platform_integrations`` (managed by superadmin). Each
search records a usage rollup (count + cost). On key/quota error the integration
status is flipped so the superadmin page shows it red.
"""

from __future__ import annotations

from src.repositories.platform_integrations import PlatformIntegrationsRepo
from src.tools.base import ToolResult
from src.tools.registry import tool

_PROVIDER = "tavily"


async def _get_provider(ctx):
    """Resolve the active search provider for this boss (None if no key set)."""
    key = await PlatformIntegrationsRepo(ctx.pool).get_api_key(_PROVIDER)
    if not key:
        return None
    from src.search.tavily import TavilyProvider

    return TavilyProvider(api_key=key)


@tool(
    name="web_search",
    description=(
        "Tra cứu web (tin tức / thông tin NGOÀI kho tri thức nội bộ). Trả danh sách "
        "{title, url, snippet}. Sau khi search, dùng `fetch_url` để đọc sâu một kết quả khi cần."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    feature="web_search",
    cost_class="medium",
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
    timeout_s=25,
)
async def web_search(ctx, query: str, max_results: int = 5) -> ToolResult:
    provider = await _get_provider(ctx)
    if provider is None:
        return ToolResult(content=None, error="search_unconfigured: chưa cấu hình tìm kiếm web")
    try:
        results = await provider.search(query, max_results=max_results)
    except Exception as e:  # noqa: BLE001
        try:
            await PlatformIntegrationsRepo(ctx.pool).set_status(_PROVIDER, False, str(e)[:200])
        except Exception:  # noqa: BLE001
            pass
        return ToolResult(content=None, error=f"search_failed: {e}")

    # Best-effort usage/cost rollup — failure here must not break the search.
    try:
        repo = PlatformIntegrationsRepo(ctx.pool)
        cfg = await repo.get(_PROVIDER)
        unit = float(cfg["unit_cost_usd"]) if cfg else 0.0
        await repo.record_usage(_PROVIDER, boss_id=ctx.boss_id, cost_usd=unit)
    except Exception:  # noqa: BLE001
        pass

    return ToolResult(
        content=[{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results]
    )
