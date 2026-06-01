"""Common types for media adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MediaExtractResult:
    """Result of extracting text/metadata from a media artifact.

    ``media_text`` is the canonical extracted body (markdown-ish plain text);
    ``title`` is best-effort. ``extra`` carries adapter-specific metadata
    (e.g. youtube video id, page count) that downstream code may opt into.
    """

    media_text: str
    title: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class MediaAdapter(Protocol):
    """Structural interface for a media adapter.

    Adapters opt in to one or more ``supports`` kinds (url / youtube /
    tiktok / image / pdf / docx / xlsx / txt). The registry routes by kind,
    breaking ties on ``priority`` (higher wins).
    """

    supports: set[str]
    priority: int

    async def extract(
        self,
        url: str | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> MediaExtractResult: ...
