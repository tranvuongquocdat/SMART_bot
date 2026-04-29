"""Communication-domain handlers — wrap `src.tools.communication` functions."""
from __future__ import annotations

from src.agent_pkg.handlers._base import ToolHandler
from src.context import ChatContext
from src.tools import communication


class SendDmHandler(ToolHandler):
    name = "send_dm"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.send_dm(ctx, **args)


class BroadcastHandler(ToolHandler):
    name = "broadcast"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.broadcast(ctx, **args)


class GetCommunicationLogHandler(ToolHandler):
    name = "get_communication_log"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.get_communication_log(ctx, **args)


class ResolvePersonHandler(ToolHandler):
    name = "resolve_person"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.resolve_person(ctx, **args)


class LinkContactToPersonHandler(ToolHandler):
    name = "link_contact_to_person"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.link_contact_to_person(ctx, **args)


class ListUnlinkedContactsHandler(ToolHandler):
    name = "list_unlinked_contacts"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.list_unlinked_contacts(ctx, **args)


class GetGroupAdminsHandler(ToolHandler):
    name = "get_group_admins"
    async def handle(self, args: dict, ctx: ChatContext) -> str:
        return await communication.get_group_admins(ctx, **args)
