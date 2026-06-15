"""Thông báo (chuông) — broadcast cho mọi user + thông báo riêng theo boss.

Trạng thái đã đọc lưu per-user (notification_reads) nên một broadcast vẫn theo
dõi được từng user đã đọc hay chưa. Mọi user đăng nhập đều đọc được phần của
mình; chỉ superadmin mới phát broadcast.
"""

from __future__ import annotations

from typing import Any


async def list_for_user(pool: Any, user_id: int, limit: int = 30) -> dict:
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT n.id, n.kind, n.title, n.body, n.link, n.created_at,
                   (r.read_at IS NOT NULL) AS is_read
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.id AND r.user_id = $1
            WHERE n.audience = 'broadcast' OR n.boss_id = $1
            ORDER BY n.created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        unread = await c.fetchval(
            """
            SELECT COUNT(*) FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.id AND r.user_id = $1
            WHERE (n.audience = 'broadcast' OR n.boss_id = $1) AND r.read_at IS NULL
            """,
            user_id,
        )
    return {
        "items": [
            {
                "id": r["id"],
                "kind": r["kind"],
                "title": r["title"],
                "body": r["body"],
                "link": r["link"],
                "created_at": r["created_at"].isoformat(),
                "is_read": r["is_read"],
            }
            for r in rows
        ],
        "unread_count": int(unread),
    }


async def mark_read(pool: Any, user_id: int, notification_id: int | None) -> int:
    """Đánh dấu đã đọc một thông báo, hoặc tất cả (notification_id=None).
    Chỉ đánh dấu trong phạm vi user thấy được. Trả số dòng ghi nhận."""
    async with pool.acquire() as c:
        if notification_id is not None:
            res = await c.execute(
                """
                INSERT INTO notification_reads (notification_id, user_id)
                SELECT n.id, $2 FROM notifications n
                WHERE n.id = $1 AND (n.audience='broadcast' OR n.boss_id = $2)
                ON CONFLICT DO NOTHING
                """,
                notification_id,
                user_id,
            )
        else:
            res = await c.execute(
                """
                INSERT INTO notification_reads (notification_id, user_id)
                SELECT n.id, $1 FROM notifications n
                LEFT JOIN notification_reads r
                  ON r.notification_id = n.id AND r.user_id = $1
                WHERE (n.audience='broadcast' OR n.boss_id = $1) AND r.read_at IS NULL
                ON CONFLICT DO NOTHING
                """,
                user_id,
            )
    # asyncpg execute trả "INSERT 0 N"
    try:
        return int(res.split()[-1])
    except Exception:
        return 0


async def notify_boss(
    pool: Any,
    boss_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO notifications (audience, boss_id, kind, title, body, link)
            VALUES ('boss', $1, $2, $3, $4, $5) RETURNING id
            """,
            boss_id,
            kind,
            title,
            body,
            link,
        )


async def broadcast(
    pool: Any,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO notifications (audience, boss_id, kind, title, body, link)
            VALUES ('broadcast', NULL, $1, $2, $3, $4) RETURNING id
            """,
            kind,
            title,
            body,
            link,
        )


async def list_broadcasts(pool: Any, limit: int = 50) -> list[dict]:
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, kind, title, body, link, created_at
            FROM notifications WHERE audience='broadcast'
            ORDER BY created_at DESC LIMIT $1
            """,
            limit,
        )
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "title": r["title"],
            "body": r["body"],
            "link": r["link"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
