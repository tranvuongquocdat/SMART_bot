"""fetch_url handler — wraps `services.url_fetch_service.fetch_url`.

Replaces the bot's old habit of disclaiming "chưa thể mở link YouTube" by
giving it a concrete tool to fetch oEmbed metadata (YouTube/TikTok) or a
plain HTML summary (news, blogs, ...).
"""
from __future__ import annotations

from src.agent.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import url_fetch_service


class FetchUrlHandler(ToolHandler):
    name = "fetch_url"

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        url = args.get("url", "")
        if not url:
            return "[TOOL_ERROR:bad_args] fetch_url: missing 'url'"
        return await url_fetch_service.fetch_url(url=url)
