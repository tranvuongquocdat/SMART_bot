"""Tiny provider → Messenger registry.

Used by the legacy `telegram_singleton.send/edit_message` shims so they can
route to the right channel based on the conversation's provider, without
plumbing the AppContainer through every caller.

Filled by `main.py` lifespan. Empty until then.
"""
from __future__ import annotations

from src.channels.base import BaseMessenger

_messengers: dict[str, BaseMessenger] = {}


def register(provider: str, messenger: BaseMessenger) -> None:
    _messengers[provider] = messenger


def get(provider: str) -> BaseMessenger | None:
    return _messengers.get(provider)


def clear() -> None:
    _messengers.clear()
