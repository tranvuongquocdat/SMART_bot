"""Web channel identity cho boss — dùng chung bởi admin chat và reminder firer.

Normalizer resolve boss của DM qua account_links, nên phải đảm bảo cả
web_users lẫn account_links cùng tồn tại.
"""

from __future__ import annotations

from typing import Any


async def get_or_create_boss_web_identity(pool: Any, boss_id: int) -> str:
    """Trả về web_user_id của boss, tự tạo (kèm account_link) nếu chưa có."""
    async with pool.acquire() as c:
        uid = await c.fetchval(
            """
            SELECT id FROM web_users
            WHERE boss_user_id=$1 AND is_boss
            ORDER BY created_at LIMIT 1
            """,
            boss_id,
        )
        if uid is None:
            name = await c.fetchval(
                "SELECT COALESCE(name, email) FROM users WHERE id=$1", boss_id
            )
            from src.channels.web.state_repo import WebUsersRepo

            uid = await WebUsersRepo(pool).create(
                name=name or f"Boss {boss_id}",
                is_boss=True,
                boss_user_id=boss_id,
            )
        await c.execute(
            """
            INSERT INTO account_links (boss_id, provider, provider_user_id)
            VALUES ($1, 'web', $2)
            ON CONFLICT (provider, provider_user_id) DO NOTHING
            """,
            boss_id,
            uid,
        )
        # Outbound web cần bot_account_assignment — thiếu là bot trả lời
        # thất bại im lặng (kể cả fallback khi LLM lỗi).
        bot_acc_id = await c.fetchval(
            "SELECT id FROM bot_accounts WHERE provider='web' AND status='active' LIMIT 1"
        )
        if bot_acc_id is not None:
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status)
                VALUES ($1, 'web', $2, 'platform_assigned', 'active')
                ON CONFLICT (boss_id, provider) DO UPDATE
                  SET status='active', bot_account_id=EXCLUDED.bot_account_id
                """,
                boss_id,
                bot_acc_id,
            )
    return uid
