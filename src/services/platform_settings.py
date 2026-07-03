"""Platform settings — knob vận hành mức nền tảng, superadmin chỉnh qua UI.

Key-value JSONB, cache in-process TTL ngắn (đọc mỗi lượt chat — không đáng
một query/lượt khi giá trị đổi vài lần một năm).

Key hiện có:
  - history_window_dm / history_window_group: số tin lịch sử đưa vào context
    responder (boss override được ở Settings cá nhân).
  - raw_message_retention_days: TTL tin thô (override env RAW_MESSAGE_RETENTION_DAYS).
"""

from __future__ import annotations

import json
import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_TTL_S = 60.0

DEFAULTS: dict[str, Any] = {
    "history_window_dm": 12,
    "history_window_group": 12,
}


async def get_setting(pool, key: str, default: Any = None) -> Any:
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL_S:
        return hit[1]
    async with pool.acquire() as c:
        raw = await c.fetchval("SELECT value FROM platform_settings WHERE key=$1", key)
    value = default if raw is None else (json.loads(raw) if isinstance(raw, str) else raw)
    if raw is None and key in DEFAULTS:
        value = DEFAULTS[key]
    _CACHE[key] = (now, value)
    return value


async def set_setting(pool, key: str, value: Any) -> None:
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO platform_settings (key, value) VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
            """,
            key, json.dumps(value),
        )
    _CACHE.pop(key, None)


def clear_cache() -> None:
    """Cho test — xoá cache TTL."""
    _CACHE.clear()
