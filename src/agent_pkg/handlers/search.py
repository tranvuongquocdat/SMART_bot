"""Search-domain handlers — wrap `src.tools.search` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import search_service as _legacy_search


class SearchHistoryHandler(ToolHandler):
    name = "search_history"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _legacy_search.search_history(ctx, **args)


class SearchNotesHandler(ToolHandler):
    name = "search_notes"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _legacy_search.search_notes(ctx, **args)
