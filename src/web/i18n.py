"""Tiny request-time i18n helper for user-facing API messages.

The web UI has full VI/EN i18n; backend error/notification strings should follow
the requesting user's ``ui_language`` (carried on :class:`BossContext`). Default
is Vietnamese — fall back to VI for any non-'en' value.
"""

from __future__ import annotations

from src.repositories.base import BossContext


def tr(ctx: BossContext | None, *, vi: str, en: str) -> str:
    """Pick ``en`` when the user's UI language is English, otherwise ``vi``."""
    lang = getattr(ctx, "ui_language", None) if ctx is not None else None
    return en if lang == "en" else vi
