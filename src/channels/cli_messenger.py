"""CLI channel — prints to terminal instead of sending HTTP requests.

Used by `scripts/cli_test.py` to test the full AI pipeline without
Telegram/Zalo.  Registered as provider="cli" in the channel registry.
"""
from __future__ import annotations

import time
import uuid

from src.channels.base import BaseMessenger, MessengerCapabilities, OutgoingMessage

# ANSI colours
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_t0: float = 0.0


def mark_start() -> None:
    """Call before dispatching to record wall-clock start."""
    global _t0
    _t0 = time.monotonic()


class CliMessenger(BaseMessenger):
    channel = "cli"
    capabilities = MessengerCapabilities(
        supports_edit=True,
        supports_markdown=True,
    )

    async def send_message(self, chat_id, text, *, format="markdown",
                           save_history=True, reply_to_message_id=None):
        elapsed = time.monotonic() - _t0 if _t0 else 0
        print(f"\n{_CYAN}[bot] {_DIM}({elapsed:.1f}s){_RESET}")
        print(text)
        return OutgoingMessage(message_id=str(uuid.uuid4()), chat_id=chat_id)

    async def edit_message(self, chat_id, message_id, text, *, format="markdown"):
        elapsed = time.monotonic() - _t0 if _t0 else 0
        print(f"\r{_GREEN}[edit] {_DIM}({elapsed:.1f}s){_RESET} {text[:120]}")

    async def delete_message(self, chat_id, message_id):
        pass  # silent

    async def get_bot_id(self) -> str:
        return "cli-bot"
