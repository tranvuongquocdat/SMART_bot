"""Task-domain handlers — wrap `src.tools.tasks` functions.

Phase 4b-2 migrates the underlying logic to `services/task_service.py`.
"""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import tasks_service as tasks


class CreateTaskHandler(ToolHandler):
    name = "create_task"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.create_task(ctx, **args)


class ListTasksHandler(ToolHandler):
    name = "list_tasks"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.list_tasks(ctx, **args)


class UpdateTaskHandler(ToolHandler):
    name = "update_task"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.update_task(ctx, **args)


class DeleteTaskHandler(ToolHandler):
    name = "delete_task"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.delete_task(ctx, **args)


class SearchTasksHandler(ToolHandler):
    name = "search_tasks"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.search_tasks(ctx, **args)


class ApproveTaskChangeHandler(ToolHandler):
    name = "approve_task_change"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.approve_task_change(ctx, **args)


class RejectTaskChangeHandler(ToolHandler):
    name = "reject_task_change"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await tasks.reject_task_change(ctx, **args)
