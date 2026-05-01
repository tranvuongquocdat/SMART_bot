"""
Channel layer — abstraction over messaging providers (Telegram, Messenger, Zalo, Web).

Core code (agent, tools, scheduler) talks to this layer through the `Messenger`
Protocol and receives `IncomingMessage` events. Never import provider SDKs
directly outside this package.
"""
from src.channels.base import (
    Attachment,
    IncomingMessage,
    Messenger,
    MessengerCapabilities,
    OutgoingMessage,
    UnsupportedOperation,
)

__all__ = [
    "Attachment",
    "IncomingMessage",
    "Messenger",
    "MessengerCapabilities",
    "OutgoingMessage",
    "UnsupportedOperation",
]
