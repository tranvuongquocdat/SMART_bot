"""Admin (boss) API endpoints for /api/v1/admin/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from src.repositories.base import BossContext
from src.web.deps import get_db, require_boss
from src.web.security import verify_json_csrf

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
