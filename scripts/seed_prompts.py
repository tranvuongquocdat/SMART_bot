#!/usr/bin/env python3
"""Seed the prompts table from config/seeds/prompts/*.yaml.

CHẠY THỦ CÔNG (như seed_llm.sh) — không tự động trong app. Idempotent:
upsert theo (key, version); nếu yaml is_active=true thì kích hoạt version đó
(tắt các version active khác cùng key). Production: superadmin tune qua web admin.

Usage:
  uv run python scripts/seed_prompts.py            # seed tất cả file
  uv run python scripts/seed_prompts.py in_group   # chỉ seed key cho trước
"""
import asyncio
import sys
from pathlib import Path

import asyncpg
import yaml

DSN = "postgresql://smart:smart@localhost:5433/smart_bot"
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "seeds" / "prompts"


async def main():
    only = set(sys.argv[1:])
    conn = await asyncpg.connect(DSN)
    files = sorted(PROMPTS_DIR.glob("*.yaml"))
    for f in files:
        spec = yaml.safe_load(f.read_text())
        key = spec["key"]
        if only and key not in only:
            continue
        version = int(spec.get("version", 1))
        body = spec["body"]
        is_active = bool(spec.get("is_active", False))
        notes = spec.get("notes")
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO prompts (key, version, body, is_active, notes)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (key, version)
                  DO UPDATE SET body=EXCLUDED.body, notes=EXCLUDED.notes
                """,
                key, version, body, False, notes,
            )
            if is_active:
                await conn.execute(
                    "UPDATE prompts SET is_active=FALSE WHERE key=$1 AND is_active", key)
                await conn.execute(
                    "UPDATE prompts SET is_active=TRUE WHERE key=$1 AND version=$2",
                    key, version)
        print(f"seeded {key} v{version} active={is_active}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
