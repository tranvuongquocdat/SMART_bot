"""Web test channel — drop-folder entrypoint.

setup(ctx) được gọi bởi ChannelRegistry.discover_and_load. Trả về
adapter để registry lưu; route mount tách riêng ở main.py (cần access
sse_hub + repos qua app.state).
"""

from __future__ import annotations

from src.channels.registry import ChannelSetupContext
from src.channels.web import fanout
from src.channels.web.adapter import WebAdapter
from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo


def setup(ctx: ChannelSetupContext) -> WebAdapter:
    sse_hub = SSEHub()
    groups_repo = WebGroupsRepo(ctx.pool)
    users_repo = WebUsersRepo(ctx.pool)

    adapter = WebAdapter(bus=ctx.bus, sse_hub=sse_hub, groups_repo=groups_repo)

    # Inbound đi qua InboundIngest (wrapper chung) — web không còn normalizer riêng.
    fanout.register(ctx.bus, sse_hub, groups_repo, ctx.pool)

    # Expose handles cho routes.py (mounted ở main.py) qua attributes
    # trên adapter — registry chỉ giữ adapter instance.
    adapter.sse_hub = sse_hub
    adapter.users_repo = users_repo
    adapter.groups_repo = groups_repo
    adapter.outbound_service = ctx.outbound_service
    adapter.pool = ctx.pool
    return adapter
