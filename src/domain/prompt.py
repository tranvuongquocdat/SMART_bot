from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Prompt:
    id: int
    key: str
    version: int
    body: str
    is_active: bool
    notes: str | None
    created_at: datetime
    created_by: int | None
