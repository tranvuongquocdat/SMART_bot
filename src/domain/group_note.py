from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class GroupNoteStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class GroupNote:
    id: int
    boss_id: int
    provider: str
    chat_id: str
    group_name: str | None
    content: str
    manually_edited_sections: list[str] = field(default_factory=list)
    last_seen_message_id: int | None = None
    status: str = "active"
    msg_count_7d: int = 0
    template_id: int | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class GroupNoteVersion:
    id: int
    group_note_id: int
    content: str
    emitted_by: str
    emitted_at: datetime
