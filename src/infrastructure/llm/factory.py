"""LLMClient factory — resolves per-boss credentials with Settings fallback.

Today: only `openai` provider. Future Groq/Gemini/Anthropic = add a branch
in `get_llm_client`. Boss columns are forward-compat (Phase 3); NULL means
fall back to Settings.
"""
from __future__ import annotations

from src.config import Settings
from src.infrastructure import crypto
from src.infrastructure.llm.base import LLMClient
from src.infrastructure.llm.openai import OpenAILLMClient


_SUPPORTED_PROVIDERS = {"openai"}


def _resolve(boss_field, settings_field):
    """Boss column wins if non-empty, else Settings."""
    if boss_field:
        return boss_field
    return settings_field


def _decrypt_boss_key(boss: dict, settings: Settings) -> str:
    encrypted = boss.get("llm_api_key_encrypted")
    if not encrypted:
        return settings.openai_api_key
    return crypto.decrypt(encrypted, key=settings.boss_credential_encryption_key)


def get_llm_client(boss: dict, settings: Settings) -> LLMClient:
    """Build an LLMClient configured for `boss`. Falls back to Settings for
    any column the boss row doesn't set."""
    provider = _resolve(boss.get("llm_provider"), "openai")
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"provider {provider!r} not supported; supported: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    if provider == "openai":
        return OpenAILLMClient(
            api_key=_decrypt_boss_key(boss, settings),
            chat_model=_resolve(boss.get("llm_model"), settings.openai_chat_model),
            embedding_model=_resolve(
                boss.get("embedding_model"), settings.openai_embedding_model
            ),
            embedding_dim=_resolve(
                boss.get("embedding_dim"), settings.openai_embedding_dim
            ),
        )
    raise AssertionError("unreachable")  # _SUPPORTED_PROVIDERS gate
