"""Zalo channel plugin entrypoint.

Called by ``src.channels.registry.discover_and_load`` at startup.
Constructs the adapter and wires the inbound normalizer.
"""

from __future__ import annotations

from src.channels.registry import ChannelSetupContext
from src.channels.zalo import normalizer as _normalizer
from src.channels.zalo.adapter import ZaloAdapter


def setup(ctx: ChannelSetupContext) -> ZaloAdapter:
    adapter = ZaloAdapter(ctx.bus, ctx.admin_repo)
    _normalizer.register(ctx.bus, ctx.pool, ctx.outbound_service)
    return adapter
