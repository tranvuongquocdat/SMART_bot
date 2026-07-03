#!/usr/bin/env python3
"""Seed legal documents (terms/privacy) từ config/seeds/legal/*.md.

Idempotent: kind đã có bản nào thì bỏ qua (publish bản mới đi qua trang
superadmin Legal, không phải seed lại).

Chạy: uv run python scripts/seed_legal.py
"""

import asyncio
from pathlib import Path

import asyncpg

DSN = "postgresql://smart:smart@localhost:5433/smart_bot"
SEED_DIR = Path(__file__).parent.parent / "config" / "seeds" / "legal"


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    for kind in ("terms", "privacy"):
        path = SEED_DIR / f"{kind}.md"
        if not path.exists():
            print(f"skip {kind}: {path} not found")
            continue
        existing = await conn.fetchval(
            "SELECT count(*) FROM legal_documents WHERE kind=$1", kind
        )
        if existing:
            print(f"skip {kind}: already has {existing} version(s)")
            continue
        await conn.execute(
            "INSERT INTO legal_documents (kind, version, content_md) VALUES ($1, 1, $2)",
            kind, path.read_text(),
        )
        print(f"seeded {kind} v1 ({path.stat().st_size} bytes)")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
