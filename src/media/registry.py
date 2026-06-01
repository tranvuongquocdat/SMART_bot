"""Adapter registry — decorator + lookup by media kind.

Adapters self-register at import time via ``@media_adapter(supports=...)``.
``find_adapter`` returns an *instance* of the highest-priority adapter
that supports the requested kind. URL kind is auto-detected from the URL
when not supplied.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

_ADAPTERS: list[type] = []


def media_adapter(
    *,
    supports: set[str],
    priority: int = 10,
    requires_caps: set[str] = frozenset(),
):
    def deco(cls):
        cls.supports = set(supports)
        cls.priority = priority
        cls.requires_caps = set(requires_caps)
        _ADAPTERS.append(cls)
        return cls

    return deco


def find_adapter(
    media_kind: str | None = None,
    url: str | None = None,
    **adapter_kwargs: Any,
):
    """Return an adapter instance for ``media_kind`` (or detected from url).

    Adapter constructors are called with ``**adapter_kwargs``; adapters with
    no-arg constructors will simply ignore unknown kwargs only if their
    signature accepts ``**kwargs``. Callers should pass exactly the kwargs
    the chosen adapter advertises (see each adapter's ``__init__``).
    """
    if url and not media_kind:
        media_kind = _detect_from_url(url)
    if media_kind is None:
        raise LookupError("media_kind not specified and not detectable from url")
    candidates = sorted(
        [a for a in _ADAPTERS if media_kind in a.supports],
        key=lambda a: -a.priority,
    )
    if not candidates:
        raise LookupError(f"no adapter for {media_kind}")
    cls = candidates[0]
    try:
        return cls(**adapter_kwargs)
    except TypeError:
        # Adapter ignores kwargs — fall back to no-arg construction.
        return cls()


def _detect_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    return "url"


def list_adapters() -> list[type]:
    """For tests/diagnostics."""
    return list(_ADAPTERS)
