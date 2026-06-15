"""Zalo channel plugin entrypoint.

Called by ``src.channels.registry.discover_and_load`` at startup.
Constructs the adapter; định danh/lọc/persist do InboundIngest (wrapper chung).
"""

from __future__ import annotations

from src.channels.registry import ChannelSetupContext
from src.channels.zalo.adapter import ZaloAdapter


def setup(ctx: ChannelSetupContext) -> ZaloAdapter:
    return ZaloAdapter(ctx.bus, ctx.admin_repo)
