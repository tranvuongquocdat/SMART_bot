"""Tests for LLMClient factory — boss override vs Settings fallback."""
from __future__ import annotations

import pytest

from src.config import Settings
from src.infrastructure import crypto
from src.infrastructure.llm.factory import get_llm_client
from src.infrastructure.llm.openai import OpenAILLMClient


def _settings(**overrides) -> Settings:
    base = {
        "telegram_bot_token": "x",
        "lark_app_id": "x",
        "lark_app_secret": "x",
        "openai_api_key": "sk-default",
        "cohere_api_key": "x",
    }
    base.update(overrides)
    return Settings(**base)


def test_no_boss_config_falls_back_to_settings():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": None, "llm_model": None, "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    assert isinstance(client, OpenAILLMClient)
    assert client.chat_model == s.openai_chat_model
    assert client.embedding_model == s.openai_embedding_model
    assert client.embedding_dim == s.openai_embedding_dim


def test_boss_overrides_chat_model():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "openai", "llm_model": "gpt-5-pro",
        "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    assert client.chat_model == "gpt-5-pro"


def test_boss_encrypted_key_is_decrypted():
    key = crypto.generate_key()
    s = _settings(boss_credential_encryption_key=key)
    encrypted = crypto.encrypt("sk-boss-secret", key=key)
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "openai", "llm_model": None,
        "llm_api_key_encrypted": encrypted,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    # Access the private attr to verify decryption.
    assert client._api_key == "sk-boss-secret"


def test_boss_embedding_dim_overrides():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": None, "llm_model": None, "llm_api_key_encrypted": None,
        "embedding_provider": "openai", "embedding_model": "text-embedding-3-large",
        "embedding_dim": 3072,
    }
    client = get_llm_client(boss, s)
    assert client.embedding_dim == 3072
    assert client.embedding_model == "text-embedding-3-large"


def test_unknown_provider_raises():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "groq", "llm_model": "llama-3.1",
        "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    with pytest.raises(ValueError, match="provider 'groq' not supported"):
        get_llm_client(boss, s)
