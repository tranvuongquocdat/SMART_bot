"""Group-domain handlers — wrap `src.tools.group` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import group_service as _group_tools


class ManageGroupHandler(ToolHandler):
    name = "manage_group"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _group_tools.manage_group(ctx, **args)


class SummarizeGroupConversationHandler(ToolHandler):
    name = "summarize_group_conversation"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _group_tools.summarize_group_conversation(ctx, **args)


class UpdateGroupNoteHandler(ToolHandler):
    name = "update_group_note"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _group_tools.update_group_note(ctx, **args)


class BroadcastToGroupHandler(ToolHandler):
    name = "broadcast_to_group"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await _group_tools.broadcast_to_group(ctx, **args)
