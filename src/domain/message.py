from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ChatType(StrEnum):
    DM = "dm"
    GROUP = "group"
    PAGE = "page"


class MediaKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    URL = "url"
    YOUTUBE = "youtube"
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    boss_id: int
    provider: str
    chat_id: str
    chat_type: str
    provider_msg_id: str | None
    reply_to_msg_id: int | None
    sender_provider_id: str | None
    sender_name: str | None
    text: str | None
    media_kind: str | None
    media_url: str | None
    media_text: str | None
    ts: datetime
    ingested_at: datetime | None


@dataclass(frozen=True, slots=True)
class NewMessage:
    """Insert-time payload (no id, no ingested_at)."""
    provider: str
    chat_id: str
    chat_type: str
    provider_msg_id: str | None
    sender_provider_id: str | None
    sender_name: str | None
    text: str | None
    media_kind: str | None
    media_url: str | None
    media_text: str | None
    ts: datetime
