from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MediaCacheEntry:
    id: int
    source_key: str
    source_kind: str
    media_text: str
    title: str | None
    fetched_at: datetime
    expires_at: datetime | None
