from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ActionItemStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class ActionItem:
    id: int
    boss_id: int
    group_note_id: int
    text: str
    assignee_name: str | None
    due_at: datetime | None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
