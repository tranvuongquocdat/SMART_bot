"""Summary-domain handlers — wrap `src.tools.summary` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import summary


class GetSummaryHandler(ToolHandler):
    name = "get_summary"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await summary.get_summary(ctx, **args)


class GetWorkloadHandler(ToolHandler):
    name = "get_workload"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await summary.get_workload(ctx, **args)


class GetProjectReportHandler(ToolHandler):
    name = "get_project_report"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await summary.get_project_report(ctx, **args)
