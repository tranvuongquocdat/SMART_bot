"""Reset-flow handlers — wrap `src.tools.reset` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import reset_service as reset


class InitiateResetHandler(ToolHandler):
    name = "initiate_reset"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reset.initiate_reset(ctx)


class ConfirmResetStep1Handler(ToolHandler):
    name = "confirm_reset_step1"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reset.confirm_reset_step1(ctx, **args)


class ExecuteResetHandler(ToolHandler):
    name = "execute_reset"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reset.execute_reset(ctx, **args)
