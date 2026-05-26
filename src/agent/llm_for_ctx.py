"""Helper to build a per-boss LLMClient from a ChatContext.

Phase 4b-3 wires every LLM call through the `LLMClient` Protocol. This
helper is the single entry point: callers do `llm = await get_llm_for_ctx(ctx)`
and then `llm.chat_with_tools(...)` / `llm.embed(...)`.

The factory looks up the boss row to read per-boss `llm_provider` /
`llm_model` / encrypted key (Phase 3 forward-compat columns); falls back
to `Settings` defaults when those are NULL. Boss row is fetched per call
because it can change at runtime (key rotation, plan switch). Cost is one
indexed SELECT per LLM round — negligible vs the LLM call itself.
"""
from __future__ import annotations

from src import db
from src.repositories.boss_repo import BossRepo
from src.config import Settings
from src.context import ChatContext
from src.infrastructure.llm.base import LLMClient
from src.infrastructure.llm.factory import get_llm_client


_settings_cache: Settings | None = None


def init_llm_settings(settings: Settings) -> None:
    """Called once from main.py lifespan with the live `Settings` instance."""
    global _settings_cache
    _settings_cache = settings


async def get_llm_for_ctx(ctx: ChatContext) -> LLMClient:
    """Resolve a configured LLMClient for the boss in `ctx`."""
    if _settings_cache is None:
        # Fallback for unit tests / import-time use: build defaults.
        settings = Settings()
    else:
        settings = _settings_cache
    boss = await (await db._repo("boss", BossRepo)).get(ctx.boss_chat_id) or {}
    return get_llm_client(boss, settings)


def get_default_llm() -> LLMClient:
    """Resolve a Settings-default LLMClient (no boss yet — onboarding flow).

    Used by paths that fire before a boss row exists (e.g., the onboarding
    extract loop for a brand-new user). Once the user is registered as a
    boss, callers should switch to `get_llm_for_ctx(ctx)`.
    """
    settings = _settings_cache or Settings()
    return get_llm_client({}, settings)
