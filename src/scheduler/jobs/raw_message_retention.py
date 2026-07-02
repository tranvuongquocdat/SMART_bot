"""raw_message_retention — dọn tin nhắn thô quá TTL (PDPL retention).

Chỉ đụng dữ liệu THÔ (``messages`` + ``outbound_messages``) — spine knowledge
đã chưng cất giữ nguyên. ``knowledge_provenance`` mất theo tin (FK CASCADE):
chấp nhận, content tri thức còn nguyên, chỉ mất vết nguồn.

TTL: ``settings.RAW_MESSAGE_RETENTION_DAYS`` (0 = tắt). Xoá theo batch để
không giữ lock dài trên bảng nóng.

Spec: docs/superpowers/specs/2026-07-02-compliance-erasure-retention-design.md
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import settings

log = logging.getLogger(__name__)

BATCH = 5000


async def job(app_state: Any) -> dict[str, int]:
    days = settings.RAW_MESSAGE_RETENTION_DAYS
    if not days or days <= 0:
        return {"messages": 0, "outbound_messages": 0}

    deleted = {"messages": 0, "outbound_messages": 0}
    async with app_state.db_pool.acquire() as c:
        for table, ts_col in (("messages", "ts"), ("outbound_messages", "sent_at")):
            while True:
                status = await c.execute(
                    f"""
                    DELETE FROM {table} WHERE id IN (
                        SELECT id FROM {table}
                        WHERE {ts_col} < NOW() - make_interval(days => $1)
                        LIMIT {BATCH}
                    )
                    """,
                    days,
                )
                n = int(status.split()[-1])
                deleted[table] += n
                if n < BATCH:
                    break
    if any(deleted.values()):
        log.info("raw_message_retention: deleted=%s (ttl=%sd)", deleted, days)
    return deleted
