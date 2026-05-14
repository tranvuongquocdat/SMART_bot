"""Capturing messenger — for the /debug/test_message endpoint.

Reuses the BaseMessenger interface but stores send/edit calls into a
process-wide ContextVar list keyed per-request, so a single endpoint
invocation can collect all bot replies (placeholder + final text) and
return them in the HTTP response. No actual outbound traffic.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from src.channels.base import BaseMessenger, MessengerCapabilities, OutgoingMessage

# Set inside the debug endpoint; the messenger appends to whatever list
# this var holds. Outside the endpoint context the var is None and the
# messenger no-ops (defensive — should never get traffic in normal flow).
_capture: ContextVar[Optional[list[tuple[str, str]]]] = ContextVar(
    "capturing_messenger_buffer", default=None,
)


def set_capture_buffer(buf: list[tuple[str, str]]) -> object:
    """Bind a buffer for the current async context. Returns a token to reset."""
    return _capture.set(buf)


def reset_capture_buffer(token: object) -> None:
    _capture.reset(token)  # type: ignore[arg-type]


class CapturingMessenger(BaseMessenger):
    channel = "debug"
    capabilities = MessengerCapabilities(
        supports_edit=True,
        supports_markdown=True,
        supports_photos=False,
        supports_files=False,
    )

    async def send_message(self, chat_id, text, *, format="markdown",
                           save_history=True, reply_to_message_id=None):
        buf = _capture.get()
        if buf is not None:
            buf.append(("send", text))
        return OutgoingMessage(message_id=str(uuid.uuid4()), chat_id=chat_id)

    async def edit_message(self, chat_id, message_id, text, *, format="markdown"):
        buf = _capture.get()
        if buf is not None:
            buf.append(("edit", text))

    async def delete_message(self, chat_id, message_id):
        return  # no-op

    async def get_bot_id(self) -> str:
        return "debug-bot"
