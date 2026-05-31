from datetime import datetime
from typing import Literal

from pydantic import BaseModel

SCHEMA_VERSION = 1


class BaseEvent(BaseModel):
    schema_version: int = SCHEMA_VERSION
    occurred_at: datetime


class MessageCaptured(BaseEvent):
    message_id: int
    boss_id: int
    provider: str
    chat_id: str
    chat_type: Literal["dm", "group"]
    mentions_bot: bool
    sender_is_boss: bool


class NoteUpdated(BaseEvent):
    group_note_id: int
    boss_id: int
    version: int
    sections_changed: list[str]


class ReminderDue(BaseEvent):
    reminder_id: int
    boss_id: int


class RegistryInvalidated(BaseEvent):
    registry_name: Literal[
        "models",
        "prompts",
        "llm_routes",
        "feature_budgets",
        "retrieval_pipelines",
        "agent_triggers",
        "note_templates",
    ]
    key: str | None = None
    by_user_id: int


class OpFire(BaseEvent):
    """Published by TriggerEngine — operation handler subscribes to op.<name>.fire."""

    op_name: str
    reason: Literal["debounce", "threshold", "on_demand"]
    source_event: dict
