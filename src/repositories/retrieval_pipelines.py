import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class RetrievalPipeline:
    feature: str
    stages_json: list[dict[str, Any]]
    description: str | None
    updated_at: datetime


def _row_to_pipeline(r: asyncpg.Record) -> RetrievalPipeline:
    stages = r["stages_json"]
    if isinstance(stages, str):
        stages = json.loads(stages)
    return RetrievalPipeline(
        feature=r["feature"],
        stages_json=stages or [],
        description=r["description"],
        updated_at=r["updated_at"],
    )


class RetrievalPipelinesRepo(BossScopedRepo):
    async def get(self, feature: str) -> RetrievalPipeline | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM retrieval_pipelines WHERE feature=$1", feature
            )
            return _row_to_pipeline(row) if row else None

    async def list(self) -> list[RetrievalPipeline]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM retrieval_pipelines ORDER BY feature")
            return [_row_to_pipeline(r) for r in rows]

    async def upsert(
        self, feature: str, stages: list[dict], description: str | None = None
    ) -> None:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO retrieval_pipelines (feature, stages_json, description)
                VALUES ($1,$2::jsonb,$3)
                ON CONFLICT (feature) DO UPDATE SET
                  stages_json=EXCLUDED.stages_json,
                  description=EXCLUDED.description,
                  updated_at=NOW()
                """,
                feature,
                json.dumps(stages),
                description,
            )
