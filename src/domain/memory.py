from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryScope(StrEnum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


@dataclass(frozen=True, slots=True)
class Memory:
    id: int
    boss_id: int
    scope: MemoryScope
    key: str | None
    content: str
    meta: dict[str, Any] = field(default_factory=dict)
    qdrant_point_id: str | None = None
    source: str = "agent_tool"
    created_at: datetime | None = None
    updated_at: datetime | None = None
