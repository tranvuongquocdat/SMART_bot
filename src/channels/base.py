"""ChannelAdapter Protocol — provider-agnostic inbound/outbound surface.

Each channel implementation (Zalo, Telegram, Lark…) implements this Protocol
so the rest of the system (agents, services) can stay provider-neutral.

Wire-level events:
  - Adapter publishes ``inbound.raw.<provider>`` with raw provider payload.
  - A per-provider Normalizer subscribes, transforms, and publishes
    ``message.captured`` (canonical schema in ``src/events/schema.py``).

Adapter is also a sender: ``send_text`` is invoked by the per-provider
``outbound.send`` subscriber.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class InboundMessage:
    bot_account_id: int
    provider: str
    chat_id: str
    chat_type: str  # 'dm' | 'group'
    provider_msg_id: str | None
    sender_provider_id: str | None
    sender_name: str | None
    text: str
    mentions_bot: bool
    reply_to_provider_msg_id: str | None
    media_kind: str | None
    media_url: str | None
    ts: datetime | None
    raw: Any = None


class BaseChannelAdapter:
    """Base cho adapter: cung cấp đường DUY NHẤT đẩy tin vào hệ thống.

    Adapter chỉ việc dịch wire-format -> InboundMessage rồi gọi _emit_inbound.
    Toàn bộ định danh/lọc/persist do InboundIngest (subscriber inbound.normalized).
    """

    def __init__(self, bus, *args, **kwargs):
        self.bus = bus

    async def _emit_inbound(self, msg: "InboundMessage") -> None:
        await self.bus.publish("inbound.normalized", {"message": msg})


class ChannelAdapter(Protocol):
    provider: str

    async def start_inbound(self, bot_acc) -> None: ...

    async def stop_inbound(self, bot_acc) -> None: ...

    async def send_text(
        self,
        bot_acc,
        chat_id: str,
        text: str,
        thread_kind: str,
    ) -> str: ...

    async def list_members(self, bot_acc, group_id: str) -> list[str]: ...

    def classify_thread_kind(self, chat_id: str) -> str:
        """Return 'user' | 'group' for a chat_id. Provider-specific heuristic."""
        ...

    def normalize_text(self, text: str) -> str:
        """Pre-send text transform (e.g. strip markdown for plain-text channels)."""
        ...

    async def health_check(self) -> dict[int, bool]:
        """Return {bot_account_id: is_alive}. Used by scheduler health job."""
        ...
