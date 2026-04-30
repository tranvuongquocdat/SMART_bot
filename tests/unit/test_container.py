"""Tests for AppContainer wiring — every field is populated, instances are
of the expected type."""
from __future__ import annotations

import pytest

from src.config import Settings
from src.container import AppContainer, build_container
from src.repositories.boss_repo import BossRepo
from src.repositories.audit_repo import AuditRepo
from src.services.audit_service import AuditService


def _settings(tmp_path) -> Settings:
    return Settings(
        telegram_bot_token="x",
        lark_app_id="x",
        lark_app_secret="x",
        openai_api_key="sk-x",
        cohere_api_key="x",
        db_path=str(tmp_path / "container.db"),
    )


@pytest.mark.asyncio
async def test_build_container_populates_every_field(tmp_path):
    # Reset the global db singleton so this test gets a fresh connection
    # bound to the tmp_path DB. Any prior test that called get_db() leaves
    # _db non-None which would otherwise be reused here.
    from src import db as _db_mod
    await _db_mod.close_db()

    container = await build_container(_settings(tmp_path))
    try:
        assert isinstance(container, AppContainer)
        assert container.settings.openai_chat_model
        assert container.db is not None

        # Repositories are real instances bound to the container's connection.
        assert isinstance(container.boss_repo, BossRepo)
        assert isinstance(container.audit_repo, AuditRepo)
        assert container.boss_repo._db is container.db

        # Services receive their dependencies via constructor injection.
        assert isinstance(container.audit_service, AuditService)
        assert container.audit_service._repo is container.audit_repo

        # Channels start empty; main.py lifespan populates after build.
        assert container.messengers == {}
    finally:
        await _db_mod.close_db()
