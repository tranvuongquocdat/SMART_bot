"""Join-flow handlers — wrap `src.tools.join` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import join


class ListAvailableWorkspacesHandler(ToolHandler):
    name = "list_available_workspaces"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await join.list_available_workspaces(ctx)


class RequestJoinHandler(ToolHandler):
    name = "request_join"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await join.request_join(ctx, **args)


class ApproveJoinHandler(ToolHandler):
    name = "approve_join"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await join.approve_join(ctx, **args)


class RejectJoinHandler(ToolHandler):
    name = "reject_join"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await join.reject_join(ctx, **args)
