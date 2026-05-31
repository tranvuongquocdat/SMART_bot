import json

import asyncpg

from src.domain.model import FeatureBudget
from src.repositories.base import BossScopedRepo


def _row_to_budget(r: asyncpg.Record) -> FeatureBudget:
    trim = r["trim_policy_json"]
    if isinstance(trim, str):
        trim = json.loads(trim)
    return FeatureBudget(
        feature=r["feature"],
        max_input_tokens=r["max_input_tokens"],
        max_output_tokens=r["max_output_tokens"],
        trim_policy_json=trim or [],
        compression_strategy=r["compression_strategy"],
        cache_prefix_hint=r["cache_prefix_hint"],
        updated_at=r["updated_at"],
    )


class FeatureBudgetsRepo(BossScopedRepo):
    async def get(self, feature: str) -> FeatureBudget | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM feature_budgets WHERE feature=$1", feature
            )
            return _row_to_budget(row) if row else None

    async def list(self) -> list[FeatureBudget]:
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM feature_budgets ORDER BY feature")
            return [_row_to_budget(r) for r in rows]

    async def upsert(
        self,
        feature: str,
        max_input_tokens: int,
        max_output_tokens: int,
        trim_policy: list[str],
        compression_strategy: str = "none",
        cache_prefix_hint: str | None = None,
    ) -> None:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO feature_budgets (feature, max_input_tokens, max_output_tokens,
                                             trim_policy_json, compression_strategy,
                                             cache_prefix_hint)
                VALUES ($1,$2,$3,$4::jsonb,$5,$6)
                ON CONFLICT (feature) DO UPDATE SET
                  max_input_tokens=EXCLUDED.max_input_tokens,
                  max_output_tokens=EXCLUDED.max_output_tokens,
                  trim_policy_json=EXCLUDED.trim_policy_json,
                  compression_strategy=EXCLUDED.compression_strategy,
                  cache_prefix_hint=EXCLUDED.cache_prefix_hint,
                  updated_at=NOW()
                """,
                feature,
                max_input_tokens,
                max_output_tokens,
                json.dumps(trim_policy),
                compression_strategy,
                cache_prefix_hint,
            )
