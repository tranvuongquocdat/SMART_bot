from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReminderScope(StrEnum):
    DM = "dm"
    GROUP = "group"
    BOTH = "both"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    FIRED = "fired"
    CANCELED = "canceled"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Reminder:
    id: int
    boss_id: int
    text: str
    due_at: datetime
    scope: str
    provider: str | None
    chat_id: str | None
    bot_account_id: int | None
    recurring: str | None
    action_item_id: int | None
    status: str
    fired_at: datetime | None
    last_error: str | None
    created_at: datetime
    created_by_op: str
