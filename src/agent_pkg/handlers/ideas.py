"""Idea-domain handlers — wrap `src.tools.ideas` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import ideas


class CreateIdeaHandler(ToolHandler):
    name = "create_idea"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await ideas.create_idea(ctx, **args)
