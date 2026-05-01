"""Shared helpers for repository implementations.

Every repo class follows the same shape:

    class FooRepo:
        def __init__(self, db: aiosqlite.Connection) -> None:
            self._db = db

        async def some_method(self, ...) -> ...:
            async with self._db.execute(...) as cur:
                row = await cur.fetchone()
            return dict(row) if row else None

Repos do NOT call `db.commit()` for read methods. Write methods call commit
inline (matches the existing function-style behaviour in `src/db.py`).
"""
from __future__ import annotations

from typing import Optional

import aiosqlite


def row_to_dict(row: Optional[aiosqlite.Row]) -> Optional[dict]:
    return dict(row) if row else None
