"""Note-domain handlers — wrap `src.tools.note` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import note


class GetNoteHandler(ToolHandler):
    name = "get_note"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await note.get_note(ctx, **args)


class UpdateNoteHandler(ToolHandler):
    name = "update_note"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await note.update_note(ctx, **args)


class AppendNoteHandler(ToolHandler):
    name = "append_note"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await note.append_note(ctx, **args)
