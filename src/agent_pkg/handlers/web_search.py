"""web_search handler — wraps `src.tools.web_search.web_search`.

Phase 4b-2 migrates the underlying function to a `WebSearchService`; for
4b-1 we wrap the existing function so the dispatcher pattern is exercised.
"""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import web_search as _legacy


class WebSearchHandler(ToolHandler):
    name = "web_search"

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        query = args.get("query", "")
        if not query:
            return "[TOOL_ERROR:bad_args] web_search: missing 'query'"
        return await _legacy.web_search(query=query)
