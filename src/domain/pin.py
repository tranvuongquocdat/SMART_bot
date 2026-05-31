from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Pin:
    id: int
    boss_id: int
    group_note_id: int
    message_id: int
    note: str | None
    pinned_by: int
    pinned_at: datetime
