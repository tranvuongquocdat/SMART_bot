"""Review-schedule-domain handlers — wrap `src.tools.review_config` functions."""
from __future__ import annotations

from src.agent.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import review_config_service as review_config


class AddReviewScheduleHandler(ToolHandler):
    name = "add_review_schedule"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await review_config.add_review_schedule(ctx, **args)


class ListReviewSchedulesHandler(ToolHandler):
    name = "list_review_schedules"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await review_config.list_review_schedules(ctx)


class ToggleReviewHandler(ToolHandler):
    name = "toggle_review"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await review_config.toggle_review(ctx, **args)


class DeleteReviewScheduleHandler(ToolHandler):
    name = "delete_review_schedule"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await review_config.delete_review_schedule(ctx, **args)
