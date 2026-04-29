"""Workspace + language handlers — wrap `src.tools.workspace`."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import workspace_service as _ws


class SetLanguageHandler(ToolHandler):
    name = "set_language"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _ws.set_language(ctx, **args)


class SwitchWorkspaceHandler(ToolHandler):
    name = "switch_workspace"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _ws.switch_workspace(ctx, **args)
