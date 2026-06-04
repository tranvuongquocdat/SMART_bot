"""Admin (boss) API endpoints for /api/v1/admin/*."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from src.repositories.base import BossContext
from src.web.deps import get_db, require_boss

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _require_group_owner(
    group_id: int,
    ctx: BossContext,
    db: asyncpg.Pool,
) -> asyncpg.Record:
    """Fetch group_notes row and enforce ownership (boss can only see own groups)."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT gn.id,
                   COALESCE(gn.group_name, gn.chat_id) AS name,
                   gn.provider                          AS channel,
                   gn.boss_id                           AS owner_id,
                   gn.chat_id,
                   gn.msg_count_7d,
                   gn.updated_at
            FROM group_notes gn
            WHERE gn.id = $1
            """,
            group_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="group not found")
    if ctx.user_role != "superadmin" and row["owner_id"] != ctx.boss_id:
        raise HTTPException(status_code=403, detail="not your group")
    return row


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}  — group meta
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}")
async def group_detail(
    group_id: int,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Return group metadata including member count and 30-day message count."""
    row = await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        # Count messages in last 30 days for this group
        cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
        messages_30d = await c.fetchval(
            """
            SELECT COUNT(*)
            FROM messages
            WHERE boss_id = $1
              AND provider = $2
              AND chat_id  = $3
              AND ts       >= $4
            """,
            row["owner_id"],
            row["channel"],
            row["chat_id"],
            cutoff_30d,
        ) or 0

        # Last active: timestamp of most recent message
        last_active = await c.fetchval(
            """
            SELECT MAX(ts)
            FROM messages
            WHERE boss_id = $1
              AND provider = $2
              AND chat_id  = $3
            """,
            row["owner_id"],
            row["channel"],
            row["chat_id"],
        )

    async with db.acquire() as c:
        members_count = await c.fetchval(
            "SELECT COUNT(*) FROM group_members WHERE group_id=$1",
            group_id,
        ) or 0

    return {
        "id": row["id"],
        "name": row["name"],
        "channel": row["channel"],
        "members_count": int(members_count),
        "messages_30d": int(messages_30d),
        "last_active_at": last_active.isoformat() if last_active else None,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/timeline
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/timeline")
async def group_timeline(
    group_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Return paginated message timeline for a group (cursor = last message id)."""
    row = await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        if cursor:
            msgs = await c.fetch(
                """
                SELECT id,
                       COALESCE(sender_name, 'unknown') AS author_name,
                       'user'                           AS author_kind,
                       COALESCE(text, '')               AS text,
                       ts                               AS created_at
                FROM messages
                WHERE boss_id = $1
                  AND provider = $2
                  AND chat_id  = $3
                  AND id       < $4
                ORDER BY id DESC
                LIMIT $5
                """,
                row["owner_id"],
                row["channel"],
                row["chat_id"],
                cursor,
                limit,
            )
        else:
            msgs = await c.fetch(
                """
                SELECT id,
                       COALESCE(sender_name, 'unknown') AS author_name,
                       'user'                           AS author_kind,
                       COALESCE(text, '')               AS text,
                       ts                               AS created_at
                FROM messages
                WHERE boss_id = $1
                  AND provider = $2
                  AND chat_id  = $3
                ORDER BY id DESC
                LIMIT $4
                """,
                row["owner_id"],
                row["channel"],
                row["chat_id"],
                limit,
            )

    message_list = [
        {
            "id": int(m["id"]),
            "author_name": m["author_name"],
            "author_kind": m["author_kind"],
            "text": m["text"],
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        }
        for m in msgs
    ]
    next_cursor = message_list[-1]["id"] if len(message_list) == limit else None

    return {
        "messages": message_list,
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/stats
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/stats")
async def group_stats(
    group_id: int,
    range: str = Query(default="7d"),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Return message/task/reminder/decision counts for a group.

    tasks      => action_items table
    reminders  => scheduled_reminders table (group-scoped = scope='group')
    decisions  => no table yet; always 0
    """
    row = await _require_group_owner(group_id, ctx, db)

    # Parse range string: e.g. "7d", "30d"
    try:
        days = int(range.rstrip("d"))
    except (ValueError, AttributeError):
        days = 7
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with db.acquire() as c:
        messages = await c.fetchval(
            """
            SELECT COUNT(*) FROM messages
            WHERE boss_id=$1 AND provider=$2 AND chat_id=$3 AND ts>=$4
            """,
            row["owner_id"], row["channel"], row["chat_id"], cutoff,
        ) or 0

        # action_items are linked to group via group_note_id
        tasks = await c.fetchval(
            """
            SELECT COUNT(*) FROM action_items
            WHERE group_note_id=$1 AND created_at>=$2
            """,
            group_id,
            cutoff,
        ) or 0

        # scheduled_reminders are boss-scoped; no group_note_id FK
        # best-effort: count all boss reminders in range
        reminders = await c.fetchval(
            """
            SELECT COUNT(*) FROM scheduled_reminders
            WHERE boss_id=$1 AND created_at>=$2
            """,
            row["owner_id"],
            cutoff,
        ) or 0

        decisions = await c.fetchval(
            "SELECT COUNT(*) FROM decisions WHERE group_id=$1 AND created_at>=$2",
            group_id,
            cutoff,
        ) or 0

    return {
        "messages": int(messages),
        "tasks": int(tasks),
        "reminders": int(reminders),
        "decisions": int(decisions),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/members
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/members")
async def group_members(
    group_id: int,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """Return group member list from group_members table."""
    await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, display_name, role, last_seen_at, joined_at
            FROM group_members
            WHERE group_id = $1
            ORDER BY joined_at DESC
            """,
            group_id,
        )

    return [
        {
            "id": int(r["id"]),
            "display_name": r["display_name"],
            "role": r["role"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
            "joined_at": r["joined_at"].isoformat() if r["joined_at"] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/summary
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/summary")
async def group_summary(
    group_id: int,
    date: str = Query(default="today"),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Return group daily summary from group_summaries table."""
    await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT body, updated_at
            FROM group_summaries
            WHERE group_id = $1 AND date_label = $2
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            group_id,
            date,
        )

    if row:
        return {
            "body": row["body"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
    return {"body": None, "updated_at": None}


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/items
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/items")
async def group_items(
    group_id: int,
    date: str = Query(default="today"),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """Return tasks/reminders/decisions for a group on a given date.

    tasks from action_items; decisions table doesn't exist (skipped).
    reminders not group-linked in schema — returns action items only.
    """
    row = await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id,
                   'task'                              AS type,
                   text,
                   COALESCE(assignee_name, '')         AS assignee,
                   due_at,
                   created_at
            FROM action_items
            WHERE group_note_id = $1
            UNION ALL
            SELECT id,
                   'decision'                          AS type,
                   text,
                   COALESCE(decided_by, '')            AS assignee,
                   NULL                                AS due_at,
                   created_at
            FROM decisions
            WHERE group_id = $1
            ORDER BY created_at DESC
            LIMIT 100
            """,
            group_id,
        )

    return [
        {
            "id": int(r["id"]),
            "type": r["type"],
            "text": r["text"],
            "assignee": r["assignee"],
            "due_at": r["due_at"].isoformat() if r["due_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/groups/{group_id}/files
# ---------------------------------------------------------------------------

@router.get("/groups/{group_id}/files")
async def group_files(
    group_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """Return group file artifacts from group_artifacts table."""
    await _require_group_owner(group_id, ctx, db)

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, kind, name, url, created_at
            FROM group_artifacts
            WHERE group_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            group_id,
            limit,
        )

    return [
        {
            "id": int(r["id"]),
            "kind": r["kind"],
            "name": r["name"],
            "url": r["url"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
