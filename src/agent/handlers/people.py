"""People-domain handlers — wrap `src.tools.people` functions."""
from __future__ import annotations

from src.agent.handlers._base import ToolHandler
from src.context import ChatContext
from src.services import people_service as people


class AddPeopleHandler(ToolHandler):
    name = "add_people"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.add_people(ctx, **args)


class GetPersonHandler(ToolHandler):
    """Routes both `get_person` and `get_people` (alias from legacy)."""
    name = "get_person"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.get_person(ctx, **args)


class GetPeopleAliasHandler(ToolHandler):
    name = "get_people"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.get_person(ctx, **args)


class ListPeopleHandler(ToolHandler):
    name = "list_people"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.list_people(ctx, **args)


class UpdatePeopleHandler(ToolHandler):
    name = "update_people"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.update_people(ctx, **args)


class DeletePeopleHandler(ToolHandler):
    name = "delete_people"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.delete_people(ctx, **args)


class CheckEffortHandler(ToolHandler):
    name = "check_effort"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.check_effort(ctx, **args)


class CheckTeamEngagementHandler(ToolHandler):
    name = "check_team_engagement"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await people.check_team_engagement(ctx, **args)
