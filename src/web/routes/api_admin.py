"""Admin (boss) API endpoints for /api/v1/admin/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.repositories.base import BossContext
from src.web.deps import get_db, require_boss
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
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
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


def _mask_keys(api_keys_enc: bytes | None) -> dict[str, dict]:
    """Decrypt api_keys_enc and return per-provider {present, last_4} map.
    Never returns raw keys. Returns empty dict on any decryption error.
    """
    from cryptography.fernet import Fernet
    from src.config import settings as cfg

    result: dict[str, dict] = {}
    if not api_keys_enc:
        return result
    try:
        f = Fernet(cfg.FERNET_KEY.encode())
        data: dict[str, str] = json.loads(f.decrypt(bytes(api_keys_enc)).decode())
    except Exception:
        return result
    for prov, key_val in data.items():
        last_4 = key_val[-4:] if len(key_val) >= 4 else ""
        result[prov] = {"present": True, "last_4": last_4}
    return result


@router.get("/settings/ai")
async def get_settings_ai(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return 3 model slots + masked API key info + available models list."""
    async with db.acquire() as c:
        boss = await c.fetchrow(
            """
            SELECT smart_model_id, fast_model_id, vision_model_id,
                   cost_cap_usd_daily, api_keys_enc
            FROM users WHERE id = $1
            """,
            ctx.boss_id,
        )
        models = await c.fetch(
            """
            SELECT id, name, provider, tier, capabilities,
                   cost_per_1m_input_usd, cost_per_1m_output_usd, is_platform_default
            FROM models
            WHERE is_active = TRUE
            ORDER BY tier, provider, name
            """
        )

    slots = [
        {
            "slot": "smart",
            "model_id": boss["smart_model_id"] if boss else None,
        },
        {
            "slot": "fast",
            "model_id": boss["fast_model_id"] if boss else None,
        },
        {
            "slot": "vision",
            "model_id": boss["vision_model_id"] if boss else None,
        },
    ]

    keys = _mask_keys(boss["api_keys_enc"] if boss else None)
    # Ensure all 3 standard providers appear (even if absent)
    for prov in ("openai", "groq", "gemini"):
        keys.setdefault(prov, {"present": False})

    models_list = [
        {
            "id": int(m["id"]),
            "name": m["name"],
            "provider": m["provider"],
            "tier": m["tier"],
            "capabilities": list(m["capabilities"]) if m["capabilities"] else [],
            "cost_per_1m_input_usd": float(m["cost_per_1m_input_usd"] or 0),
            "cost_per_1m_output_usd": float(m["cost_per_1m_output_usd"] or 0),
            "is_platform_default": bool(m["is_platform_default"]),
        }
        for m in models
    ]

    return {
        "slots": slots,
        "keys": keys,
        "models": models_list,
        "cost_cap_usd_daily": float(boss["cost_cap_usd_daily"] or 0) if boss else 0.0,
    }


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
    slot = payload.get("slot")
    model_id = payload.get("model_id")
    cap = payload.get("cost_cap_usd_daily")

    slot_col_map = {"smart": "smart_model_id", "fast": "fast_model_id", "vision": "vision_model_id"}

    if slot and slot in slot_col_map:
        col = slot_col_map[slot]
        async with db.acquire() as c:
            await c.execute(
                f"UPDATE users SET {col}=$2 WHERE id=$1",
                ctx.boss_id,
                int(model_id) if model_id is not None else None,
            )
        return {"updated": 1}

    if cap is not None:
        async with db.acquire() as c:
            await c.execute(
                "UPDATE users SET cost_cap_usd_daily=$2 WHERE id=$1",
                ctx.boss_id,
                float(cap),
            )
        return {"updated": 1}

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
    from cryptography.fernet import Fernet
    from src.config import settings as cfg

    provider = payload.get("provider", "").strip().lower()
    if provider not in ("openai", "groq", "gemini"):
        raise HTTPException(status_code=422, detail="unknown provider")

    async with db.acquire() as c:
        blob = await c.fetchval(
            "SELECT api_keys_enc FROM users WHERE id=$1", ctx.boss_id
        )

    f = Fernet(cfg.FERNET_KEY.encode())
    existing: dict[str, str] = {}
    if blob:
        try:
            existing = json.loads(f.decrypt(bytes(blob)).decode())
        except Exception:
            existing = {}

    if payload.get("clear"):
        existing.pop(provider, None)
    else:
        api_key = (payload.get("api_key") or "").strip()
        if not api_key:
            raise HTTPException(status_code=422, detail="api_key required")
        existing[provider] = api_key

    new_blob = f.encrypt(json.dumps(existing).encode())
    async with db.acquire() as c:
        await c.execute(
            "UPDATE users SET api_keys_enc=$2 WHERE id=$1",
            ctx.boss_id,
            new_blob,
        )

    return {"updated": 1}


# ---------------------------------------------------------------------------
# Settings: general  GET/PATCH /api/v1/admin/settings/general
# ---------------------------------------------------------------------------


@router.get("/settings/general")
async def get_settings_general(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return general/profile settings: name, tz, language."""
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, name, tz, language FROM users WHERE id=$1",
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
                       COALESCE(gn.group_name, gn.chat_id) AS name,
                       gn.provider                          AS channel,
                       gn.updated_at,
                       (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = gn.id) AS members_count
                FROM group_notes gn
                ORDER BY gn.updated_at DESC NULLS LAST
                """
            )
        else:
            rows = await c.fetch(
                """
                SELECT gn.id,
                       COALESCE(gn.group_name, gn.chat_id) AS name,
                       gn.provider                          AS channel,
                       gn.updated_at,
                       (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = gn.id) AS members_count
                FROM group_notes gn
                WHERE gn.boss_id = $1
                ORDER BY gn.updated_at DESC NULLS LAST
                """,
                ctx.boss_id,
            )
    return [
        {
            "id": int(r["id"]),
            "name": r["name"],
            "channel": r["channel"],
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
    """Update name, tz, language."""
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

    set_parts.append(f"updated_at=NOW()")
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
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),  # noqa: ARG001
) -> dict:
    """Kick off a channel connect flow. Currently stubbed — real OAuth/QR flows TBD."""
    # Real implementation will return {redirect_url} or {qr_url} depending on provider.
    # Frontend handles null redirect_url gracefully (shows "coming soon" toast).
    return {
        "provider": provider,
        "redirect_url": None,
        "qr_url": None,
        "message": "not_implemented",
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
        # Per-day breakdown for DataTable / chart
        daily_rows = await c.fetch(
            """
            SELECT DATE(called_at AT TIME ZONE 'UTC') AS day,
                   SUM(tokens_in)   AS tokens_in,
                   SUM(tokens_out)  AS tokens_out,
                   SUM(tokens_in + tokens_out) AS tokens_total,
                   COUNT(*)         AS messages,
                   SUM(cost_usd)    AS cost_usd
            FROM token_usage
            WHERE boss_id = $1
              AND called_at > NOW() - ($2 || ' days')::INTERVAL
            GROUP BY day
            ORDER BY day DESC
            """,
            ctx.boss_id,
            str(days),
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
