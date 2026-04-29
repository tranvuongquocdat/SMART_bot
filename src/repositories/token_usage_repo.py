"""token_usage table — per-boss LLM cost tracking."""
from __future__ import annotations

import aiosqlite


class TokenUsageRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def log(
        self, boss_chat_id: str, source: str,
        prompt_tokens: int, completion_tokens: int, total_tokens: int,
    ) -> None:
        await self._db.execute(
            "INSERT INTO token_usage "
            "(boss_chat_id, source, prompt_tokens, completion_tokens, total_tokens) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(boss_chat_id), source, prompt_tokens, completion_tokens, total_tokens),
        )
        await self._db.commit()
