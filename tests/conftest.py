"""Shared test fixtures: db_pool + boss_user.

Tests run against a SEPARATE database (default: `<dbname>_test`), never the
dev/prod DB. Override with `POSTGRES_TEST_DSN`. The clean_db fixture asserts
the active database name ends with `_test` so a misconfigured run will fail
loudly rather than silently TRUNCATE production data.

Setup once: ./scripts/setup_test_db.sh
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from src.config import settings


def _resolve_test_dsn() -> str:
    """Return DSN for tests. Refuse anything not ending in '_test'."""
    explicit = os.environ.get("POSTGRES_TEST_DSN", "").strip()
    if explicit:
        dsn = explicit
    else:
        parsed = urlparse(settings.POSTGRES_DSN)
        base = parsed.path.lstrip("/")
        if base.endswith("_test"):
            dsn = settings.POSTGRES_DSN
        else:
            dsn = urlunparse(parsed._replace(path=f"/{base}_test"))
    db_name = urlparse(dsn).path.lstrip("/")
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"Test DSN must point at a *_test database (got {db_name!r}). "
            "Tests TRUNCATE on every fixture — refusing to run against dev/prod."
        )
    return dsn


TEST_DSN = _resolve_test_dsn()

# Redirect ALL Postgres access during tests to the test DB. This covers:
#   - asyncpg.create_pool calls in fixtures (explicit TEST_DSN)
#   - src.infra.db.create_pool() inside the app lifespan (reads settings)
#   - subprocesses (alembic) that read POSTGRES_DSN from env
settings.POSTGRES_DSN = TEST_DSN
os.environ["POSTGRES_DSN"] = TEST_DSN


def _maybe_bootstrap_test_db() -> None:
    """Create the test DB + apply migrations if missing.

    Idempotent; runs once at import time. Connects to `/postgres` admin DB to
    issue CREATE DATABASE, then shells out to alembic with the test DSN.
    """
    parsed = urlparse(TEST_DSN)
    target_db = parsed.path.lstrip("/")
    admin_dsn = urlunparse(parsed._replace(path="/postgres"))

    import asyncio

    async def _check_and_create() -> bool:
        conn = await asyncpg.connect(admin_dsn)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname=$1", target_db
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{target_db}"')
                return True  # newly created → needs migrations
            # Already exists; check if alembic is at head revision.
            test_conn = await asyncpg.connect(TEST_DSN)
            try:
                current_rev = await test_conn.fetchval(
                    "SELECT version_num FROM alembic_version LIMIT 1"
                ) if await test_conn.fetchval(
                    "SELECT to_regclass('public.alembic_version') IS NOT NULL"
                ) else None
            finally:
                await test_conn.close()
            return current_rev != "0005"
        finally:
            await conn.close()

    try:
        needs_migrate = asyncio.run(_check_and_create())
    except Exception as e:
        raise RuntimeError(
            f"Cannot reach Postgres at {admin_dsn!r}: {e}. "
            "Run `docker compose -f docker/docker-compose.yml up -d postgres` first."
        ) from e

    if needs_migrate:
        env = os.environ.copy()
        env["POSTGRES_DSN"] = TEST_DSN
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            env=env,
            check=True,
        )


_maybe_bootstrap_test_db()


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(
        TEST_DSN, min_size=1, max_size=5, command_timeout=30
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    """Truncate user-data tables in dependency order before test."""
    async with db_pool.acquire() as c:
        # Defense-in-depth: never TRUNCATE against a non-_test DB even if
        # _resolve_test_dsn() was bypassed somehow.
        current = await c.fetchval("SELECT current_database()")
        if not current.endswith("_test"):
            raise RuntimeError(
                f"Refuse to TRUNCATE against {current!r} — must end in '_test'."
            )
        await c.execute(
            """
            TRUNCATE
              admin_audit_log, boss_integrations, scheduled_reminders, action_items,
              projects,
              tool_call_log, token_usage, pins, outbound_messages, messages,
              group_note_versions, group_notes, memory_entries, linking_tokens,
              account_links, bot_account_assignments, bot_accounts, users,
              web_group_members, web_groups, web_users,
              mcp_catalog,
              models, llm_routes, feature_budgets
            RESTART IDENTITY CASCADE
            """
        )
        # Re-seed the web test bot_account removed by truncation above.
        await c.execute(
            """
            INSERT INTO bot_accounts (provider, provider_user_id, display_name,
                                      account_kind, ownership, status)
            VALUES ('web', 'web-bot-1', 'Web Test Bot', 'personal', 'platform', 'active')
            ON CONFLICT DO NOTHING
            """
        )
    yield db_pool


async def _seed_all_tools(conn, boss_id: int) -> None:
    """Seed every registered tool as active — runtime filter is a strict
    intersect, so agent tests need rows in boss_active_tools."""
    from src.tools.registry import _REGISTRY

    await conn.executemany(
        """
        INSERT INTO boss_active_tools (boss_id, tool_name)
        VALUES ($1, $2) ON CONFLICT DO NOTHING
        """,
        [(boss_id, n) for n in _REGISTRY],
    )


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
        await _seed_all_tools(c, row["id"])
    return row


# ---------------------------------------------------------------------------
# Shared HTTP client + logged-in session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(clean_db):
    """Sync TestClient wrapping the FastAPI app; DB is clean before each test."""
    from src import main as main_mod

    with TestClient(main_mod.app) as c:
        yield c


@pytest.fixture
def logged_in_boss(client, clean_db):
    """Seed a boss user, inject a session cookie, return a simple ctx object."""
    from src.web.security import SESSION_COOKIE, make_session

    def _seed():
        async def _async():
            async with clean_db.acquire() as c:
                row = await c.fetchrow(
                    "INSERT INTO users (email, name, role) VALUES ($1, $2, 'boss') RETURNING id",
                    "boss-shared@example.com",
                    "Shared Boss",
                )
                await _seed_all_tools(c, int(row["id"]))
                return int(row["id"])

        return asyncio.get_event_loop().run_until_complete(_async())

    uid = _seed()
    client.cookies.set(SESSION_COOKIE, make_session(uid))
    return type("Boss", (), {"boss_id": uid, "user_role": "boss"})()


@pytest.fixture
def logged_in_superadmin(client, clean_db):
    """Seed a superadmin user, inject a session cookie, return a simple ctx object."""
    from src.web.security import SESSION_COOKIE, make_session

    def _seed():
        async def _async():
            async with clean_db.acquire() as c:
                row = await c.fetchrow(
                    "INSERT INTO users (email, name, role) VALUES ($1, $2, 'superadmin') RETURNING id",
                    "superadmin-shared@example.com",
                    "Shared Superadmin",
                )
                return int(row["id"])

        return asyncio.get_event_loop().run_until_complete(_async())

    uid = _seed()
    client.cookies.set(SESSION_COOKIE, make_session(uid))
    return type("Sup", (), {"boss_id": uid, "user_role": "superadmin"})()


# ---------------------------------------------------------------------------
# group_notes seed fixtures (used by test_api_admin_groups.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_group_owned_by_boss(clean_db, logged_in_boss):
    """Insert a group_notes row owned by the logged-in boss."""

    def _seed():
        async def _async():
            async with clean_db.acquire() as c:
                gid = await c.fetchval(
                    """
                    INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (boss_id, provider, chat_id) DO UPDATE
                      SET group_name = EXCLUDED.group_name
                    RETURNING id
                    """,
                    logged_in_boss.boss_id,
                    "zalo",
                    "zalo-group-test-001",
                    "Phòng Test",
                )
                return int(gid)

        return asyncio.get_event_loop().run_until_complete(_async())

    gid = _seed()
    return type("Group", (), {"id": gid, "name": "Phòng Test"})()


@pytest.fixture
def seed_group_owned_by_other(clean_db):
    """Insert a group_notes row owned by a different boss (not logged_in_boss)."""

    def _seed():
        async def _async():
            async with clean_db.acquire() as c:
                other_id = await c.fetchval(
                    "INSERT INTO users (email, name, role) VALUES ($1, $2, 'boss') RETURNING id",
                    "other-boss-group@example.com",
                    "Other Boss",
                )
                gid = await c.fetchval(
                    """
                    INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    int(other_id),
                    "zalo",
                    "zalo-group-other-001",
                    "Other Group",
                )
                return int(gid)

        return asyncio.get_event_loop().run_until_complete(_async())

    gid = _seed()
    return type("Group", (), {"id": gid})()
