"""Memory-domain handlers — wrap `src.tools.memory` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import memory


class ListPendingApprovalsHandler(ToolHandler):
    name = "list_pending_approvals"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await memory.list_pending_approvals(ctx)
