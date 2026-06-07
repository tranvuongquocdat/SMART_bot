#!/bin/bash
# One-time setup: create smart_bot_test DB + apply migrations.
# Tests use this DB; the dev DB (smart_bot) is never touched.
# Conftest also auto-bootstraps, but this script is the explicit/idempotent path.

set -e

DEV_DSN="${POSTGRES_DSN:-postgresql://smart:smart@localhost:5433/smart_bot}"
TEST_DSN="${POSTGRES_TEST_DSN:-${DEV_DSN%/*}/smart_bot_test}"

echo "Test DSN: $TEST_DSN"

# Create the test database if it doesn't exist.
docker exec docker-postgres-1 psql -U smart -d postgres \
  -c "SELECT 'CREATE DATABASE smart_bot_test' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='smart_bot_test')\gexec"

# Apply migrations against the test DB.
POSTGRES_DSN="$TEST_DSN" uv run alembic upgrade head

echo "smart_bot_test ready."
