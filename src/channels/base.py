"""
Channel abstraction layer.

Every messaging provider implements `Messenger`. Core (agent/tools/scheduler)
talks to providers only through this interface.

Design rules:
- `chat_id` is always TEXT (string). Each provider stringifies its native id.
- `IncomingMessage` is the normalized event delivered to the router.
- Provider-specific extras live in `IncomingMessage.raw` — only for debug/logging.
- Capabilities a provider may not support (group admin ops on Messenger/Zalo,
  voice transcription, etc.) raise `UnsupportedOperation`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


class UnsupportedOperation(Exception):
    """Raised when a Messenger method is not supported by this channel."""


# --- Message format --------------------------------------------------------
# Providers render in different ways:
#   Telegram → Markdown / HTML
#   Messenger → plain (no markdown in unofficial, limited in official)
#   Zalo → plain
#   Web → markdown (client-rendered)
# Core passes a format hint; provider does best-effort rendering.

FormatHint = str  # "markdown" | "plain" | "html"


# --- Incoming events -------------------------------------------------------

@dataclass
class Attachment:
    """Media attached to an incoming message. url may be a provider-signed URL
    or a local path after the channel downloads it."""
    kind: str           # 'photo' | 'voice' | 'file' | 'video' | 'sticker'
    url: str = ""
    mime_type: str = ""
    filename: str = ""
    size_bytes: int = 0


@dataclass
class IncomingMessage:
    """Normalized inbound event from any channel."""
    channel: str                    # 'telegram' | 'messenger' | 'zalo' | 'web'
    chat_id: str                    # conversation id (DM or group) — string
    chat_type: str                  # 'dm' | 'group'
    sender_id: str                  # user id in the provider
    sender_name: str = ""
    text: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    is_mentioned: bool = False      # bot was @mentioned (groups)
    is_forwarded: bool = False
    reply_to_message_id: str | None = None
    reply_to_sender_id: str | None = None
    message_id: str = ""
    timestamp: int = 0              # unix seconds
    group_name: str = ""            # when chat_type='group'

    # Channel-specific harvest data — optional, provider may populate
    mentions: list[dict] = field(default_factory=list)        # [{id, name, username}]
    username_mentions: list[str] = field(default_factory=list)
    new_members: list[dict] = field(default_factory=list)     # [{id, name, username}]

    raw: dict = field(default_factory=dict)   # original provider payload (debug only)


@dataclass
class OutgoingMessage:
    """Result of a send/edit call — identifiers the channel returned."""
    message_id: str = ""
    chat_id: str = ""


# --- Capabilities ----------------------------------------------------------

@dataclass
class MessengerCapabilities:
    """Static capability flags so tools can feature-detect."""
    supports_groups: bool = False
    supports_group_admin: bool = False        # add/kick/pin/title/description
    supports_invite_links: bool = False
    supports_edit: bool = True
    supports_delete: bool = True
    supports_typing: bool = True
    supports_photos: bool = True
    supports_files: bool = True
    supports_voice: bool = False
    supports_markdown: bool = True


# --- Messenger protocol ----------------------------------------------------

IncomingHandler = Callable[[IncomingMessage], Awaitable[None]]


@runtime_checkable
class Messenger(Protocol):
    """Interface every channel provider must implement.

    Methods that a provider genuinely cannot support raise
    `UnsupportedOperation`. Callers that depend on optional features must
    check `capabilities` first.
    """
    channel: str                         # 'telegram' | ...
    capabilities: MessengerCapabilities

    # --- Lifecycle ---
    async def start(self, on_message: IncomingHandler) -> None:
        """Start listening. Blocks (or returns once a background task is running)
        and calls `on_message(IncomingMessage)` for every event."""
        ...

    async def stop(self) -> None: ...

    # --- Send ---
    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        format: FormatHint = "markdown",
        save_history: bool = True,
        reply_to_message_id: str | None = None,
    ) -> OutgoingMessage: ...

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        *,
        format: FormatHint = "markdown",
    ) -> None: ...

    async def delete_message(self, chat_id: str, message_id: str) -> None: ...

    async def typing(self, chat_id: str) -> None: ...

    # --- Media ---
    async def send_photo(
        self, chat_id: str, url_or_path: str, *, caption: str = ""
    ) -> OutgoingMessage: ...

    async def send_file(
        self, chat_id: str, url_or_path: str, *, filename: str = "", caption: str = ""
    ) -> OutgoingMessage: ...

    async def send_voice(
        self, chat_id: str, url_or_path: str
    ) -> OutgoingMessage: ...

    # --- Identity ---
    async def get_user_profile(self, user_id: str) -> dict:
        """Return {id, name, username, avatar_url, ...}. Best effort."""
        ...

    async def get_bot_id(self) -> str: ...

    # --- Group admin (optional — guarded by capabilities.supports_group_admin) ---
    async def get_chat_administrators(self, chat_id: str) -> list[dict]: ...
    async def get_chat_member(self, chat_id: str, user_id: str) -> dict: ...
    async def add_chat_member(self, chat_id: str, user_id: str) -> bool: ...
    async def set_chat_title(self, chat_id: str, title: str) -> bool: ...
    async def set_chat_description(self, chat_id: str, description: str) -> bool: ...
    async def pin_chat_message(self, chat_id: str, message_id: str) -> bool: ...
    async def unpin_all_chat_messages(self, chat_id: str) -> bool: ...
    async def ban_chat_member(self, chat_id: str, user_id: str) -> bool: ...
    async def unban_chat_member(self, chat_id: str, user_id: str) -> bool: ...
    async def create_invite_link(
        self, chat_id: str, *, member_limit: int = 1, expire_hours: int = 24
    ) -> str: ...


# --- Helper base class for providers ---------------------------------------
# Providers can inherit to get default UnsupportedOperation for ops they skip.

class BaseMessenger:
    """Mixin for concrete channels. Inherit and override the methods you
    support; the rest raise `UnsupportedOperation` by default."""
    channel: str = "base"
    capabilities: MessengerCapabilities = MessengerCapabilities()

    async def start(self, on_message: IncomingHandler) -> None:
        raise UnsupportedOperation(f"{self.channel}: start")

    async def stop(self) -> None: ...

    async def send_message(self, chat_id, text, *, format="markdown", save_history=True, reply_to_message_id=None):
        raise UnsupportedOperation(f"{self.channel}: send_message")

    async def edit_message(self, chat_id, message_id, text, *, format="markdown"):
        raise UnsupportedOperation(f"{self.channel}: edit_message")

    async def delete_message(self, chat_id, message_id):
        raise UnsupportedOperation(f"{self.channel}: delete_message")

    async def typing(self, chat_id):
        return  # no-op by default

    async def send_photo(self, chat_id, url_or_path, *, caption=""):
        raise UnsupportedOperation(f"{self.channel}: send_photo")

    async def send_file(self, chat_id, url_or_path, *, filename="", caption=""):
        raise UnsupportedOperation(f"{self.channel}: send_file")

    async def send_voice(self, chat_id, url_or_path):
        raise UnsupportedOperation(f"{self.channel}: send_voice")

    async def get_user_profile(self, user_id):
        return {"id": user_id, "name": "", "username": "", "avatar_url": ""}

    async def get_bot_id(self) -> str:
        raise UnsupportedOperation(f"{self.channel}: get_bot_id")

    async def get_chat_administrators(self, chat_id):
        raise UnsupportedOperation(f"{self.channel}: get_chat_administrators")

    async def get_chat_member(self, chat_id, user_id):
        raise UnsupportedOperation(f"{self.channel}: get_chat_member")

    async def add_chat_member(self, chat_id, user_id):
        raise UnsupportedOperation(f"{self.channel}: add_chat_member")

    async def set_chat_title(self, chat_id, title):
        raise UnsupportedOperation(f"{self.channel}: set_chat_title")

    async def set_chat_description(self, chat_id, description):
        raise UnsupportedOperation(f"{self.channel}: set_chat_description")

    async def pin_chat_message(self, chat_id, message_id):
        raise UnsupportedOperation(f"{self.channel}: pin_chat_message")

    async def unpin_all_chat_messages(self, chat_id):
        raise UnsupportedOperation(f"{self.channel}: unpin_all_chat_messages")

    async def ban_chat_member(self, chat_id, user_id):
        raise UnsupportedOperation(f"{self.channel}: ban_chat_member")

    async def unban_chat_member(self, chat_id, user_id):
        raise UnsupportedOperation(f"{self.channel}: unban_chat_member")

    async def create_invite_link(self, chat_id, *, member_limit=1, expire_hours=24):
        raise UnsupportedOperation(f"{self.channel}: create_invite_link")
