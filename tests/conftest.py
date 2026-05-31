"""Shared test fixtures: db_pool + boss_user.

Integration tests require Postgres + migrations applied:
    docker compose -f docker/docker-compose.yml up -d postgres
    uv run alembic upgrade head
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from src.infra.db import create_pool


@pytest_asyncio.fixture
async def db_pool():
    pool = await create_pool()
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """Truncate user-data tables in dependency order before test."""
    async with db_pool.acquire() as c:
        await c.execute(
            """
            TRUNCATE
              admin_audit_log, boss_integrations, scheduled_reminders, action_items,
              tool_call_log, token_usage, pins, outbound_messages, messages,
              group_note_versions, group_notes, memory_entries, linking_tokens,
              account_links, bot_account_assignments, bot_accounts, users
            RESTART IDENTITY CASCADE
            """
        )
    yield db_pool


@pytest_asyncio.fixture
async def boss_user(clean_db):
    """Insert a single boss user, return (id, email, name)."""
    async with clean_db.acquire() as c:
        row = await c.fetchrow(
            """
            INSERT INTO users (email, name, role)
            VALUES ('boss@example.com', 'Test Boss', 'boss') RETURNING id, email, name
            """
        )
    return row
