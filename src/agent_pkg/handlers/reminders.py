"""Reminder-domain handlers — wrap `src.tools.reminder` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import reminder


class CreateReminderHandler(ToolHandler):
    name = "create_reminder"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reminder.create_reminder(ctx, **args)


class ListRemindersHandler(ToolHandler):
    name = "list_reminders"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reminder.list_reminders(ctx, **args)


class UpdateReminderHandler(ToolHandler):
    name = "update_reminder"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reminder.update_reminder(ctx, **args)


class DeleteReminderHandler(ToolHandler):
    name = "delete_reminder"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await reminder.delete_reminder(ctx, **args)
