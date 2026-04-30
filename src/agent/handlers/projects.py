"""Project-domain handlers — wrap `src.tools.projects` functions."""
from __future__ import annotations

from src.agent.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import projects_service as projects


class CreateProjectHandler(ToolHandler):
    name = "create_project"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await projects.create_project(ctx, **args)


class GetProjectHandler(ToolHandler):
    name = "get_project"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await projects.get_project(ctx, **args)


class ListProjectsHandler(ToolHandler):
    name = "list_projects"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await projects.list_projects(ctx, **args)


class UpdateProjectHandler(ToolHandler):
    name = "update_project"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await projects.update_project(ctx, **args)


class DeleteProjectHandler(ToolHandler):
    name = "delete_project"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await projects.delete_project(ctx, **args)
