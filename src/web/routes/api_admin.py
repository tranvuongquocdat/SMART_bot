"""Admin (boss) API endpoints for /api/v1/admin/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from src.repositories.base import BossContext
from src.web.deps import get_db, require_boss
from src.web.i18n import tr
from src.web.security import verify_json_csrf

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# GET /dashboard  — boss home-page summary
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return dashboard summary: recent groups, today's items, 30-day stats, recent activity."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    async with db.acquire() as c:
        # Recent 5 groups
        recent_groups = await c.fetch(
            """
            SELECT id,
                   COALESCE(group_name, chat_id) AS name,
                   provider,
                   msg_count_7d,
                   updated_at
            FROM group_notes
            WHERE boss_id = $1
            ORDER BY updated_at DESC
            LIMIT 5
            """,
            ctx.boss_id,
        )

        # Today's open action items (due today or overdue)
        today_items = await c.fetch(
            """
            SELECT ai.id, ai.text, ai.due_at, ai.status, ai.assignee_name,
                   COALESCE(gn.group_name, gn.chat_id) AS group_name
            FROM action_items ai
            JOIN group_notes gn ON gn.id = ai.group_note_id
            WHERE ai.boss_id = $1
              AND ai.status = 'open'
            ORDER BY ai.due_at NULLS LAST, ai.id DESC
            LIMIT 10
            """,
            ctx.boss_id,
        )

        # 30-day stats
        msg_count = await c.fetchval(
            "SELECT count(*) FROM messages WHERE boss_id=$1 AND ts >= $2",
            ctx.boss_id, thirty_days_ago,
        )
        task_count = await c.fetchval(
            "SELECT count(*) FROM action_items WHERE boss_id=$1 AND created_at >= $2",
            ctx.boss_id, thirty_days_ago,
        )
        reminder_count = await c.fetchval(
            "SELECT count(*) FROM scheduled_reminders WHERE boss_id=$1 AND created_at >= $2",
            ctx.boss_id, thirty_days_ago,
        )
        decision_count = await c.fetchval(
            """
            SELECT count(*) FROM decisions d
            JOIN group_notes gn ON gn.id = d.group_id
            WHERE gn.boss_id = $1 AND d.created_at >= $2
            """,
            ctx.boss_id, thirty_days_ago,
        )

        # Previous 30-day window (60d → 30d ago) for delta %
        prev_msg_count = await c.fetchval(
            "SELECT count(*) FROM messages WHERE boss_id=$1 AND ts >= $2 AND ts < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_task_count = await c.fetchval(
            "SELECT count(*) FROM action_items WHERE boss_id=$1 AND created_at >= $2 AND created_at < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_reminder_count = await c.fetchval(
            "SELECT count(*) FROM scheduled_reminders WHERE boss_id=$1 AND created_at >= $2 AND created_at < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_decision_count = await c.fetchval(
            """
            SELECT count(*) FROM decisions d
            JOIN group_notes gn ON gn.id = d.group_id
            WHERE gn.boss_id = $1 AND d.created_at >= $2 AND d.created_at < $3
            """,
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )

        # Recent activity: last 10 items updated
        recent_activity = await c.fetch(
            """
            SELECT 'action_item' AS kind,
                   ai.id,
                   ai.text AS title,
                   ai.status,
                   ai.updated_at AS ts
            FROM action_items ai
            WHERE ai.boss_id = $1
            UNION ALL
            SELECT 'reminder' AS kind,
                   sr.id,
                   sr.text AS title,
                   sr.status,
                   sr.created_at AS ts
            FROM scheduled_reminders sr
            WHERE sr.boss_id = $1
            ORDER BY ts DESC
            LIMIT 10
            """,
            ctx.boss_id,
        )

    return {
        "recent_groups": [
            {
                "id": r["id"],
                "name": r["name"],
                "provider": r["provider"],
                "msg_count_7d": r["msg_count_7d"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in recent_groups
        ],
        "today_items": [
            {
                "id": r["id"],
                "text": r["text"],
                "due_at": r["due_at"].isoformat() if r["due_at"] else None,
                "status": r["status"],
                "assignee_name": r["assignee_name"],
                "group_name": r["group_name"],
            }
            for r in today_items
        ],
        "stats_30d": {
            "messages": int(msg_count or 0),
            "tasks": int(task_count or 0),
            "reminders": int(reminder_count or 0),
            "decisions": int(decision_count or 0),
        },
        "stats_prev_30d": {
            "messages": int(prev_msg_count or 0),
            "tasks": int(prev_task_count or 0),
            "reminders": int(prev_reminder_count or 0),
            "decisions": int(prev_decision_count or 0),
        },
        "recent_activity": [
            {
                "kind": r["kind"],
                "id": r["id"],
                "title": r["title"],
                "status": r["status"],
                "ts": r["ts"].isoformat(),
            }
            for r in recent_activity
        ],
    }


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
    await _require_group_owner(group_id, ctx, db)

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


# ---------------------------------------------------------------------------
# Settings: account  GET/PATCH /api/v1/admin/settings/account
# ---------------------------------------------------------------------------


@router.get("/settings/account")
async def get_settings_account(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return account profile (read-only fields + editable display name)."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT id, email, name, role,
                   google_sub IS NOT NULL     AS google_linked,
                   subscription_status,
                   subscription_expiry,
                   cost_cap_usd_daily
            FROM users WHERE id = $1
            """,
            ctx.boss_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    data = dict(row)
    data["cost_cap_usd_daily"] = float(data["cost_cap_usd_daily"] or 0)
    # Serialize datetimes
    if data.get("subscription_expiry"):
        data["subscription_expiry"] = data["subscription_expiry"].isoformat()
    return data


@router.patch("/settings/account", dependencies=[Depends(verify_json_csrf)])
async def patch_settings_account(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Update whitelisted profile fields: name, tz, language."""
    allowed = {"name", "tz", "language"}
    sets = {k: v for k, v in payload.items() if k in allowed}
    if not sets:
        return {"updated": 0}
    keys = list(sets.keys())
    vals = list(sets.values())
    col_exprs = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(keys))
    async with db.acquire() as c:
        await c.execute(
            f"UPDATE users SET {col_exprs} WHERE id=$1",
            ctx.boss_id,
            *vals,
        )
    return {"updated": 1}


# ---------------------------------------------------------------------------
# Settings: AI  GET/PATCH /api/v1/admin/settings/ai
#              PATCH /api/v1/admin/settings/ai/keys
# ---------------------------------------------------------------------------


from src.services.boss_ai_config import AiConfigError  # noqa: E402


def _ai_err(e: AiConfigError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.message)


@router.get("/settings/ai")
async def get_settings_ai(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return 3 model slots + masked API key info + available models list."""
    from src.services import boss_ai_config

    try:
        return await boss_ai_config.get_ai_settings(db, ctx.boss_id)
    except AiConfigError as e:
        raise _ai_err(e)


@router.patch("/settings/ai", dependencies=[Depends(verify_json_csrf)])
async def patch_settings_ai(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Update a single model slot or cost_cap_usd_daily.

    Accepted payload shapes:
      {slot: 'smart'|'fast'|'vision', model_id: int|null}
      {cost_cap_usd_daily: float}
    """
    from src.services import boss_ai_config

    slot = payload.get("slot")
    cap = payload.get("cost_cap_usd_daily")

    try:
        if slot:
            await boss_ai_config.set_model_slot(db, ctx.boss_id, slot, payload.get("model_id"))
            return {"updated": 1}
        if cap is not None:
            await boss_ai_config.set_cost_cap(db, ctx.boss_id, cap)
            return {"updated": 1}
    except AiConfigError as e:
        raise _ai_err(e)
    return {"updated": 0}


@router.patch("/settings/ai/keys", dependencies=[Depends(verify_json_csrf)])
async def patch_settings_ai_keys(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Save or clear a single BYO API key for a provider.

    Payload: {provider: 'openai'|'groq'|'gemini', api_key: str}
          or {provider: '...', clear: true}

    Keys are Fernet-encrypted at rest. Never echoed back.
    """
    from src.services import boss_ai_config

    provider = payload.get("provider", "")
    try:
        if payload.get("clear"):
            await boss_ai_config.clear_api_key(db, ctx.boss_id, provider)
        else:
            # validate=True: test khoá với provider trước khi lưu + ghi trạng thái
            # sống/chết. Lưu khoá chết là vô nghĩa ("Kiểm tra & lưu").
            await boss_ai_config.set_api_key(
                db,
                ctx.boss_id,
                provider,
                payload.get("api_key") or "",
                validate=True,
                base_url=payload.get("base_url"),
            )
    except AiConfigError as e:
        raise _ai_err(e)
    return {"updated": 1}


@router.post("/settings/ai/keys/check", dependencies=[Depends(verify_json_csrf)])
async def check_settings_ai_key(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Kiểm tra khoá đã lưu của 1 provider còn sống không, ghi lại trạng thái.

    Payload: {provider}. Trả {provider, present, ok, message, checked_at}.
    """
    from src.services import boss_ai_config

    try:
        return await boss_ai_config.check_key(db, ctx.boss_id, payload.get("provider", ""))
    except AiConfigError as e:
        raise _ai_err(e)


# ---------------------------------------------------------------------------
# Settings: AI — model riêng của boss (BYO)
#   POST   /api/v1/admin/settings/ai/models
#   DELETE /api/v1/admin/settings/ai/models/{model_id}
# ---------------------------------------------------------------------------


@router.post("/settings/ai/models", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def create_own_model(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Boss tự thêm model chạy bằng API key của mình.

    Payload: {provider, name, tier, vision?: bool, ctx_max?: int}
    Yêu cầu boss đã lưu BYO key cho provider — model riêng không có dữ liệu giá
    nên không được chạy trên quota nền tảng (lách cost cap).
    """
    from src.services import boss_ai_config

    try:
        new_id = await boss_ai_config.create_own_model(db, ctx, ctx.boss_id, payload)
    except AiConfigError as e:
        raise _ai_err(e)
    return {"id": new_id}


@router.patch("/settings/ai/models/{model_id}", dependencies=[Depends(verify_json_csrf)])
async def patch_own_model(
    model_id: int,
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Sửa thông số model riêng: tier, capabilities, cost, ctx_max."""
    from src.services import boss_ai_config

    try:
        await boss_ai_config.patch_own_model(db, ctx.boss_id, model_id, payload)
    except AiConfigError as e:
        raise _ai_err(e)
    return {"updated": 1}


@router.delete("/settings/ai/models/{model_id}", dependencies=[Depends(verify_json_csrf)])
async def delete_own_model(
    model_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.services import boss_ai_config

    try:
        await boss_ai_config.delete_own_model(db, ctx.boss_id, model_id)
    except AiConfigError as e:
        raise _ai_err(e)
    return {"deleted": 1}


# ---------------------------------------------------------------------------
# Settings: general  GET/PATCH /api/v1/admin/settings/general
# ---------------------------------------------------------------------------


@router.get("/settings/general")
async def get_settings_general(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return general/profile settings: name, tz, language (bot), ui_language (web)."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, name, tz, language, ui_language FROM users WHERE id=$1",
            ctx.boss_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    return dict(row)


# ---------------------------------------------------------------------------
# SP2-4: Groups list, create, delete
# ---------------------------------------------------------------------------

@router.get("/groups")
async def groups_list(
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """List all group_notes rows owned by the current boss (or all for superadmin)."""
    async with db.acquire() as c:
        if ctx.user_role == "superadmin":
            rows = await c.fetch(
                """
                SELECT gn.id,
                       gn.chat_id,
                       COALESCE(gn.group_name, wg.name, gn.chat_id) AS name,
                       gn.provider                          AS channel,
                       gn.is_active,
                       gn.updated_at,
                       (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = gn.id) AS members_count
                FROM group_notes gn
                LEFT JOIN web_groups wg ON wg.id = gn.chat_id
                ORDER BY gn.updated_at DESC NULLS LAST
                """
            )
        else:
            rows = await c.fetch(
                """
                SELECT gn.id,
                       gn.chat_id,
                       COALESCE(gn.group_name, wg.name, gn.chat_id) AS name,
                       gn.provider                          AS channel,
                       gn.is_active,
                       gn.updated_at,
                       (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = gn.id) AS members_count
                FROM group_notes gn
                LEFT JOIN web_groups wg ON wg.id = gn.chat_id
                WHERE gn.boss_id = $1
                ORDER BY gn.updated_at DESC NULLS LAST
                """,
                ctx.boss_id,
            )
    return [
        {
            "id": int(r["id"]),
            "chat_id": r["chat_id"],
            "name": r["name"],
            "channel": r["channel"],
            "is_active": bool(r["is_active"]),
            "members_count": int(r["members_count"]),
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.post("/groups", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def create_group(
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Create a new group_notes row for the current boss."""
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    channel = payload.get("channel", "web").strip() or "web"
    # Generate a unique chat_id for manually-created groups
    import uuid
    chat_id = f"manual-{uuid.uuid4().hex[:12]}"
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
            VALUES ($1, $2, $3, $4)
            RETURNING id, group_name, provider, updated_at
            """,
            ctx.boss_id,
            channel,
            chat_id,
            name,
        )
    return {
        "id": int(row["id"]),
        "name": row["group_name"],
        "channel": row["provider"],
        "members_count": 0,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.delete("/groups/{group_id}", dependencies=[Depends(verify_json_csrf)], status_code=204)
async def delete_group(
    group_id: int,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> None:
    """Delete a group_notes row (must be owned by current boss)."""
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        await c.execute("DELETE FROM group_notes WHERE id=$1", group_id)


# ---------------------------------------------------------------------------
# SP2-4: Group members add/remove
# ---------------------------------------------------------------------------

@router.post("/groups/{group_id}/members", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def add_group_member(
    group_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    """Add a member to a group."""
    await _require_group_owner(group_id, ctx, db)
    display_name = payload.get("display_name", "").strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name is required")
    external_id = payload.get("external_id") or None
    role = payload.get("role") or None
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            INSERT INTO group_members (group_id, display_name, external_id, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (group_id, external_id) DO UPDATE
              SET display_name = EXCLUDED.display_name,
                  role = EXCLUDED.role
            RETURNING id, display_name, role, joined_at
            """,
            group_id,
            display_name,
            external_id,
            role,
        )
    return {
        "id": int(row["id"]),
        "display_name": row["display_name"],
        "role": row["role"],
        "joined_at": row["joined_at"].isoformat() if row["joined_at"] else None,
    }


@router.delete("/groups/{group_id}/members/{member_id}", dependencies=[Depends(verify_json_csrf)], status_code=204)
async def remove_group_member(
    group_id: int,
    member_id: int,
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> None:
    """Remove a member from a group."""
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        result = await c.execute(
            "DELETE FROM group_members WHERE id=$1 AND group_id=$2",
            member_id,
            group_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="member not found")


# ---------------------------------------------------------------------------
# SP2-4: People search (for UserPicker autocomplete)
# ---------------------------------------------------------------------------

@router.get("/people")
async def people_search(
    q: str = Query(default="", max_length=100),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """Search workspace users by display_name (ILIKE). Limit 20."""
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, name AS display_name, email AS external_id
            FROM users
            WHERE name ILIKE $1
            ORDER BY name
            LIMIT 20
            """,
            f"%{q}%",
        )
    return [
        {
            "id": int(r["id"]),
            "display_name": r["display_name"] or r["external_id"],
            "external_id": r["external_id"],
        }
        for r in rows
    ]


@router.patch("/settings/general", dependencies=[Depends(verify_json_csrf)])
async def patch_settings_general(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Update name, tz, language (bot), ui_language (web)."""
    allowed = {"name", "tz", "language", "ui_language"}
    sets = {k: v for k, v in payload.items() if k in allowed}
    if not sets:
        return {"updated": 0}
    keys = list(sets.keys())
    vals = list(sets.values())
    col_exprs = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(keys))
    async with db.acquire() as c:
        await c.execute(
            f"UPDATE users SET {col_exprs} WHERE id=$1",
            ctx.boss_id,
            *vals,
        )
    return {"updated": 1}


# ---------------------------------------------------------------------------
# Reminders CRUD  GET/POST /api/v1/admin/reminders
#                 PATCH/DELETE /api/v1/admin/reminders/:id
# ---------------------------------------------------------------------------

def _reminder_row(r: asyncpg.Record) -> dict:
    return {
        "id": int(r["id"]),
        "text": r["text"],
        "due_at": r["due_at"].isoformat() if r["due_at"] else None,
        "status": r["status"],
        "scope": r["scope"],
        "provider": r["provider"],
        "chat_id": r["chat_id"],
        "recurring": r["recurring"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


@router.get("/reminders")
async def list_reminders(
    status: str = Query(default="pending"),
    db: asyncpg.Pool = Depends(get_db),
    ctx: BossContext = Depends(require_boss),
) -> list:
    """List reminders for current boss, optionally filtered by status."""
    if status == "all":
        if ctx.user_role == "superadmin":
            where_clause = ""
            params: list = []
        else:
            where_clause = "WHERE boss_id = $1"
            params = [ctx.boss_id]
    else:
        if ctx.user_role == "superadmin":
            where_clause = "WHERE status = $1"
            params = [status]
        else:
            where_clause = "WHERE boss_id = $1 AND status = $2"
            params = [ctx.boss_id, status]

    query = f"""
        SELECT id, text, due_at, status, scope, provider, chat_id, recurring, created_at
        FROM scheduled_reminders
        {where_clause}
        ORDER BY due_at ASC
        LIMIT 200
    """
    async with db.acquire() as c:
        rows = await c.fetch(query, *params)
    return [_reminder_row(r) for r in rows]


@router.post("/reminders", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def create_reminder(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Create a new reminder."""
    text = payload.get("text", "").strip()
    due_at_raw = payload.get("due_at", "")
    scope = payload.get("scope", "dm")

    if not text:
        raise HTTPException(400, "text is required")
    if not due_at_raw:
        raise HTTPException(400, "due_at is required")

    try:
        if isinstance(due_at_raw, str):
            if due_at_raw.endswith("Z"):
                due_at = datetime.fromisoformat(due_at_raw.replace("Z", "+00:00"))
            elif "+" in due_at_raw[10:]:
                due_at = datetime.fromisoformat(due_at_raw)
            else:
                due_at = datetime.fromisoformat(due_at_raw).replace(tzinfo=timezone.utc)
        else:
            raise ValueError("due_at must be a string")
    except (ValueError, IndexError):
        raise HTTPException(400, "invalid due_at format") from None

    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, status, created_by_op)
            VALUES ($1, $2, $3, $4, 'pending', 'web.api')
            RETURNING id, text, due_at, status, scope, provider, chat_id, recurring, created_at
            """,
            ctx.boss_id, text, due_at, scope,
        )
    return _reminder_row(row)


@router.patch("/reminders/{reminder_id}", dependencies=[Depends(verify_json_csrf)])
async def patch_reminder(
    reminder_id: int,
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Update reminder fields: status and/or due_at."""
    allowed = {"status", "due_at"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "no updatable fields provided")

    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT id, boss_id FROM scheduled_reminders WHERE id=$1",
            reminder_id,
        )
    if not existing:
        raise HTTPException(404, "reminder not found")
    if ctx.user_role != "superadmin" and existing["boss_id"] != ctx.boss_id:
        raise HTTPException(403, "not your reminder")

    set_parts = []
    vals: list = []
    param_idx = 1

    if "due_at" in updates:
        raw = updates["due_at"]
        try:
            if raw.endswith("Z"):
                due_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            elif "+" in raw[10:]:
                due_dt = datetime.fromisoformat(raw)
            else:
                due_dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            raise HTTPException(400, "invalid due_at format") from None
        set_parts.append(f"due_at=${param_idx}")
        vals.append(due_dt)
        param_idx += 1

    if "status" in updates:
        valid_statuses = {"pending", "done", "canceled"}
        if updates["status"] not in valid_statuses:
            raise HTTPException(400, f"status must be one of {valid_statuses}")
        set_parts.append(f"status=${param_idx}")
        vals.append(updates["status"])
        param_idx += 1

    vals.append(reminder_id)
    async with db.acquire() as c:
        row = await c.fetchrow(
            f"""
            UPDATE scheduled_reminders
            SET {', '.join(set_parts)}
            WHERE id=${param_idx}
            RETURNING id, text, due_at, status, scope, provider, chat_id, recurring, created_at
            """,
            *vals,
        )
    return _reminder_row(row)


@router.delete("/reminders/{reminder_id}", dependencies=[Depends(verify_json_csrf)], status_code=204)
async def delete_reminder(
    reminder_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    """Delete a reminder (hard delete)."""
    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT id, boss_id FROM scheduled_reminders WHERE id=$1",
            reminder_id,
        )
    if not existing:
        raise HTTPException(404, "reminder not found")
    if ctx.user_role != "superadmin" and existing["boss_id"] != ctx.boss_id:
        raise HTTPException(403, "not your reminder")

    async with db.acquire() as c:
        await c.execute("DELETE FROM scheduled_reminders WHERE id=$1", reminder_id)


# ===========================================================================
# Projects
# ===========================================================================


class _ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


def _project_row(row: asyncpg.Record) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "items_count": row["items_count"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.get("/projects")
async def list_projects(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    """List all projects for the authenticated boss, with action item count."""
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT p.id, p.name, p.description, p.created_at, p.updated_at,
                   COUNT(ai.id) AS items_count
            FROM projects p
            LEFT JOIN action_items ai ON ai.project_id = p.id
            WHERE p.boss_id = $1
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """,
            ctx.boss_id,
        )
    return [_project_row(r) for r in rows]


@router.post("/projects", dependencies=[Depends(verify_json_csrf)], status_code=201)
async def create_project(
    body: _ProjectCreate,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Create a new project."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            INSERT INTO projects (boss_id, name, description)
            VALUES ($1, $2, $3)
            RETURNING id, name, description, created_at, updated_at
            """,
            ctx.boss_id,
            body.name.strip(),
            body.description,
        )
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "items_count": 0,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.delete("/projects/{project_id}", dependencies=[Depends(verify_json_csrf)], status_code=204)
async def delete_project(
    project_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    """Delete a project (hard delete). action_items.project_id set to NULL by FK."""
    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT id, boss_id FROM projects WHERE id=$1", project_id
        )
    if not existing:
        raise HTTPException(404, "project not found")
    if ctx.user_role != "superadmin" and existing["boss_id"] != ctx.boss_id:
        raise HTTPException(403, "not your project")
    async with db.acquire() as c:
        await c.execute("DELETE FROM projects WHERE id=$1", project_id)


# ===========================================================================
# Action Items (boss-scoped, with filters)
# ===========================================================================


class _ActionItemPatch(BaseModel):
    done: Optional[bool] = None
    text: Optional[str] = None
    assignee_name: Optional[str] = None
    due_at: Optional[str] = None
    project_id: Optional[int] = None


def _action_item_row(row: asyncpg.Record) -> dict:
    return {
        "id": row["id"],
        "group_note_id": row["group_note_id"],
        "group_name": row["group_name"],
        "text": row["text"],
        "assignee_name": row["assignee_name"],
        "due_at": row["due_at"].isoformat() if row["due_at"] else None,
        "status": row["status"],
        "project_id": row["project_id"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/action-items")
async def list_action_items(
    group_id: Optional[int] = Query(None, alias="group_id"),
    project_id: Optional[int] = Query(None, alias="project_id"),
    done: Optional[bool] = Query(None),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    """List action items with optional filters: group_id, project_id, done."""
    # Map done bool to status filter
    status_filter: Optional[str] = None
    if done is True:
        status_filter = "done"
    elif done is False:
        status_filter = "open"

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT ai.id, ai.group_note_id, ai.text, ai.assignee_name,
                   ai.due_at, ai.status, ai.project_id, ai.created_at,
                   COALESCE(gn.group_name, gn.chat_id) AS group_name
            FROM action_items ai
            JOIN group_notes gn ON gn.id = ai.group_note_id
            WHERE ai.boss_id = $1
              AND ($2::BIGINT IS NULL OR ai.group_note_id = $2)
              AND ($3::BIGINT IS NULL OR ai.project_id = $3)
              AND ($4::TEXT IS NULL OR ai.status = $4)
            ORDER BY ai.status, ai.due_at NULLS LAST, ai.id DESC
            LIMIT 500
            """,
            ctx.boss_id,
            group_id,
            project_id,
            status_filter,
        )
    return [_action_item_row(r) for r in rows]


@router.patch("/action-items/{item_id}", dependencies=[Depends(verify_json_csrf)])
async def patch_action_item(
    item_id: int,
    body: _ActionItemPatch,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Patch an action item (toggle done, rename, reassign, etc.)."""
    async with db.acquire() as c:
        existing = await c.fetchrow(
            "SELECT id, boss_id, status FROM action_items WHERE id=$1", item_id
        )
    if not existing:
        raise HTTPException(404, "action item not found")
    if ctx.user_role != "superadmin" and existing["boss_id"] != ctx.boss_id:
        raise HTTPException(403, "not your item")

    set_parts: list[str] = []
    vals: list = []
    param_idx = 1

    if body.done is not None:
        set_parts.append(f"status=${param_idx}")
        vals.append("done" if body.done else "open")
        param_idx += 1
    if body.text is not None:
        set_parts.append(f"text=${param_idx}")
        vals.append(body.text.strip())
        param_idx += 1
    if body.assignee_name is not None:
        set_parts.append(f"assignee_name=${param_idx}")
        vals.append(body.assignee_name or None)
        param_idx += 1
    if body.due_at is not None:
        set_parts.append(f"due_at=${param_idx}")
        vals.append(body.due_at)
        param_idx += 1
    if body.project_id is not None:
        set_parts.append(f"project_id=${param_idx}")
        vals.append(body.project_id)
        param_idx += 1

    if not set_parts:
        raise HTTPException(400, "nothing to update")

    set_parts.append("updated_at=NOW()")
    vals.append(item_id)

    async with db.acquire() as c:
        row = await c.fetchrow(
            f"""
            UPDATE action_items
            SET {', '.join(set_parts)}
            WHERE id=${param_idx}
            RETURNING id, group_note_id, text, assignee_name, due_at,
                      status, project_id, created_at,
                      (SELECT COALESCE(gn.group_name, gn.chat_id)
                       FROM group_notes gn WHERE gn.id = group_note_id) AS group_name
            """,
            *vals,
        )
    return _action_item_row(row)


# ===========================================================================
# Channels  –  GET /api/v1/admin/channels
#              POST /api/v1/admin/channels/{provider}/connect  (stub)
#              DELETE /api/v1/admin/channels/{id}
# ===========================================================================

def _channel_row(r: asyncpg.Record) -> dict:
    """Serialize a bot_account_assignments + bot_accounts join row."""
    # Use the bot_accounts status as primary health indicator
    bot_status = r.get("bot_status") or "unknown"
    assign_status = r.get("status") or "unknown"
    dot: str
    if bot_status in ("active", "online"):
        dot = "ok"
    elif bot_status in ("warn", "degraded"):
        dot = "warn"
    elif bot_status in ("inactive", "offline", "error"):
        dot = "err"
    else:
        dot = "idle"

    connected_at = r.get("assigned_at")
    # Stable identifier: use "{boss_id}:{provider}" encoded as URL-safe string
    # For DELETE we use provider as the path param since PK is (boss_id, provider).
    return {
        "provider": r["provider"],
        "display_name": r.get("display_name") or None,
        "status": bot_status,
        "assign_status": assign_status,
        "status_dot": dot,
        "assignment_kind": r.get("assignment_kind"),
        "ownership": r.get("ownership"),
        "connected_at": connected_at.isoformat() if connected_at else None,
    }


@router.get("/channels")
async def list_channels(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    """Return all bot account assignments (channels) for the current boss."""
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT baa.boss_id,
                   baa.provider,
                   baa.assignment_kind,
                   baa.status,
                   baa.assigned_at,
                   ba.display_name,
                   ba.status  AS bot_status,
                   ba.account_kind,
                   ba.ownership
            FROM bot_account_assignments baa
            JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE baa.boss_id = $1
            ORDER BY baa.status, baa.provider
            """,
            ctx.boss_id,
        )
    return [_channel_row(r) for r in rows]


@router.post("/channels/{provider}/connect", dependencies=[Depends(verify_json_csrf)])
async def connect_channel(
    provider: str,
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Self-service connect: cấp phát bot account từ pool nền tảng.

    Zalo dùng acc cá nhân do nền tảng quản lý (không OAuth) — connect nghĩa là
    chọn acc ít tải nhất còn slot rồi kích hoạt inbound luôn (bấm Connect từ
    web chính là chấp nhận assignment).
    """
    from src.services.bot_account_service import BotAccountService, NoCapacityError
    from src.services.subscription import get_effective_limits

    provider = provider.lower().strip()

    async with db.acquire() as c:
        existing = await c.fetchval(
            """
            SELECT status FROM bot_account_assignments
            WHERE boss_id=$1 AND provider=$2 AND status IN ('active', 'pending_accept')
            """,
            ctx.boss_id,
            provider,
        )
        if existing:
            raise HTTPException(409, tr(ctx, vi="Kênh này đã được kết nối", en="This channel is already connected"))

        limits = await get_effective_limits(db, ctx.boss_id)
        if limits.max_active_channels is not None:
            active = await c.fetchval(
                """
                SELECT COUNT(*) FROM bot_account_assignments
                WHERE boss_id=$1 AND status='active' AND provider <> 'web'
                """,
                ctx.boss_id,
            )
            if active >= limits.max_active_channels:
                raise HTTPException(
                    400,
                    tr(
                        ctx,
                        vi=f"Đã đạt giới hạn {limits.max_active_channels} kênh của gói hiện tại",
                        en=f"Reached the {limits.max_active_channels}-channel limit of the current plan",
                    ),
                )

    registry = getattr(request.app.state, "channel_registry", None)
    adapter_map = (
        {a.provider: a for a in registry.adapters()} if registry is not None else {}
    )
    svc = BotAccountService(db, request.app.state.bus, adapter_map)
    try:
        bot_account_id = await svc.auto_assign(ctx.boss_id, provider)
    except NoCapacityError:
        raise HTTPException(
            409,
            tr(
                ctx,
                vi="Hiện chưa có tài khoản bot khả dụng cho kênh này — vui lòng liên hệ quản trị viên",
                en="No bot account is available for this channel right now — please contact an administrator",
            ),
        )
    await svc.accept(ctx.boss_id, provider)

    async with db.acquire() as c:
        display_name = await c.fetchval(
            "SELECT display_name FROM bot_accounts WHERE id=$1", bot_account_id
        )
    return {"provider": provider, "status": "active", "display_name": display_name}


@router.post("/channels/{provider}/link-token", dependencies=[Depends(verify_json_csrf)])
async def mint_link_token(
    provider: str,
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Cấp token handshake để boss nhắn ``/start <token>`` từ TÀI KHOẢN CHÍNH.

    Đây là khâu định danh acc chính của sếp: bot nhận DM ``/start <token>``,
    InboundIngest consume token -> ghi account_links. Nhờ đó bot nhận diện được
    sếp khi sếp DM hoặc khi sếp xuất hiện trong nhóm.
    """
    provider = provider.lower().strip()
    async with db.acquire() as c:
        acc = await c.fetchrow(
            """
            SELECT ba.id, ba.provider_user_id, ba.display_name
            FROM bot_account_assignments baa
            JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE baa.boss_id=$1 AND baa.provider=$2 AND baa.status='active'
            """,
            ctx.boss_id,
            provider,
        )
    if acc is None:
        raise HTTPException(
            409,
            tr(ctx, vi="Chưa kết nối kênh này", en="Channel not connected"),
        )
    from src.services.linking_service import LinkingService

    token = await LinkingService(db).generate(ctx.boss_id, provider, acc["id"])
    return {
        "token": token,
        "bot_name": acc["display_name"] or acc["provider_user_id"],
    }


# ---------------------------------------------------------------------------
# Zalo: boss tự kết nối acc phụ qua QR
#   POST /channels/zalo/qr-login        → mở phiên login, trả login_id
#   GET  /channels/zalo/qr-login/{id}   → poll trạng thái + ảnh QR
# ---------------------------------------------------------------------------


async def _check_channel_slot(db, ctx, provider: str) -> None:
    """Chặn connect khi đã có kênh này hoặc vượt limit gói (dùng chung)."""
    from src.services.subscription import get_effective_limits

    async with db.acquire() as c:
        existing = await c.fetchval(
            """
            SELECT status FROM bot_account_assignments
            WHERE boss_id=$1 AND provider=$2 AND status IN ('active', 'pending_accept')
            """,
            ctx.boss_id,
            provider,
        )
        if existing:
            raise HTTPException(409, tr(ctx, vi="Kênh này đã được kết nối", en="This channel is already connected"))
        limits = await get_effective_limits(db, ctx.boss_id)
        if limits.max_active_channels is not None:
            active = await c.fetchval(
                """
                SELECT COUNT(*) FROM bot_account_assignments
                WHERE boss_id=$1 AND status='active' AND provider <> 'web'
                """,
                ctx.boss_id,
            )
            if active >= limits.max_active_channels:
                raise HTTPException(
                    400,
                    tr(
                        ctx,
                        vi=f"Đã đạt giới hạn {limits.max_active_channels} kênh của gói hiện tại",
                        en=f"Reached the {limits.max_active_channels}-channel limit of the current plan",
                    ),
                )


@router.post("/channels/zalo/qr-login", dependencies=[Depends(verify_json_csrf)])
async def zalo_qr_login_start(
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Mở phiên QR login để boss quét bằng acc Zalo phụ (acc nghe ngóng)."""
    await _check_channel_slot(db, ctx, "zalo")
    manager = getattr(request.app.state, "zalo_qr_login", None)
    if manager is None:
        raise HTTPException(503, tr(ctx, vi="Zalo QR login chưa sẵn sàng", en="Zalo QR login is not ready"))
    sess = await manager.start(ctx.boss_id)
    return {"login_id": sess.login_id, "status": sess.status}


@router.get("/channels/zalo/qr-login/{login_id}")
async def zalo_qr_login_status(
    login_id: str,
    request: Request,
    ctx: BossContext = Depends(require_boss),
) -> dict:
    manager = getattr(request.app.state, "zalo_qr_login", None)
    sess = manager.get(ctx.boss_id, login_id) if manager else None
    if sess is None:
        raise HTTPException(404, tr(ctx, vi="Phiên đăng nhập không tồn tại", en="Login session does not exist"))
    return {
        "status": sess.status,
        "qr_image_b64": sess.qr_image_b64 if sess.status == "qr" else None,
        "display_name": sess.display_name,
        "error": sess.error,
        "bot_account_id": sess.bot_account_id,
        "expires_in_s": sess.expires_in_s,
    }


@router.delete("/channels/{provider}", dependencies=[Depends(verify_json_csrf)])
async def disconnect_channel(
    provider: str,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Remove a bot account assignment (disconnect channel) by provider."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT boss_id FROM bot_account_assignments WHERE boss_id = $1 AND provider = $2",
            ctx.boss_id,
            provider,
        )
    if not row:
        raise HTTPException(404, "channel assignment not found")
    # boss_id check is implicit in the SELECT above

    async with db.acquire() as c:
        await c.execute(
            "DELETE FROM bot_account_assignments WHERE boss_id = $1 AND provider = $2",
            ctx.boss_id,
            provider,
        )
    return {"deleted": True, "provider": provider}


# ===========================================================================
# Workload / Hiệu suất  –  GET /api/v1/admin/workload?group_id=
# Tổng hợp khối lượng việc theo người TỪ SPINE (knowledge_items có assignee):
# open=active, done=resolved, overdue=active&due<now + completion_rate + overdue_items.
# ===========================================================================

@router.get("/workload")
async def get_workload(
    group_id: str | None = Query(None),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.repositories.knowledge import KnowledgeRepo

    repo = KnowledgeRepo(db, ctx)
    return await repo.workload_summary(chat_id=group_id or None)


# ===========================================================================
# Usage  –  GET /api/v1/admin/usage?range=30d
# ===========================================================================

@router.get("/usage")
async def get_usage(
    range: str = Query("30d", pattern=r"^\d+d$"),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return aggregated token usage for the boss over the requested time range."""
    try:
        days = int(range.rstrip("d"))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))

    async with db.acquire() as c:
        # Per-day breakdown — gap-fill đủ N ngày (ngày không dùng = 0) để chart
        # hiển thị trọn khoảng đã chọn.
        daily_rows = await c.fetch(
            """
            SELECT d::date AS day,
                   COALESCE(SUM(t.tokens_in), 0)::bigint            AS tokens_in,
                   COALESCE(SUM(t.tokens_out), 0)::bigint           AS tokens_out,
                   COALESCE(SUM(t.tokens_in + t.tokens_out), 0)::bigint AS tokens_total,
                   COUNT(t.id)::bigint                              AS messages,
                   COALESCE(SUM(t.cost_usd), 0.0)                   AS cost_usd
            FROM generate_series(
                   (NOW() AT TIME ZONE 'UTC')::date - ($2::int - 1),
                   (NOW() AT TIME ZONE 'UTC')::date,
                   INTERVAL '1 day'
                 ) d
            LEFT JOIN token_usage t
                   ON DATE(t.called_at AT TIME ZONE 'UTC') = d::date
                  AND t.boss_id = $1
            GROUP BY d
            ORDER BY d DESC
            """,
            ctx.boss_id,
            days,
        )

        # Summary totals
        totals = await c.fetchrow(
            """
            SELECT COALESCE(SUM(tokens_in), 0)::bigint            AS total_tokens_in,
                   COALESCE(SUM(tokens_out), 0)::bigint           AS total_tokens_out,
                   COALESCE(SUM(tokens_in + tokens_out), 0)::bigint AS total_tokens,
                   COALESCE(COUNT(*), 0)::bigint                  AS total_messages,
                   COALESCE(SUM(cost_usd), 0.0)::float            AS total_cost_usd
            FROM token_usage
            WHERE boss_id = $1
              AND called_at > NOW() - ($2 || ' days')::INTERVAL
            """,
            ctx.boss_id,
            str(days),
        )

        # Per-model breakdown — model nào tốn bao nhiêu (cost + tokens + calls).
        model_rows = await c.fetch(
            """
            SELECT provider, model,
                   SUM(tokens_in)  AS tokens_in,
                   SUM(tokens_out) AS tokens_out,
                   COUNT(*)        AS calls,
                   SUM(cost_usd)   AS cost_usd
            FROM token_usage
            WHERE boss_id = $1
              AND called_at > NOW() - ($2 || ' days')::INTERVAL
            GROUP BY provider, model
            ORDER BY cost_usd DESC NULLS LAST, calls DESC
            """,
            ctx.boss_id,
            str(days),
        )

    return {
        "range_days": days,
        "totals": {
            "tokens_in": totals["total_tokens_in"],
            "tokens_out": totals["total_tokens_out"],
            "tokens": totals["total_tokens"],
            "messages": totals["total_messages"],
            "cost_usd": float(totals["total_cost_usd"]),
        },
        "daily": [
            {
                "date": str(r["day"]),
                "tokens_in": int(r["tokens_in"] or 0),
                "tokens_out": int(r["tokens_out"] or 0),
                "tokens": int(r["tokens_total"] or 0),
                "messages": int(r["messages"] or 0),
                "cost_usd": float(r["cost_usd"] or 0),
            }
            for r in daily_rows
        ],
        "by_model": [
            {
                "provider": r["provider"],
                "model": r["model"],
                "tokens_in": int(r["tokens_in"] or 0),
                "tokens_out": int(r["tokens_out"] or 0),
                "calls": int(r["calls"] or 0),
                "cost_usd": float(r["cost_usd"] or 0),
            }
            for r in model_rows
        ],
    }


# ===========================================================================
# Subscription  –  GET /api/v1/admin/subscription
# ===========================================================================

@router.get("/subscription")
async def get_subscription(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return current boss's subscription / plan info (read-only)."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT email,
                   subscription_status,
                   subscription_plan,
                   subscription_expiry,
                   cost_cap_usd_daily
            FROM users
            WHERE id = $1
            """,
            ctx.boss_id,
        )
    if not row:
        raise HTTPException(404, "user not found")

    return {
        "billing_email": row["email"],
        "status": row["subscription_status"] or "free",
        "plan": row["subscription_plan"] or "free",
        "expires_at": row["subscription_expiry"].isoformat() if row["subscription_expiry"] else None,
        "cost_cap_usd_daily": float(row["cost_cap_usd_daily"] or 0),
        # Future fields (billing portal, last invoice) stubbed as null
        "last_invoice": None,
        "upgrade_url": None,
    }


# ===========================================================================
# Subscription — Plans & Requests
# ===========================================================================

from src.services.subscription import get_effective_limits, check_over_limit  # noqa: E402
from src.web.uploads import save_upload  # noqa: E402


@router.get("/subscription/plans")
async def list_plans(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, label, limits_json, prices_json FROM plans WHERE is_active=TRUE ORDER BY sort_order"
        )
    result = []
    for r in rows:
        # asyncpg trả JSONB dạng chuỗi (không đăng ký codec) — phải parse,
        # không thì frontend nhận string và mọi limit hiển thị "Không giới hạn".
        prices = r["prices_json"]
        if isinstance(prices, str):
            prices = json.loads(prices)
        limits = r["limits_json"]
        if isinstance(limits, str):
            limits = json.loads(limits)
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "label": r["label"],
                "limits": limits or {},
                "prices": prices or {},
            }
        )
    return result


@router.get("/subscription/limits")
async def get_limits(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    lim = await get_effective_limits(db, ctx.boss_id)
    over = await check_over_limit(db, ctx.boss_id)
    return {
        "max_active_groups": lim.max_active_groups,
        "max_active_tools": lim.max_active_tools,
        "max_active_channels": lim.max_active_channels,
        "mcp_slots": lim.mcp_slots,
        "cost_cap_usd_daily": lim.cost_cap_usd_daily,
        "over_limit": {
            "groups": over.groups,
            "tools": over.tools,
            "channels": over.channels,
            "mcp": over.mcp,
            "any_over": over.any_over,
        },
    }


@router.get("/subscription/requests")
async def list_subscription_requests(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT sr.id, sr.status, sr.note, sr.amount_paid_vnd, sr.transfer_content,
                   sr.billing_months,
                   sr.reviewer_note, sr.refund_requested, sr.created_at, sr.reviewed_at,
                   sr.cancelled_at,
                   p.name AS plan_name, p.label AS plan_label
            FROM subscription_requests sr
            JOIN plans p ON p.id = sr.plan_id
            WHERE sr.boss_id = $1
            ORDER BY sr.created_at DESC
            """,
            ctx.boss_id,
        )
    result = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("reviewed_at"):
            d["reviewed_at"] = d["reviewed_at"].isoformat()
        if d.get("cancelled_at"):
            d["cancelled_at"] = d["cancelled_at"].isoformat()
        result.append(d)
    return result


@router.post("/subscription/requests", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_subscription_request(
    plan_id: int = Form(...),
    note: str | None = Form(None),
    amount_paid_vnd: int | None = Form(None),
    transfer_content: str | None = Form(None),
    billing_months: int = Form(1),
    payment_proof: UploadFile = File(...),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    async with db.acquire() as c:
        plan = await c.fetchrow(
            "SELECT id, name, prices_json FROM plans WHERE id=$1 AND is_active=TRUE", plan_id
        )
        if not plan:
            raise HTTPException(404, "Plan not found")
        prices = plan["prices_json"]
        if isinstance(prices, str):
            prices = json.loads(prices)
        prices = prices or {}
        if prices and str(billing_months) not in prices:
            raise HTTPException(422, tr(ctx, vi="Gói không hỗ trợ chu kỳ thanh toán này", en="The plan does not support this billing cycle"))
        proof_path = await save_upload(payment_proof, "payment_proofs")
        try:
            row = await c.fetchrow(
                """
                INSERT INTO subscription_requests
                  (boss_id, plan_id, note, payment_proof_path, amount_paid_vnd,
                   transfer_content, billing_months)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, status
                """,
                ctx.boss_id,
                plan_id,
                note,
                proof_path,
                amount_paid_vnd,
                transfer_content,
                billing_months,
            )
        except Exception as e:
            if "uq_one_pending_per_boss" in str(e):
                raise HTTPException(409, "Already have a pending request")
            raise
    return {"id": row["id"], "status": row["status"], "plan_name": plan["name"]}


@router.post(
    "/subscription/requests/{req_id}/cancel",
    dependencies=[Depends(verify_json_csrf)],
)
async def cancel_subscription_request(
    req_id: int,
    cancel_reason: str | None = Form(None),
    refund_requested: bool = Form(False),
    refund_qr: UploadFile | None = File(None),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    qr_path = None
    if refund_requested and refund_qr and refund_qr.filename:
        qr_path = await save_upload(refund_qr, "refund_qr")
    async with db.acquire() as c:
        req = await c.fetchrow(
            "SELECT id, boss_id, status FROM subscription_requests WHERE id=$1",
            req_id,
        )
        if not req or req["boss_id"] != ctx.boss_id:
            raise HTTPException(404, "Request not found")
        if req["status"] != "pending":
            raise HTTPException(400, "Can only cancel pending requests")
        await c.execute(
            """
            UPDATE subscription_requests SET
              status='cancelled', cancel_reason=$2,
              refund_requested=$3, refund_qr_path=$4,
              cancelled_at=NOW()
            WHERE id=$1
            """,
            req_id,
            cancel_reason,
            refund_requested,
            qr_path,
        )
    return {"status": "cancelled", "refund_requested": refund_requested}


# ===========================================================================
# Tools — List & Toggle
# ===========================================================================

from src.tools import registry as _tool_registry  # noqa: E402


@router.get("/tools")
async def list_tools(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    """Công cụ LÕI (built-in): luôn bật cho mọi boss, không tắt được, không cap.
    Hiển thị read-only. Integration (MCP/plugin) là endpoint /integrations riêng."""
    return [
        {
            "name": name,
            "description": t.description,
            "core": True,
            "active": True,
            "can_disable": False,
        }
        for name, t in _tool_registry._REGISTRY.items()
    ]


@router.patch("/tools/{name}/toggle", dependencies=[Depends(verify_json_csrf)])
async def toggle_tool(
    name: str,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    if name not in _tool_registry._REGISTRY:
        raise HTTPException(404, "Tool not found")
    # Mọi tool trong _REGISTRY là tool lõi — luôn bật, không tắt được. Cap/bật-tắt
    # chỉ áp cho integration (xem /integrations).
    raise HTTPException(
        400,
        tr(
            ctx,
            vi="Công cụ lõi luôn bật, không thể tắt. Chỉ integration mới bật/tắt được.",
            en="Core tools are always on and cannot be disabled. Only integrations are toggleable.",
        ),
    )


# ===========================================================================
# Chat — sếp chat với bot ngay trong web admin (đi qua web channel)
#   GET  /api/v1/admin/chat/messages
#   POST /api/v1/admin/chat/send
#   GET  /api/v1/admin/chat/stream   (SSE)
# ===========================================================================


async def _boss_web_identity(db: asyncpg.Pool, ctx: BossContext) -> str:
    from src.services.web_identity import get_or_create_boss_web_identity

    return await get_or_create_boss_web_identity(db, ctx.boss_id)


async def _conversation_uid(
    db: asyncpg.Pool, ctx: BossContext, conversation_id: str | None
) -> str:
    """Resolve hội thoại: None → hội thoại mặc định (tự tạo nếu chưa có)."""
    if conversation_id is None:
        return await _boss_web_identity(db, ctx)
    async with db.acquire() as c:
        ok = await c.fetchval(
            "SELECT 1 FROM web_users WHERE id=$1 AND boss_user_id=$2 AND is_boss",
            conversation_id,
            ctx.boss_id,
        )
    if not ok:
        raise HTTPException(404, "Conversation not found")
    return conversation_id


@router.get("/chat/messages")
async def chat_messages(
    limit: int = Query(50, le=200),
    conversation_id: str | None = Query(None),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    uid = await _conversation_uid(db, ctx, conversation_id)
    chat_id = f"dm:{uid}"
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT * FROM (
              SELECT 'in'::text AS kind, m.id, m.sender_name, m.text, m.ts,
                     m.media_kind, m.media_url
              FROM messages m
              WHERE m.provider='web' AND m.chat_id=$1
              UNION ALL
              SELECT 'out'::text AS kind, o.id, 'Bot' AS sender_name, o.content AS text, o.sent_at AS ts,
                     'text' AS media_kind, NULL AS media_url
              FROM outbound_messages o
              WHERE o.provider='web' AND o.chat_id=$1
            ) merged
            ORDER BY ts DESC
            LIMIT $2
            """,
            chat_id,
            limit,
        )
    return [
        {
            "kind": r["kind"],
            "id": r["id"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "media_kind": r["media_kind"],
            "media_url": r["media_url"],
            "ts": r["ts"].isoformat(),
        }
        for r in reversed(rows)
    ]


@router.post("/chat/send", dependencies=[Depends(verify_json_csrf)])
async def chat_send(
    payload: dict,
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Lưu tin nhắn ngay (history thấy tức thì) rồi xếp agent run vào hàng đợi
    theo hội thoại — POST trả về ngay, không chờ agent; nhắn liên tục được
    xử lý tuần tự; hủy được qua /chat/cancel."""
    import uuid as _uuid
    from datetime import datetime, timezone

    from src.domain.message import NewMessage
    from src.repositories.messages import MessagesRepo

    text = (payload.get("text") or "").strip()
    attachment = payload.get("attachment") or None
    if not text and not attachment:
        raise HTTPException(400, "text or attachment required")
    uid = await _conversation_uid(db, ctx, payload.get("conversation_id"))
    async with db.acquire() as c:
        sender_name = await c.fetchval("SELECT name FROM web_users WHERE id=$1", uid)

    media_url = attachment.get("url") if attachment else None
    media_kind = attachment.get("kind") if attachment else None
    agent_text = text
    if attachment:
        # Cho LLM biết có đính kèm (xử lý sâu nội dung file thuộc media pipeline)
        label = attachment.get("name") or media_url
        agent_text = f"{text}\n[Attachment {media_kind}: {label}]".strip()

    chat_id = f"dm:{uid}"
    repo = MessagesRepo(db, BossContext(boss_id=ctx.boss_id, user_role="boss"))
    msg_id = await repo.insert(
        NewMessage(
            provider="web",
            chat_id=chat_id,
            chat_type="dm",
            provider_msg_id=f"adm-{_uuid.uuid4().hex[:10]}",
            sender_provider_id=uid,
            sender_name=sender_name,
            text=agent_text or None,
            media_kind=media_kind or "text",
            media_url=media_url,
            media_text=None,
            ts=datetime.now(tz=timezone.utc),
        )
    )
    if msg_id is None:
        return {"ok": True, "deduped": True}

    request.app.state.chat_runs.submit(
        f"web:{chat_id}",
        request.app.state.bus.publish(
            "message.captured",
            {
                "message_id": msg_id,
                "boss_id": ctx.boss_id,
                "provider": "web",
                "chat_id": chat_id,
                "chat_type": "dm",
                "mentions_bot": False,
                "sender_is_boss": True,
                "text": agent_text,
                "bot_account_id": None,
            },
        ),
    )
    return {"ok": True}


@router.post("/chat/cancel", dependencies=[Depends(verify_json_csrf)])
async def chat_cancel(
    payload: dict,
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Hủy các lượt agent đang chạy/đang chờ của hội thoại."""
    uid = await _conversation_uid(db, ctx, payload.get("conversation_id"))
    cancelled = request.app.state.chat_runs.cancel(f"web:dm:{uid}")
    return {"cancelled": cancelled}


@router.get("/chat/stream")
async def chat_stream(
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
):
    """SSE: đẩy event bot trả lời về cho admin chat (reuse sse_hub của web channel)."""
    import asyncio as _asyncio

    from fastapi.responses import StreamingResponse

    registry = getattr(request.app.state, "channel_registry", None)
    adapter = registry.get("web") if registry is not None else None
    if adapter is None:
        raise HTTPException(503, "web channel not loaded")

    uid = await _conversation_uid(
        db, ctx, request.query_params.get("conversation_id")
    )
    client = adapter.sse_hub.attach(uid)

    async def gen():
        try:
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await _asyncio.wait_for(client.queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n".encode()
                except _asyncio.TimeoutError:
                    yield b": heartbeat\n\n"
        finally:
            adapter.sse_hub.detach(client)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tools/enable-all", dependencies=[Depends(verify_json_csrf)])
async def enable_all_tools(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Core tools luôn bật toàn bộ (không cap). Endpoint giữ idempotent: đảm bảo
    mọi tool lõi có row hiển thị, không cắt theo limit."""
    from src.tools import registry as _reg

    names = list(_reg._REGISTRY.keys())
    async with db.acquire() as c:
        await c.executemany(
            """
            INSERT INTO boss_active_tools (boss_id, tool_name)
            VALUES ($1, $2) ON CONFLICT DO NOTHING
            """,
            [(ctx.boss_id, n) for n in names],
        )
    return {"enabled": len(names), "active": len(names), "total": len(names), "limit": None}


@router.patch("/groups/{group_id}/toggle-active", dependencies=[Depends(verify_json_csrf)])
async def toggle_group_active(
    group_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Bật/tắt nhóm — bật bị chặn khi vượt max_active_groups của gói."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, is_active FROM group_notes WHERE id=$1 AND boss_id=$2",
            group_id,
            ctx.boss_id,
        )
        if not row:
            raise HTTPException(404, "Group not found")

        if row["is_active"]:
            await c.execute(
                "UPDATE group_notes SET is_active=FALSE WHERE id=$1", group_id
            )
            return {"id": group_id, "is_active": False}

        lim = await get_effective_limits(db, ctx.boss_id)
        if lim.max_active_groups is not None:
            count = await c.fetchval(
                "SELECT COUNT(*) FROM group_notes WHERE boss_id=$1 AND is_active=TRUE",
                ctx.boss_id,
            )
            if count >= lim.max_active_groups:
                raise HTTPException(
                    400,
                    tr(
                        ctx,
                        vi=f"Đã đạt giới hạn {lim.max_active_groups} nhóm active của gói hiện tại",
                        en=f"Reached the {lim.max_active_groups}-active-group limit of the current plan",
                    ),
                )
        await c.execute(
            "UPDATE group_notes SET is_active=TRUE WHERE id=$1", group_id
        )
        return {"id": group_id, "is_active": True}


@router.post("/tools/disable-all", dependencies=[Depends(verify_json_csrf)])
async def disable_all_tools(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Công cụ lõi không tắt được → disable-all bị từ chối."""
    raise HTTPException(
        400,
        tr(
            ctx,
            vi="Công cụ lõi luôn bật, không thể tắt.",
            en="Core tools are always on and cannot be disabled.",
        ),
    )


@router.post("/groups/enable-all", dependencies=[Depends(verify_json_csrf)])
async def enable_all_groups(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Bật toàn bộ nhóm trong một lần bấm, cắt theo max_active_groups của gói."""
    lim = await get_effective_limits(db, ctx.boss_id)
    async with db.acquire() as c:
        total = await c.fetchval(
            "SELECT COUNT(*) FROM group_notes WHERE boss_id=$1", ctx.boss_id
        )
        active = await c.fetchval(
            "SELECT COUNT(*) FROM group_notes WHERE boss_id=$1 AND is_active=TRUE",
            ctx.boss_id,
        )
        slots = None
        if lim.max_active_groups is not None:
            slots = max(0, lim.max_active_groups - active)
        if slots is None:
            result = await c.execute(
                "UPDATE group_notes SET is_active=TRUE WHERE boss_id=$1 AND is_active=FALSE",
                ctx.boss_id,
            )
            enabled = int(result.split()[-1]) if result else 0
        elif slots > 0:
            # Bật các nhóm hoạt động gần nhất trước
            result = await c.execute(
                """
                UPDATE group_notes SET is_active=TRUE
                WHERE id IN (
                  SELECT id FROM group_notes
                  WHERE boss_id=$1 AND is_active=FALSE
                  ORDER BY updated_at DESC NULLS LAST
                  LIMIT $2
                )
                """,
                ctx.boss_id,
                slots,
            )
            enabled = int(result.split()[-1]) if result else 0
        else:
            enabled = 0
    return {
        "enabled": enabled,
        "active": active + enabled,
        "total": total,
        "limit": lim.max_active_groups,
    }


@router.post("/groups/disable-all", dependencies=[Depends(verify_json_csrf)])
async def disable_all_groups(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Tắt toàn bộ nhóm trong một lần bấm."""
    async with db.acquire() as c:
        result = await c.execute(
            "UPDATE group_notes SET is_active=FALSE WHERE boss_id=$1 AND is_active=TRUE",
            ctx.boss_id,
        )
    disabled = int(result.split()[-1]) if result else 0
    return {"disabled": disabled, "active": 0}


@router.get("/subscription/payment-info")
async def subscription_payment_info(
    plan_id: int = Query(...),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Thông tin chuyển khoản + nội dung gen sẵn để khách copy."""
    from src.config import settings

    async with db.acquire() as c:
        plan_name = await c.fetchval(
            "SELECT name FROM plans WHERE id=$1 AND is_active=TRUE", plan_id
        )
    if not plan_name:
        raise HTTPException(404, "Plan not found")
    return {
        "transfer_content": f"SMART {plan_name.upper()} U{ctx.boss_id}",
        "bank_account_number": settings.BANK_ACCOUNT_NUMBER or None,
        "bank_account_name": settings.BANK_ACCOUNT_NAME or None,
        "bank_bin": settings.BANK_BIN or None,
    }


# ===========================================================================
# Group note — lõi của nhóm: xem / sửa / refresh / versions / template
#   GET   /groups/:id/note
#   PATCH /groups/:id/note            {content}
#   POST  /groups/:id/note/refresh
#   GET   /groups/:id/note/versions
#   POST  /groups/:id/note/versions/:vid/restore
#   GET   /note-templates             (read-only cho boss chọn)
#   PATCH /groups/:id/template        {template_id}
# ===========================================================================


@router.get("/groups/{group_id}/note")
async def get_group_note(
    group_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT content, template_id, manually_edited_sections, updated_at
            FROM group_notes WHERE id=$1
            """,
            group_id,
        )
    edited = row["manually_edited_sections"]
    if isinstance(edited, str):
        edited = json.loads(edited)
    return {
        "content": row["content"],
        "template_id": row["template_id"],
        "manually_edited_sections": edited,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.patch("/groups/{group_id}/note", dependencies=[Depends(verify_json_csrf)])
async def edit_group_note_web(
    group_id: int,
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    content = payload.get("content")
    if content is None:
        raise HTTPException(400, "content required")
    await _require_group_owner(group_id, ctx, db)
    from src.repositories.group_notes import GroupNotesRepo

    repo = GroupNotesRepo(db, ctx)
    await repo.update_content(group_id, content, emitted_by="boss_web")
    return {"ok": True}


@router.post("/groups/{group_id}/note/refresh", dependencies=[Depends(verify_json_csrf)])
async def refresh_group_note_web(
    group_id: int,
    request: Request,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT provider, chat_id FROM group_notes WHERE id=$1", group_id
        )
    await request.app.state.bus.publish(
        "op.note_updater.fire",
        {
            "reason": "on_demand_web",
            "boss_id": ctx.boss_id,
            "source_event": {
                "boss_id": ctx.boss_id,
                "provider": row["provider"],
                "chat_id": row["chat_id"],
            },
        },
    )
    return {"ok": True, "message": "Bot is updating the note"}


@router.get("/groups/{group_id}/note/versions")
async def list_note_versions(
    group_id: int,
    limit: int = Query(20, le=100),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, emitted_by, emitted_at, LENGTH(content) AS content_len
            FROM group_note_versions
            WHERE group_note_id=$1
            ORDER BY id DESC LIMIT $2
            """,
            group_id,
            limit,
        )
    return [
        {
            "id": r["id"],
            "emitted_by": r["emitted_by"],
            "emitted_at": r["emitted_at"].isoformat(),
            "content_len": r["content_len"],
        }
        for r in rows
    ]


@router.post(
    "/groups/{group_id}/note/versions/{version_id}/restore",
    dependencies=[Depends(verify_json_csrf)],
)
async def restore_note_version(
    group_id: int,
    version_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        content = await c.fetchval(
            "SELECT content FROM group_note_versions WHERE id=$1 AND group_note_id=$2",
            version_id,
            group_id,
        )
    if content is None:
        raise HTTPException(404, "Version not found")
    from src.repositories.group_notes import GroupNotesRepo

    repo = GroupNotesRepo(db, ctx)
    await repo.update_content(group_id, content, emitted_by=f"restore_v{version_id}")
    return {"ok": True}


@router.get("/note-templates")
async def list_note_templates_admin(
    ctx: BossContext = Depends(require_boss),  # noqa: ARG001
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, description FROM note_templates ORDER BY name"
        )
    return [dict(r) for r in rows]


@router.patch("/groups/{group_id}/template", dependencies=[Depends(verify_json_csrf)])
async def set_group_template(
    group_id: int,
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    template_id = payload.get("template_id")
    async with db.acquire() as c:
        if template_id is not None:
            exists = await c.fetchval(
                "SELECT 1 FROM note_templates WHERE id=$1", template_id
            )
            if not exists:
                raise HTTPException(404, "Template not found")
        await c.execute(
            "UPDATE group_notes SET template_id=$2 WHERE id=$1", group_id, template_id
        )
    return {"ok": True, "template_id": template_id}


# ---------------------------------------------------------------------------
# Chat conversations — quản lý nhiều hội thoại với trợ lý
# ---------------------------------------------------------------------------


@router.get("/chat/conversations")
async def list_conversations(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    # Đảm bảo luôn có ít nhất 1 hội thoại
    await _boss_web_identity(db, ctx)
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT w.id, w.name, w.created_at,
                   (SELECT MAX(ts) FROM messages m
                    WHERE m.provider='web' AND m.chat_id='dm:'||w.id) AS last_message_at,
                   (SELECT text FROM messages m
                    WHERE m.provider='web' AND m.chat_id='dm:'||w.id
                    ORDER BY ts DESC LIMIT 1) AS last_message
            FROM web_users w
            WHERE w.boss_user_id=$1 AND w.is_boss
            ORDER BY COALESCE(
              (SELECT MAX(ts) FROM messages m
               WHERE m.provider='web' AND m.chat_id='dm:'||w.id),
              w.created_at) DESC
            """,
            ctx.boss_id,
        )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"].isoformat(),
            "last_message_at": r["last_message_at"].isoformat() if r["last_message_at"] else None,
            "last_message": (r["last_message"] or "")[:80] or None,
        }
        for r in rows
    ]


@router.post("/chat/conversations", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_conversation(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.channels.web.state_repo import WebUsersRepo

    name = (payload.get("name") or "").strip() or "New conversation"
    uid = await WebUsersRepo(db).create(
        name=name, is_boss=True, boss_user_id=ctx.boss_id
    )
    async with db.acquire() as c:
        await c.execute(
            """
            INSERT INTO account_links (boss_id, provider, provider_user_id)
            VALUES ($1, 'web', $2) ON CONFLICT DO NOTHING
            """,
            ctx.boss_id,
            uid,
        )
    return {"id": uid, "name": name}


@router.patch("/chat/conversations/{conversation_id}", dependencies=[Depends(verify_json_csrf)])
async def rename_conversation(
    conversation_id: str,
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    await _conversation_uid(db, ctx, conversation_id)
    async with db.acquire() as c:
        await c.execute(
            "UPDATE web_users SET name=$2 WHERE id=$1", conversation_id, name
        )
    return {"id": conversation_id, "name": name}


@router.delete("/chat/conversations/{conversation_id}", status_code=204, dependencies=[Depends(verify_json_csrf)])
async def delete_conversation(
    conversation_id: str,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    await _conversation_uid(db, ctx, conversation_id)
    chat_id = f"dm:{conversation_id}"
    async with db.acquire() as c:
        await c.execute(
            "DELETE FROM messages WHERE boss_id=$1 AND provider='web' AND chat_id=$2",
            ctx.boss_id,
            chat_id,
        )
        await c.execute(
            "DELETE FROM outbound_messages WHERE boss_id=$1 AND provider='web' AND chat_id=$2",
            ctx.boss_id,
            chat_id,
        )
        await c.execute(
            "DELETE FROM account_links WHERE provider='web' AND provider_user_id=$1",
            conversation_id,
        )
        await c.execute("DELETE FROM web_users WHERE id=$1", conversation_id)


@router.post("/chat/upload", dependencies=[Depends(verify_json_csrf)])
async def chat_upload(
    file: UploadFile = File(...),
    ctx: BossContext = Depends(require_boss),
) -> dict:
    from src.web.uploads import save_upload

    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf",
               ".docx", ".xlsx", ".csv", ".txt", ".md"}
    path = await save_upload(file, f"chat/{ctx.boss_id}", allowed=allowed)
    filename = path.rsplit("/", 1)[-1]
    ext = filename.rsplit(".", 1)[-1].lower()
    kind = "image" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "file"
    return {
        "url": f"/api/v1/admin/chat/files/{filename}",
        "name": file.filename or filename,
        "kind": kind,
    }


@router.get("/chat/files/{filename}")
async def chat_file(
    filename: str,
    ctx: BossContext = Depends(require_boss),
):
    from pathlib import Path as _Path

    from fastapi.responses import FileResponse

    safe = _Path(filename).name
    candidate = _Path("uploads") / "chat" / str(ctx.boss_id) / safe
    if not candidate.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(str(candidate))


# ===========================================================================
# Tích hợp — MCP servers (theo slot gói) + plugins nội bộ
# ===========================================================================


@router.get("/integrations")
async def list_integrations(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.plugins_loader import list_available_plugins
    from src.services.subscription import get_effective_limits

    lim = await get_effective_limits(db, ctx.boss_id)
    async with db.acquire() as c:
        catalog = await c.fetch(
            "SELECT id, name, description, icon_url FROM mcp_catalog WHERE is_active ORDER BY name"
        )
        servers = await c.fetch(
            """
            SELECT s.id, s.name, s.url, s.enabled, s.created_at, s.catalog_id
            FROM mcp_servers s WHERE s.boss_id=$1 ORDER BY s.created_at
            """,
            ctx.boss_id,
        )
        plug_rows = await c.fetch(
            "SELECT plugin_id, enabled FROM boss_integrations WHERE boss_id=$1",
            ctx.boss_id,
        )
    plug_state = {r["plugin_id"]: r["enabled"] for r in plug_rows}
    used = sum(1 for s in servers if s["enabled"])
    return {
        "mcp_slots": lim.mcp_slots,
        "mcp_used": used,
        "catalog": [dict(r) for r in catalog],
        "servers": [
            {**dict(r), "created_at": r["created_at"].isoformat()} for r in servers
        ],
        "plugins": [
            {
                "plugin_id": p["id"],
                "name": p.get("name") or p["id"],
                "description": p.get("description"),
                "enabled": plug_state.get(p["id"], False),
            }
            for p in list_available_plugins()
        ],
    }


@router.post("/mcp-servers", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def add_mcp_server(
    payload: dict,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.services.subscription import get_effective_limits

    catalog_id = payload.get("catalog_id")
    if not catalog_id:
        raise HTTPException(400, "catalog_id required")
    lim = await get_effective_limits(db, ctx.boss_id)
    async with db.acquire() as c:
        cat = await c.fetchrow(
            "SELECT name, url FROM mcp_catalog WHERE id=$1 AND is_active", catalog_id
        )
        if not cat:
            raise HTTPException(404, "Catalog item not found")
        if lim.mcp_slots is not None:
            used = await c.fetchval(
                "SELECT COUNT(*) FROM mcp_servers WHERE boss_id=$1 AND enabled", ctx.boss_id
            )
            if used >= lim.mcp_slots:
                raise HTTPException(
                    400, tr(
                        ctx,
                        vi=f"Đã đạt giới hạn {lim.mcp_slots} integration của gói hiện tại",
                        en=f"Reached the {lim.mcp_slots}-integration limit of the current plan",
                    )
                )
        dup = await c.fetchval(
            "SELECT 1 FROM mcp_servers WHERE boss_id=$1 AND catalog_id=$2",
            ctx.boss_id, catalog_id,
        )
        if dup:
            raise HTTPException(409, tr(ctx, vi="Integration này đã được thêm", en="This integration is already added"))
        sid = await c.fetchval(
            """
            INSERT INTO mcp_servers (boss_id, catalog_id, name, url, enabled)
            VALUES ($1, $2, $3, $4, TRUE) RETURNING id
            """,
            ctx.boss_id, catalog_id, cat["name"], cat["url"],
        )
    return {"id": sid, "name": cat["name"], "enabled": True}


@router.patch("/mcp-servers/{server_id}/toggle", dependencies=[Depends(verify_json_csrf)])
async def toggle_mcp_server(
    server_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.services.subscription import get_effective_limits

    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT enabled FROM mcp_servers WHERE id=$1 AND boss_id=$2",
            server_id, ctx.boss_id,
        )
        if not row:
            raise HTTPException(404, "Integration not found")
        if row["enabled"]:
            await c.execute(
                "UPDATE mcp_servers SET enabled=FALSE WHERE id=$1", server_id
            )
            return {"id": server_id, "enabled": False}
        lim = await get_effective_limits(db, ctx.boss_id)
        if lim.mcp_slots is not None:
            used = await c.fetchval(
                "SELECT COUNT(*) FROM mcp_servers WHERE boss_id=$1 AND enabled", ctx.boss_id
            )
            if used >= lim.mcp_slots:
                raise HTTPException(
                    400, tr(
                        ctx,
                        vi=f"Đã đạt giới hạn {lim.mcp_slots} integration của gói hiện tại",
                        en=f"Reached the {lim.mcp_slots}-integration limit of the current plan",
                    )
                )
        await c.execute("UPDATE mcp_servers SET enabled=TRUE WHERE id=$1", server_id)
        return {"id": server_id, "enabled": True}


@router.delete("/mcp-servers/{server_id}", status_code=204, dependencies=[Depends(verify_json_csrf)])
async def delete_mcp_server(
    server_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    async with db.acquire() as c:
        deleted = await c.fetchval(
            "DELETE FROM mcp_servers WHERE id=$1 AND boss_id=$2 RETURNING id",
            server_id, ctx.boss_id,
        )
    if not deleted:
        raise HTTPException(404, "Integration not found")


@router.patch("/integrations/plugins/{plugin_id}/toggle", dependencies=[Depends(verify_json_csrf)])
async def toggle_plugin(
    plugin_id: str,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.plugins_loader import list_available_plugins

    if plugin_id not in {p["id"] for p in list_available_plugins()}:
        raise HTTPException(404, "Plugin not found")
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT enabled FROM boss_integrations WHERE boss_id=$1 AND plugin_id=$2",
            ctx.boss_id, plugin_id,
        )
        new_state = not (row and row["enabled"])
        await c.execute(
            """
            INSERT INTO boss_integrations (boss_id, plugin_id, enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (boss_id, plugin_id) DO UPDATE SET enabled=EXCLUDED.enabled
            """,
            ctx.boss_id, plugin_id, new_state,
        )
    return {"plugin_id": plugin_id, "enabled": new_state}
