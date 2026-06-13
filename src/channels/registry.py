"""ChannelRegistry — single source of truth for active channel adapters.

Each channel package (``src/channels/<provider>/``) exposes a ``setup(ctx)``
callable in its ``__init__.py`` that:
  1. constructs the channel's adapter (implementing ``ChannelAdapter``),
  2. returns the adapter so the registry can store it.

Inbound đi qua wrapper chung ``InboundIngest`` (đăng ký một lần ở app
lifespan) — adapter chỉ emit ``inbound.normalized``, không tự wire normalizer.

Discovery walks the channels directory at startup and invokes every
``setup`` it finds — adding a new channel is a drop-folder operation,
no edit to ``main.py``.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ChannelSetupContext:
    bus: Any
    pool: Any
    admin_repo: Any  # BotAccountsRepo with superadmin context
    outbound_service: Any | None = None  # for in-channel reply paths (handshake, etc.)


class ChannelRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, Any] = {}

    def register(self, adapter: Any) -> None:
        provider = getattr(adapter, "provider", None)
        if not provider:
            raise ValueError("adapter has no .provider attribute")
        if provider in self._adapters:
            raise ValueError(f"duplicate channel provider: {provider}")
        self._adapters[provider] = adapter

    def get(self, provider: str) -> Any | None:
        return self._adapters.get(provider)

    def providers(self) -> list[str]:
        return list(self._adapters.keys())

    def adapters(self) -> list[Any]:
        return list(self._adapters.values())


async def discover_and_load(
    registry: ChannelRegistry, ctx: ChannelSetupContext
) -> list[str]:
    """Scan ``src/channels/*/`` and invoke each package's ``setup(ctx)``.

    Returns the list of providers loaded.
    """
    base = Path(__file__).parent
    loaded: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if not (child / "__init__.py").exists():
            continue
        modname = f"src.channels.{child.name}"
        try:
            mod = importlib.import_module(modname)
        except Exception:
            log.exception("channel import failed: %s", modname)
            continue
        setup_fn = getattr(mod, "setup", None)
        if setup_fn is None:
            continue
        try:
            result = setup_fn(ctx)
            adapter = await result if asyncio.iscoroutine(result) else result
        except Exception:
            log.exception("channel setup failed: %s", modname)
            continue
        if adapter is None:
            continue
        registry.register(adapter)
        loaded.append(adapter.provider)
        log.info("channel loaded: %s", adapter.provider)
    return loaded


async def boot_inbound_for_all(
    registry: ChannelRegistry, admin_repo: Any
) -> None:
    """For each registered channel, start_inbound on every active bot_account.

    Called at app startup AFTER discover_and_load.
    """
    for adapter in registry.adapters():
        try:
            accs = await admin_repo.list_active_by_provider(adapter.provider)
        except Exception:
            log.exception(
                "channel boot: list_active_by_provider failed for %s",
                adapter.provider,
            )
            continue
        for acc in accs:
            try:
                await adapter.start_inbound(acc)
            except Exception:
                log.exception(
                    "channel boot: start_inbound failed provider=%s bot_acc=%s",
                    adapter.provider,
                    acc.id,
                )


async def shutdown_inbound_for_all(
    registry: ChannelRegistry, admin_repo: Any
) -> None:
    """For each channel, stop_inbound on every active bot_account."""
    for adapter in registry.adapters():
        try:
            accs = await admin_repo.list_active_by_provider(adapter.provider)
        except Exception:
            continue
        for acc in accs:
            try:
                await adapter.stop_inbound(acc)
            except Exception:
                pass
