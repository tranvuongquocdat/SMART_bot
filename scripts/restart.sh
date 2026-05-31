#!/bin/bash
set -e
docker compose -f docker/docker-compose.yml up -d postgres qdrant
uv run alembic upgrade head
exec uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
