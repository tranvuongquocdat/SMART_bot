# Subscription Plans & Approval Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build end-to-end subscription plan management — boss picks plan, uploads payment proof, superadmin approves; limits enforced via active-item toggles with resolution flow on downgrade.

**Architecture:** Plans stored in `plans` table with `limits_json`. On approve, limits copied to `users`. Enforcement is two-way: block activation at N+1 (API + frontend), show resolution screen when already over-limit (plan change/expiry). Tools tracked in `boss_active_tools`; groups via `group_notes.is_active`. MCP tables created in migration but API deferred.

**Tech Stack:** Python/FastAPI/asyncpg, React/TanStack Query, Tailwind v4, Alembic migrations, pytest integration tests.

**Out of scope (deferred):** MCP catalog API, MCP server self-service API.

---

## File Map

**New backend:**
- `migrations/versions/0002_subscription_plans.py` — all new tables
- `src/services/subscription.py` — effective_limits(), check_over_limit(), approve/reject/cancel helpers
- `src/web/uploads.py` — file upload utility (payment proof, refund QR)

**Modified backend:**
- `src/web/routes/api_admin.py` — subscription request endpoints, tools toggle endpoints
- `src/web/routes/api_superadmin.py` — request management, plans CRUD
- `src/scheduler/jobs/subscription_check.py` — expired_grace degrade logic
- `src/tools/registry.py` — filter_for_op_and_boss()
- `src/agents/dm_responder.py` + `src/agents/in_group_responder.py` — pass boss active tools

**New frontend:**
- `frontend/src/modules/admin/features/subscription/plan-cards.tsx`
- `frontend/src/modules/admin/features/subscription/request-modal.tsx`
- `frontend/src/modules/admin/features/subscription/cancel-modal.tsx`
- `frontend/src/modules/admin/features/subscription/resolution-screen.tsx`
- `frontend/src/modules/admin/features/tools/page.tsx`
- `frontend/src/modules/admin/features/tools/api.ts`
- `frontend/src/modules/superadmin/features/subscriptions/page.tsx`
- `frontend/src/modules/superadmin/features/subscriptions/api.ts`
- `frontend/src/modules/superadmin/features/plans/page.tsx`
- `frontend/src/modules/superadmin/features/plans/api.ts`

**Modified frontend:**
- `frontend/src/modules/admin/features/subscription/page.tsx`
- `frontend/src/modules/admin/features/subscription/api.ts`
- `frontend/src/modules/admin/routes.tsx`
- `frontend/src/modules/admin/nav.ts`
- `frontend/src/modules/superadmin/routes.tsx`
- `frontend/src/modules/superadmin/nav.ts`

**New tests:**
- `tests/integration/test_api_subscription_plans.py`
- `tests/integration/test_api_tools_toggle.py`
- `tests/integration/test_subscription_service.py`

---

### Task 1: DB Migration

**Files:**
- Create: `migrations/versions/0002_subscription_plans.py`

- [ ] **Step 1: Create migration file**

```python
# migrations/versions/0002_subscription_plans.py
"""subscription plans, requests, mcp tables, boss_active_tools, group_notes.is_active"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE plans (
      id           SERIAL PRIMARY KEY,
      name         TEXT NOT NULL UNIQUE,
      label        TEXT NOT NULL,
      limits_json  JSONB NOT NULL DEFAULT '{}',
      is_active    BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order   INTEGER NOT NULL DEFAULT 0,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    INSERT INTO plans (name, label, limits_json, sort_order) VALUES
      ('trial',   'Trial',   '{"max_active_groups":2,"max_active_tools":5,"max_active_channels":1,"mcp_slots":0,"duration_days":14,"cost_cap_usd_daily":0.5}',   0),
      ('starter', 'Starter', '{"max_active_groups":5,"max_active_tools":10,"max_active_channels":1,"mcp_slots":0,"duration_days":30,"cost_cap_usd_daily":2.0}',  1),
      ('pro',     'Pro',     '{"max_active_groups":30,"max_active_tools":null,"max_active_channels":3,"mcp_slots":2,"duration_days":30,"cost_cap_usd_daily":5.0}', 2),
      ('custom',  'Custom',  '{"max_active_groups":null,"max_active_tools":null,"max_active_channels":null,"mcp_slots":null,"duration_days":null,"cost_cap_usd_daily":null}', 3)
    """)

    op.execute("""
    CREATE TABLE subscription_requests (
      id                  BIGSERIAL PRIMARY KEY,
      boss_id             BIGINT NOT NULL REFERENCES users(id),
      plan_id             INTEGER NOT NULL REFERENCES plans(id),
      status              TEXT NOT NULL DEFAULT 'pending',
      note                TEXT,
      payment_proof_path  TEXT,
      amount_paid_vnd     INTEGER,
      transfer_content    TEXT,
      reviewer_note       TEXT,
      reviewed_at         TIMESTAMPTZ,
      cancel_reason       TEXT,
      refund_requested    BOOLEAN NOT NULL DEFAULT FALSE,
      refund_qr_path      TEXT,
      cancelled_at        TIMESTAMPTZ,
      created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_one_pending_per_boss
      ON subscription_requests(boss_id)
      WHERE status = 'pending'
    """)

    op.execute("""
    CREATE TABLE boss_active_tools (
      boss_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      tool_name  TEXT NOT NULL,
      enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (boss_id, tool_name)
    )
    """)

    # Seed all existing bosses with all currently registered tools active
    op.execute("""
    INSERT INTO boss_active_tools (boss_id, tool_name)
    SELECT u.id, t.name
    FROM users u
    CROSS JOIN (VALUES
      ('search_history'),('count_messages'),('list_groups'),('list_reminders'),
      ('set_reminder'),('cancel_reminder'),('list_action_items'),('mark_action_item'),
      ('pin_message'),('find_exact_quote'),('remember'),('forget'),
      ('fetch_url'),('edit_group_note'),('read_group_note'),
      ('refresh_group_note'),('current_time')
    ) AS t(name)
    WHERE u.role = 'boss'
    ON CONFLICT DO NOTHING
    """)

    # MCP tables (API deferred)
    op.execute("""
    CREATE TABLE mcp_catalog (
      id                    SERIAL PRIMARY KEY,
      name                  TEXT NOT NULL,
      description           TEXT,
      url                   TEXT NOT NULL,
      config_template_json  JSONB NOT NULL DEFAULT '[]',
      icon_url              TEXT,
      is_active             BOOLEAN NOT NULL DEFAULT TRUE,
      created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE mcp_servers (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      catalog_id      INTEGER REFERENCES mcp_catalog(id),
      name            TEXT NOT NULL,
      url             TEXT NOT NULL,
      auth_json_enc   TEXT,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # group_notes: add is_active flag
    op.execute("ALTER TABLE group_notes ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")

    # users: plan FK + per-boss overrides
    op.execute("ALTER TABLE users ADD COLUMN plan_id INTEGER REFERENCES plans(id)")
    op.execute("ALTER TABLE users ADD COLUMN plan_overrides_json JSONB NOT NULL DEFAULT '{}'")

    # Set all existing bosses on trial plan
    op.execute("""
    UPDATE users SET plan_id = (SELECT id FROM plans WHERE name = 'trial')
    WHERE role = 'boss' AND plan_id IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_overrides_json")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_id")
    op.execute("ALTER TABLE group_notes DROP COLUMN IF EXISTS is_active")
    op.execute("DROP TABLE IF EXISTS mcp_servers")
    op.execute("DROP TABLE IF EXISTS mcp_catalog")
    op.execute("DROP TABLE IF EXISTS boss_active_tools")
    op.execute("DROP TABLE IF EXISTS subscription_requests")
    op.execute("DROP TABLE IF EXISTS plans")
```

- [ ] **Step 2: Run migration**

```bash
uv run alembic upgrade head
```

Expected: `Running upgrade 0001 -> 0002, subscription plans, requests, mcp tables...`

- [ ] **Step 3: Verify tables exist**

```bash
uv run python -c "
import asyncio, asyncpg
from src.config import settings
async def check():
    c = await asyncpg.connect(settings.POSTGRES_DSN)
    for t in ['plans','subscription_requests','boss_active_tools','mcp_catalog','mcp_servers']:
        n = await c.fetchval(f'SELECT COUNT(*) FROM {t}')
        print(f'{t}: {n} rows')
    await c.close()
asyncio.run(check())
"
```

Expected: `plans: 4 rows`, others 0 (boss_active_tools may have rows if bosses exist).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0002_subscription_plans.py
git commit -m "feat(db): subscription plans, requests, boss_active_tools, mcp tables"
```

---

### Task 2: Effective Limits Service

**Files:**
- Create: `src/services/subscription.py`
- Test: `tests/integration/test_subscription_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_subscription_service.py
"""Tests for effective_limits() and check_over_limit()."""
from __future__ import annotations
import asyncio
import pytest
from src.services.subscription import get_effective_limits, check_over_limit, EffectiveLimits


def _seed_plan(clean_db, name="starter", limits=None):
    if limits is None:
        limits = '{"max_active_groups":5,"max_active_tools":10,"max_active_channels":1,"mcp_slots":0,"duration_days":30,"cost_cap_usd_daily":2.0}'
    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "INSERT INTO plans (name,label,limits_json) VALUES ($1,$1,$2::jsonb) "
                "ON CONFLICT (name) DO UPDATE SET limits_json=$2::jsonb RETURNING id",
                name, limits
            )
    return asyncio.get_event_loop().run_until_complete(_())


def _set_boss_plan(clean_db, boss_id, plan_id, overrides="{}"):
    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                "UPDATE users SET plan_id=$2, plan_overrides_json=$3::jsonb WHERE id=$1",
                boss_id, plan_id, overrides
            )
    asyncio.get_event_loop().run_until_complete(_())


def test_effective_limits_from_plan(clean_db, logged_in_boss):
    plan_id = _seed_plan(clean_db, "starter")
    _set_boss_plan(clean_db, logged_in_boss.boss_id, plan_id)
    limits = asyncio.get_event_loop().run_until_complete(
        get_effective_limits(clean_db, logged_in_boss.boss_id)
    )
    assert limits.max_active_groups == 5
    assert limits.max_active_tools == 10
    assert limits.cost_cap_usd_daily == 2.0


def test_effective_limits_override_wins(clean_db, logged_in_boss):
    plan_id = _seed_plan(clean_db, "starter")
    _set_boss_plan(clean_db, logged_in_boss.boss_id, plan_id,
                   overrides='{"max_active_groups": 50}')
    limits = asyncio.get_event_loop().run_until_complete(
        get_effective_limits(clean_db, logged_in_boss.boss_id)
    )
    assert limits.max_active_groups == 50  # override
    assert limits.max_active_tools == 10   # from plan


def test_effective_limits_null_is_unlimited(clean_db, logged_in_boss):
    plan_id = _seed_plan(clean_db, "custom",
                         limits='{"max_active_groups":null,"max_active_tools":null}')
    _set_boss_plan(clean_db, logged_in_boss.boss_id, plan_id)
    limits = asyncio.get_event_loop().run_until_complete(
        get_effective_limits(clean_db, logged_in_boss.boss_id)
    )
    assert limits.max_active_groups is None
    assert limits.max_active_tools is None


def test_check_over_limit_not_over(clean_db, logged_in_boss):
    plan_id = _seed_plan(clean_db, "pro",
                         limits='{"max_active_groups":30,"max_active_tools":null,"max_active_channels":3,"mcp_slots":2}')
    _set_boss_plan(clean_db, logged_in_boss.boss_id, plan_id)
    over = asyncio.get_event_loop().run_until_complete(
        check_over_limit(clean_db, logged_in_boss.boss_id)
    )
    assert over.groups == 0
    assert over.tools == 0
    assert over.channels == 0
    assert over.mcp == 0
    assert not over.any_over
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/integration/test_subscription_service.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'get_effective_limits'`

- [ ] **Step 3: Implement service**

```python
# src/services/subscription.py
"""Subscription plan limits and over-limit detection."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class EffectiveLimits:
    max_active_groups: int | None
    max_active_tools: int | None
    max_active_channels: int | None
    mcp_slots: int | None
    cost_cap_usd_daily: float | None


@dataclass
class OverLimitItems:
    groups: int
    tools: int
    channels: int
    mcp: int

    @property
    def any_over(self) -> bool:
        return any([self.groups, self.tools, self.channels, self.mcp])


async def get_effective_limits(pool: Any, boss_id: int) -> EffectiveLimits:
    """Merge plan limits_json with per-boss plan_overrides_json."""
    async with pool.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT COALESCE(p.limits_json, '{}'::jsonb) AS plan_limits,
                   u.plan_overrides_json
            FROM users u
            LEFT JOIN plans p ON p.id = u.plan_id
            WHERE u.id = $1
            """,
            boss_id,
        )
    if not row:
        return EffectiveLimits(None, None, None, None, None)

    merged = {**dict(row["plan_limits"]), **dict(row["plan_overrides_json"])}

    def _int(key: str) -> int | None:
        v = merged.get(key)
        return int(v) if v is not None else None

    def _float(key: str) -> float | None:
        v = merged.get(key)
        return float(v) if v is not None else None

    return EffectiveLimits(
        max_active_groups=_int("max_active_groups"),
        max_active_tools=_int("max_active_tools"),
        max_active_channels=_int("max_active_channels"),
        mcp_slots=_int("mcp_slots"),
        cost_cap_usd_daily=_float("cost_cap_usd_daily"),
    )


async def check_over_limit(pool: Any, boss_id: int) -> OverLimitItems:
    """Return count of items exceeding effective limits in each category."""
    limits = await get_effective_limits(pool, boss_id)

    async with pool.acquire() as c:
        active_groups = await c.fetchval(
            "SELECT COUNT(*) FROM group_notes WHERE boss_id=$1 AND is_active=TRUE",
            boss_id,
        )
        active_tools = await c.fetchval(
            "SELECT COUNT(*) FROM boss_active_tools WHERE boss_id=$1",
            boss_id,
        )
        active_channels = await c.fetchval(
            """
            SELECT COUNT(*) FROM bot_account_assignments
            WHERE boss_id=$1 AND status='active'
            """,
            boss_id,
        )
        active_mcp = await c.fetchval(
            "SELECT COUNT(*) FROM mcp_servers WHERE boss_id=$1 AND enabled=TRUE",
            boss_id,
        )

    def _over(current: int, limit: int | None) -> int:
        if limit is None:
            return 0
        return max(0, current - limit)

    return OverLimitItems(
        groups=_over(active_groups, limits.max_active_groups),
        tools=_over(active_tools, limits.max_active_tools),
        channels=_over(active_channels, limits.max_active_channels),
        mcp=_over(active_mcp, limits.mcp_slots),
    )


async def apply_plan_to_user(
    pool: Any,
    boss_id: int,
    plan_id: int,
    overrides: dict,
) -> None:
    """Copy plan limits onto users row. Called on approve."""
    async with pool.acquire() as c:
        async with c.transaction():
            plan = await c.fetchrow("SELECT limits_json FROM plans WHERE id=$1", plan_id)
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")
            limits = {**dict(plan["limits_json"]), **overrides}

            import json
            from datetime import datetime, timedelta, timezone
            expiry = None
            if limits.get("duration_days") is not None:
                expiry = datetime.now(timezone.utc) + timedelta(days=int(limits["duration_days"]))

            await c.execute(
                """
                UPDATE users SET
                    plan_id              = $2,
                    plan_overrides_json  = $3::jsonb,
                    subscription_status  = 'active',
                    subscription_expiry  = $4,
                    cost_cap_usd_daily   = $5
                WHERE id = $1
                """,
                boss_id,
                plan_id,
                json.dumps({k: v for k, v in overrides.items()}),
                expiry,
                float(limits["cost_cap_usd_daily"]) if limits.get("cost_cap_usd_daily") is not None else 0.0,
            )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/integration/test_subscription_service.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/subscription.py tests/integration/test_subscription_service.py
git commit -m "feat(service): effective_limits, check_over_limit, apply_plan_to_user"
```

---

### Task 3: File Upload Utility

**Files:**
- Create: `src/web/uploads.py`

- [ ] **Step 1: Create upload utility**

```python
# src/web/uploads.py
"""Simple file upload helper used by subscription request endpoints."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

UPLOAD_ROOT = Path("uploads")
_ALLOWED = {".jpg", ".jpeg", ".png", ".pdf"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def save_upload(file: UploadFile, subfolder: str) -> str:
    """Save UploadFile to uploads/<subfolder>/<uuid><ext>. Returns relative path."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: jpg, png, pdf")
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")
    dest_dir = UPLOAD_ROOT / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    (dest_dir / filename).write_bytes(content)
    return str(dest_dir / filename)
```

- [ ] **Step 2: Commit**

```bash
git add src/web/uploads.py
git commit -m "feat(web): file upload utility for payment proofs"
```

---

### Task 4: Admin API — Subscription Plans & Requests

**Files:**
- Modify: `src/web/routes/api_admin.py`
- Test: `tests/integration/test_api_subscription_plans.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_api_subscription_plans.py
"""Tests for subscription plan listing and request flow."""
from __future__ import annotations
import asyncio, io
import pytest
from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-sub"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _seed_trial_plan(clean_db) -> int:
    async def _():
        async with clean_db.acquire() as c:
            return await c.fetchval(
                "SELECT id FROM plans WHERE name='trial'"
            )
    return asyncio.get_event_loop().run_until_complete(_())


# --- GET /api/v1/admin/subscription/plans ---

def test_list_plans_unauthenticated(client):
    r = client.get("/api/v1/admin/subscription/plans")
    assert r.status_code == 401


def test_list_plans_returns_active(client, logged_in_boss):
    r = client.get("/api/v1/admin/subscription/plans")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 4
    names = [p["name"] for p in body]
    assert "trial" in names and "pro" in names
    p = next(x for x in body if x["name"] == "trial")
    assert "label" in p and "limits" in p


# --- GET /api/v1/admin/subscription/limits ---

def test_get_limits_returns_effective(client, logged_in_boss):
    r = client.get("/api/v1/admin/subscription/limits")
    assert r.status_code == 200
    body = r.json()
    assert "max_active_groups" in body
    assert "max_active_tools" in body


# --- POST /api/v1/admin/subscription/requests ---

def test_create_request_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/subscription/requests", data={"plan_id": 1})
    assert r.status_code == 403


def test_create_request_happy_path(client, logged_in_boss, clean_db):
    plan_id = _seed_trial_plan(clean_db)
    # Get a non-trial plan
    async def _get_starter():
        async with clean_db.acquire() as c:
            return await c.fetchval("SELECT id FROM plans WHERE name='starter'")
    starter_id = asyncio.get_event_loop().run_until_complete(_get_starter())

    proof = io.BytesIO(b"fake image data")
    r = client.post(
        "/api/v1/admin/subscription/requests",
        data={
            "plan_id": starter_id,
            "note": "Muon nang cap",
            "amount_paid_vnd": 490000,
            "transfer_content": "SMART STARTER test",
        },
        files={"payment_proof": ("proof.jpg", proof, "image/jpeg")},
        headers=_csrf(client),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["plan_name"] == "starter"


def test_create_request_duplicate_pending(client, logged_in_boss, clean_db):
    async def _get_starter():
        async with clean_db.acquire() as c:
            return await c.fetchval("SELECT id FROM plans WHERE name='starter'")
    starter_id = asyncio.get_event_loop().run_until_complete(_get_starter())

    def _submit():
        proof = io.BytesIO(b"fake")
        return client.post(
            "/api/v1/admin/subscription/requests",
            data={"plan_id": starter_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
            files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
            headers=_csrf(client),
        )
    r1 = _submit()
    assert r1.status_code == 201
    r2 = _submit()
    assert r2.status_code == 409  # duplicate pending


# --- GET /api/v1/admin/subscription/requests ---

def test_list_requests_returns_history(client, logged_in_boss, clean_db):
    r = client.get("/api/v1/admin/subscription/requests")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# --- POST /api/v1/admin/subscription/requests/:id/cancel ---

def test_cancel_request_no_csrf(client, logged_in_boss):
    r = client.post("/api/v1/admin/subscription/requests/999/cancel", json={})
    assert r.status_code == 403


def test_cancel_request_with_refund(client, logged_in_boss, clean_db):
    async def _get_starter():
        async with clean_db.acquire() as c:
            return await c.fetchval("SELECT id FROM plans WHERE name='starter'")
    starter_id = asyncio.get_event_loop().run_until_complete(_get_starter())

    proof = io.BytesIO(b"fake")
    r_create = client.post(
        "/api/v1/admin/subscription/requests",
        data={"plan_id": starter_id, "amount_paid_vnd": 490000, "transfer_content": "X"},
        files={"payment_proof": ("p.jpg", proof, "image/jpeg")},
        headers=_csrf(client),
    )
    req_id = r_create.json()["id"]

    qr = io.BytesIO(b"qr image data")
    r_cancel = client.post(
        f"/api/v1/admin/subscription/requests/{req_id}/cancel",
        data={"cancel_reason": "doi y", "refund_requested": "true"},
        files={"refund_qr": ("qr.png", qr, "image/png")},
        headers=_csrf(client),
    )
    assert r_cancel.status_code == 200
    body = r_cancel.json()
    assert body["status"] == "cancelled"
    assert body["refund_requested"] is True
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/integration/test_api_subscription_plans.py -v 2>&1 | head -15
```

Expected: `404 Not Found` on plan endpoints.

- [ ] **Step 3: Add endpoints to api_admin.py**

Add after the existing subscription section (around line 1655 in `src/web/routes/api_admin.py`):

```python
# ---------------------------------------------------------------------------
# Subscription — Plans & Requests
# GET  /api/v1/admin/subscription/plans
# GET  /api/v1/admin/subscription/limits
# GET  /api/v1/admin/subscription/requests
# POST /api/v1/admin/subscription/requests       (multipart)
# POST /api/v1/admin/subscription/requests/:id/cancel  (multipart)
# ---------------------------------------------------------------------------

from fastapi import File, Form, UploadFile
from src.services.subscription import get_effective_limits, check_over_limit
from src.web.uploads import save_upload


@router.get("/subscription/plans")
async def list_plans(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, label, limits_json FROM plans WHERE is_active=TRUE ORDER BY sort_order"
        )
    return [
        {"id": r["id"], "name": r["name"], "label": r["label"], "limits": dict(r["limits_json"])}
        for r in rows
    ]


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
                   sr.reviewer_note, sr.refund_requested, sr.created_at, sr.reviewed_at,
                   sr.cancelled_at, p.name AS plan_name, p.label AS plan_label
            FROM subscription_requests sr
            JOIN plans p ON p.id = sr.plan_id
            WHERE sr.boss_id = $1
            ORDER BY sr.created_at DESC
            """,
            ctx.boss_id,
        )
    return [dict(r) for r in rows]


@router.post("/subscription/requests", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_subscription_request(
    plan_id: int = Form(...),
    note: str | None = Form(None),
    amount_paid_vnd: int | None = Form(None),
    transfer_content: str | None = Form(None),
    payment_proof: UploadFile = File(...),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    proof_path = await save_upload(payment_proof, "payment_proofs")
    async with db.acquire() as c:
        # Verify plan exists
        plan = await c.fetchrow("SELECT id, name FROM plans WHERE id=$1 AND is_active=TRUE", plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        try:
            row = await c.fetchrow(
                """
                INSERT INTO subscription_requests
                  (boss_id, plan_id, note, payment_proof_path, amount_paid_vnd, transfer_content)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, status
                """,
                ctx.boss_id, plan_id, note, proof_path, amount_paid_vnd, transfer_content,
            )
        except Exception as e:
            if "uq_one_pending_per_boss" in str(e):
                raise HTTPException(409, "Already have a pending request")
            raise
    return {"id": row["id"], "status": row["status"], "plan_name": plan["name"]}


@router.post("/subscription/requests/{req_id}/cancel", dependencies=[Depends(verify_json_csrf)])
async def cancel_subscription_request(
    req_id: int,
    cancel_reason: str | None = Form(None),
    refund_requested: bool = Form(False),
    refund_qr: UploadFile | None = File(None),
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    qr_path = None
    if refund_requested and refund_qr:
        qr_path = await save_upload(refund_qr, "refund_qr")
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, boss_id, status FROM subscription_requests WHERE id=$1",
            req_id,
        )
        if not row or row["boss_id"] != ctx.boss_id:
            raise HTTPException(404, "Request not found")
        if row["status"] != "pending":
            raise HTTPException(400, "Can only cancel pending requests")
        await c.execute(
            """
            UPDATE subscription_requests SET
              status='cancelled', cancel_reason=$2,
              refund_requested=$3, refund_qr_path=$4,
              cancelled_at=NOW()
            WHERE id=$1
            """,
            req_id, cancel_reason, refund_requested, qr_path,
        )
    return {"status": "cancelled", "refund_requested": refund_requested}
```

Note: `verify_json_csrf` applies to form/multipart too since CSRF token is sent as a header. Check existing multipart endpoints in the file — if they use a different dependency, match that pattern.

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/integration/test_api_subscription_plans.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/api_admin.py tests/integration/test_api_subscription_plans.py
git commit -m "feat(api): subscription plans list, request create/cancel with payment proof"
```

---

### Task 5: Admin API — Tools Toggle

**Files:**
- Modify: `src/web/routes/api_admin.py`
- Modify: `src/tools/registry.py`
- Test: `tests/integration/test_api_tools_toggle.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_api_tools_toggle.py
from __future__ import annotations
import asyncio
from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-tools"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_list_tools_unauthenticated(client):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 401


def test_list_tools_returns_registry(client, logged_in_boss):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
    tool = body[0]
    assert "name" in tool and "description" in tool and "active" in tool


def test_toggle_tool_no_csrf(client, logged_in_boss):
    r = client.patch("/api/v1/admin/tools/current_time/toggle")
    assert r.status_code == 403


def test_toggle_tool_deactivate(client, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/tools/current_time/toggle",
        headers=_csrf(client),
    )
    assert r.status_code == 200
    body = r.json()
    # First toggle: was active → now inactive
    assert "active" in body


def test_toggle_nonexistent_tool(client, logged_in_boss):
    r = client.patch(
        "/api/v1/admin/tools/nonexistent_tool_xyz/toggle",
        headers=_csrf(client),
    )
    assert r.status_code == 404


def test_toggle_respects_limit(client, logged_in_boss, clean_db):
    """Cannot activate more tools than max_active_tools allows."""
    import asyncio

    async def _set_limit():
        async with clean_db.acquire() as c:
            # Set plan with max 1 tool
            pid = await c.fetchval(
                "INSERT INTO plans (name,label,limits_json) VALUES ('tiny','Tiny','{ \"max_active_tools\": 1 }'::jsonb) "
                "ON CONFLICT(name) DO UPDATE SET limits_json=EXCLUDED.limits_json RETURNING id"
            )
            # Delete all active tools for this boss
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1", logged_in_boss.boss_id
            )
            # Add exactly 1 active tool
            await c.execute(
                "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, 'current_time')",
                logged_in_boss.boss_id,
            )
            await c.execute(
                "UPDATE users SET plan_id=$2 WHERE id=$1",
                logged_in_boss.boss_id, pid,
            )

    asyncio.get_event_loop().run_until_complete(_set_limit())

    # Trying to activate a second tool should fail
    r = client.patch(
        "/api/v1/admin/tools/set_reminder/toggle",
        headers=_csrf(client),
    )
    assert r.status_code == 400
    assert "limit" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
uv run pytest tests/integration/test_api_tools_toggle.py -v 2>&1 | head -10
```

Expected: `404` on `/api/v1/admin/tools`.

- [ ] **Step 3: Add tools endpoints to api_admin.py**

```python
# Add to src/web/routes/api_admin.py (after tools section or near subscription)

# ---------------------------------------------------------------------------
# Tools management
# GET   /api/v1/admin/tools
# PATCH /api/v1/admin/tools/:name/toggle
# ---------------------------------------------------------------------------

@router.get("/tools")
async def list_tools(
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    from src.tools import registry as tool_registry
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT tool_name FROM boss_active_tools WHERE boss_id=$1", ctx.boss_id
        )
    active_names = {r["tool_name"] for r in rows}
    return [
        {
            "name": name,
            "description": t.description,
            "active": name in active_names,
        }
        for name, t in tool_registry._REGISTRY.items()
    ]


@router.patch("/tools/{name}/toggle", dependencies=[Depends(verify_json_csrf)])
async def toggle_tool(
    name: str,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    from src.tools import registry as tool_registry
    from src.services.subscription import get_effective_limits

    if name not in tool_registry._REGISTRY:
        raise HTTPException(404, "Tool not found")

    async with db.acquire() as c:
        exists = await c.fetchval(
            "SELECT 1 FROM boss_active_tools WHERE boss_id=$1 AND tool_name=$2",
            ctx.boss_id, name,
        )
        if exists:
            await c.execute(
                "DELETE FROM boss_active_tools WHERE boss_id=$1 AND tool_name=$2",
                ctx.boss_id, name,
            )
            return {"name": name, "active": False}
        else:
            limits = await get_effective_limits(db, ctx.boss_id)
            if limits.max_active_tools is not None:
                count = await c.fetchval(
                    "SELECT COUNT(*) FROM boss_active_tools WHERE boss_id=$1", ctx.boss_id
                )
                if count >= limits.max_active_tools:
                    raise HTTPException(
                        400,
                        f"Limit reached: max {limits.max_active_tools} active tools on your plan",
                    )
            await c.execute(
                "INSERT INTO boss_active_tools (boss_id, tool_name) VALUES ($1, $2)",
                ctx.boss_id, name,
            )
            return {"name": name, "active": True}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/integration/test_api_tools_toggle.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/api_admin.py tests/integration/test_api_tools_toggle.py
git commit -m "feat(api): tools list and toggle with limit enforcement"
```

---

### Task 6: Agent — Filter Active Tools Per Boss

**Files:**
- Modify: `src/tools/registry.py`
- Modify: `src/agents/dm_responder.py`
- Modify: `src/agents/in_group_responder.py`

- [ ] **Step 1: Add boss-aware filter to registry**

In `src/tools/registry.py`, add after `filter_for_op`:

```python
def filter_for_op_and_boss(
    op_name: str,
    allowed: set[str],
    boss_active: set[str],
) -> list[ToolDef]:
    """Like filter_for_op but also intersects with boss_active tool names."""
    return [
        t
        for n, t in _REGISTRY.items()
        if n in allowed
        and (not t.available_to or op_name in t.available_to)
        and n in boss_active
    ]
```

- [ ] **Step 2: Load boss active tools in agents**

Find where each agent builds its tool list. In `src/agents/dm_responder.py`, locate the call to `filter_for_op` or similar. Add active-tool loading before the call:

```python
# Before building tool list, load boss active tools from DB
async with pool.acquire() as c:
    rows = await c.fetch(
        "SELECT tool_name FROM boss_active_tools WHERE boss_id=$1", boss_id
    )
boss_active = {r["tool_name"] for r in rows}

# Replace filter_for_op(...) with:
tools = filter_for_op_and_boss(op_name, allowed_tools, boss_active)
```

Apply the same pattern in `src/agents/in_group_responder.py`.

- [ ] **Step 3: Run existing agent tests to confirm no regression**

```bash
uv run pytest tests/integration/test_dm_responder.py tests/integration/test_in_group_responder.py -v 2>&1 | tail -10
```

Expected: all pass (boss_active_tools seeded in migration for existing bosses).

- [ ] **Step 4: Commit**

```bash
git add src/tools/registry.py src/agents/dm_responder.py src/agents/in_group_responder.py
git commit -m "feat(agent): filter tools by boss active tool set"
```

---

### Task 7: Superadmin API — Request Management

**Files:**
- Modify: `src/web/routes/api_superadmin.py`

- [ ] **Step 1: Write failing tests** — add to `tests/integration/test_api_subscription_plans.py`:

```python
# Append to test_api_subscription_plans.py

def _seed_pending_request(clean_db, boss_id) -> int:
    async def _():
        async with clean_db.acquire() as c:
            starter_id = await c.fetchval("SELECT id FROM plans WHERE name='starter'")
            return await c.fetchval(
                """
                INSERT INTO subscription_requests
                  (boss_id, plan_id, amount_paid_vnd, transfer_content, payment_proof_path)
                VALUES ($1, $2, 490000, 'SMART TEST', 'uploads/payment_proofs/test.jpg')
                RETURNING id
                """,
                boss_id, starter_id,
            )
    return asyncio.get_event_loop().run_until_complete(_())


def test_superadmin_list_requests(superadmin_client, logged_in_boss, clean_db):
    _seed_pending_request(clean_db, logged_in_boss.boss_id)
    r = superadmin_client.get("/api/v1/superadmin/subscription-requests?status=pending")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["status"] == "pending"


def test_superadmin_approve_request(superadmin_client, logged_in_boss, clean_db):
    req_id = _seed_pending_request(clean_db, logged_in_boss.boss_id)
    r = superadmin_client.post(
        f"/api/v1/superadmin/subscription-requests/{req_id}/approve",
        json={"overrides": {}},
        headers=_csrf(superadmin_client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    # Verify user plan updated
    async def _check():
        async with clean_db.acquire() as c:
            return await c.fetchrow(
                "SELECT subscription_status, plan_id FROM users WHERE id=$1",
                logged_in_boss.boss_id,
            )
    row = asyncio.get_event_loop().run_until_complete(_check())
    assert row["subscription_status"] == "active"
    assert row["plan_id"] is not None


def test_superadmin_reject_request(superadmin_client, logged_in_boss, clean_db):
    req_id = _seed_pending_request(clean_db, logged_in_boss.boss_id)
    r = superadmin_client.post(
        f"/api/v1/superadmin/subscription-requests/{req_id}/reject",
        json={"reviewer_note": "Khong hop le"},
        headers=_csrf(superadmin_client),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
```

Note: `superadmin_client` fixture may not exist yet. Check `tests/conftest.py`. If missing, add:

```python
# In tests/conftest.py or tests/fixtures/
@pytest.fixture
def superadmin_client(client, clean_db):
    """Return client logged in as superadmin."""
    # Look at existing test_api_superadmin.py for how superadmin login is done
    # and replicate the pattern here
    ...
```

Check `tests/integration/test_api_superadmin.py` for the existing superadmin login pattern and use the same fixture.

- [ ] **Step 2: Add superadmin endpoints to api_superadmin.py**

```python
# Add to src/web/routes/api_superadmin.py

# ---------------------------------------------------------------------------
# Subscription requests management
# GET  /api/v1/superadmin/subscription-requests
# GET  /api/v1/superadmin/subscription-requests/:id
# POST /api/v1/superadmin/subscription-requests/:id/approve
# POST /api/v1/superadmin/subscription-requests/:id/reject
# GET  /api/v1/superadmin/payment-proof/:filename
# ---------------------------------------------------------------------------

from src.services.subscription import apply_plan_to_user


@router.get("/subscription-requests")
async def list_subscription_requests(
    status: str | None = Query(None),  # pending, approved, rejected, cancelled
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        query = """
            SELECT sr.id, sr.status, sr.note, sr.amount_paid_vnd, sr.transfer_content,
                   sr.reviewer_note, sr.refund_requested, sr.refund_qr_path,
                   sr.created_at, sr.reviewed_at, sr.cancelled_at,
                   p.name AS plan_name, p.label AS plan_label,
                   u.email AS boss_email, u.name AS boss_name,
                   cp.name AS current_plan_name
            FROM subscription_requests sr
            JOIN plans p ON p.id = sr.plan_id
            JOIN users u ON u.id = sr.boss_id
            LEFT JOIN plans cp ON cp.id = u.plan_id
            {where}
            ORDER BY sr.created_at DESC
        """
        if status:
            rows = await c.fetch(query.format(where="WHERE sr.status=$1"), status)
        else:
            rows = await c.fetch(query.format(where=""))
    return [dict(r) for r in rows]


@router.get("/subscription-requests/{req_id}")
async def get_subscription_request(
    req_id: int,
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT sr.*, p.name AS plan_name, p.label AS plan_label,
                   p.limits_json AS plan_limits,
                   u.email AS boss_email, u.name AS boss_name,
                   u.subscription_status AS current_status,
                   cp.name AS current_plan_name
            FROM subscription_requests sr
            JOIN plans p ON p.id = sr.plan_id
            JOIN users u ON u.id = sr.boss_id
            LEFT JOIN plans cp ON cp.id = u.plan_id
            WHERE sr.id = $1
            """,
            req_id,
        )
    if not row:
        raise HTTPException(404, "Request not found")
    return dict(row)


@router.post("/subscription-requests/{req_id}/approve", dependencies=[Depends(verify_json_csrf)])
async def approve_subscription_request(
    req_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> dict:
    overrides = payload.get("overrides", {})
    async with db.acquire() as c:
        req = await c.fetchrow(
            "SELECT boss_id, plan_id, status FROM subscription_requests WHERE id=$1",
            req_id,
        )
    if not req:
        raise HTTPException(404, "Request not found")
    if req["status"] != "pending":
        raise HTTPException(400, "Request is not pending")

    await apply_plan_to_user(db, req["boss_id"], req["plan_id"], overrides)

    async with db.acquire() as c:
        await c.execute(
            "UPDATE subscription_requests SET status='approved', reviewed_at=NOW() WHERE id=$1",
            req_id,
        )
    return {"status": "approved", "request_id": req_id}


@router.post("/subscription-requests/{req_id}/reject", dependencies=[Depends(verify_json_csrf)])
async def reject_subscription_request(
    req_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> dict:
    async with db.acquire() as c:
        req = await c.fetchrow(
            "SELECT status FROM subscription_requests WHERE id=$1", req_id
        )
        if not req or req["status"] != "pending":
            raise HTTPException(400, "Request not pending or not found")
        await c.execute(
            "UPDATE subscription_requests SET status='rejected', reviewed_at=NOW(), reviewer_note=$2 WHERE id=$1",
            req_id, payload.get("reviewer_note", ""),
        )
    return {"status": "rejected", "request_id": req_id}


@router.get("/payment-proof/{filename}")
async def get_payment_proof(
    filename: str,
    _: None = Depends(require_superadmin),
):
    from fastapi.responses import FileResponse
    from pathlib import Path
    # Strip path traversal
    safe_name = Path(filename).name
    path = Path("uploads") / safe_name
    # Also check subdirs
    for subdir in ["payment_proofs", "refund_qr"]:
        candidate = Path("uploads") / subdir / safe_name
        if candidate.exists():
            return FileResponse(str(candidate))
    raise HTTPException(404, "File not found")
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/integration/test_api_subscription_plans.py -v -k "superadmin"
```

- [ ] **Step 4: Commit**

```bash
git add src/web/routes/api_superadmin.py
git commit -m "feat(api): superadmin subscription request management — list, approve, reject"
```

---

### Task 8: Superadmin API — Plans CRUD

**Files:**
- Modify: `src/web/routes/api_superadmin.py`

- [ ] **Step 1: Add plans CRUD endpoints**

```python
# Add to src/web/routes/api_superadmin.py

# ---------------------------------------------------------------------------
# Plans CRUD
# GET   /api/v1/superadmin/plans
# POST  /api/v1/superadmin/plans
# PATCH /api/v1/superadmin/plans/:id
# ---------------------------------------------------------------------------

import json as _json


@router.get("/plans")
async def list_plans_superadmin(
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            "SELECT id, name, label, limits_json, is_active, sort_order FROM plans ORDER BY sort_order"
        )
    return [dict(r) for r in rows]


@router.post("/plans", status_code=201, dependencies=[Depends(verify_json_csrf)])
async def create_plan(
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> dict:
    required = {"name", "label", "limits_json"}
    if not required.issubset(payload):
        raise HTTPException(400, f"Required fields: {required}")
    async with db.acquire() as c:
        try:
            row = await c.fetchrow(
                """
                INSERT INTO plans (name, label, limits_json, sort_order)
                VALUES ($1, $2, $3::jsonb, COALESCE($4, 99))
                RETURNING id, name
                """,
                payload["name"],
                payload["label"],
                _json.dumps(payload["limits_json"]),
                payload.get("sort_order"),
            )
        except Exception as e:
            if "unique" in str(e).lower():
                raise HTTPException(409, "Plan name already exists")
            raise
    return {"id": row["id"], "name": row["name"]}


@router.patch("/plans/{plan_id}", dependencies=[Depends(verify_json_csrf)])
async def update_plan(
    plan_id: int,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: None = Depends(require_superadmin),
) -> dict:
    allowed = {"label", "limits_json", "is_active", "sort_order"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    async with db.acquire() as c:
        # If disabling a plan, verify no users on it
        if updates.get("is_active") is False:
            count = await c.fetchval(
                "SELECT COUNT(*) FROM users WHERE plan_id=$1", plan_id
            )
            if count > 0:
                raise HTTPException(
                    400, f"Cannot deactivate plan: {count} users are on it"
                )
        sets = []
        vals = [plan_id]
        for i, (k, v) in enumerate(updates.items(), start=2):
            if k == "limits_json":
                sets.append(f"limits_json=${i}::jsonb")
                vals.append(_json.dumps(v))
            else:
                sets.append(f"{k}=${i}")
                vals.append(v)
        sets.append("updated_at=NOW()")
        await c.execute(
            f"UPDATE plans SET {', '.join(sets)} WHERE id=$1",
            *vals,
        )
    return {"updated": 1}
```

- [ ] **Step 2: Run all superadmin tests to check no regression**

```bash
uv run pytest tests/integration/test_api_superadmin.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
git add src/web/routes/api_superadmin.py
git commit -m "feat(api): superadmin plans CRUD"
```

---

### Task 9: Scheduler — expired_grace Degrade

**Files:**
- Modify: `src/scheduler/jobs/subscription_check.py`

- [ ] **Step 1: Update job**

```python
# src/scheduler/jobs/subscription_check.py
"""subscription_check job — flip statuses past expiry + degrade expired_grace to trial limits."""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)


async def job(app_state: Any) -> None:
    async with app_state.db_pool.acquire() as c:
        # active → expired_grace once expiry passes
        await c.execute(
            """
            UPDATE users SET subscription_status='expired_grace'
            WHERE subscription_status='active'
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < NOW()
            """
        )
        # expired_grace → expired after 30-day grace window
        await c.execute(
            """
            UPDATE users SET subscription_status='expired'
            WHERE subscription_status='expired_grace'
              AND subscription_expiry IS NOT NULL
              AND subscription_expiry < NOW() - INTERVAL '30 days'
            """
        )
        # Degrade expired_grace users: apply trial limits
        trial = await c.fetchrow("SELECT limits_json FROM plans WHERE name='trial'")
        if trial:
            import json
            from datetime import datetime, timezone
            limits = dict(trial["limits_json"])
            await c.execute(
                """
                UPDATE users SET
                    plan_id = (SELECT id FROM plans WHERE name='trial'),
                    plan_overrides_json = '{}'::jsonb,
                    cost_cap_usd_daily = $1
                WHERE subscription_status = 'expired_grace'
                  AND plan_id != (SELECT id FROM plans WHERE name='trial')
                """,
                float(limits.get("cost_cap_usd_daily") or 0),
            )
            log.info("subscription_check: degraded expired_grace users to trial limits")
```

- [ ] **Step 2: Run scheduler tests**

```bash
uv run pytest tests/integration/test_scheduler_jobs.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Commit**

```bash
git add src/scheduler/jobs/subscription_check.py
git commit -m "feat(scheduler): degrade expired_grace users to trial limits"
```

---

### Task 10: Build Frontend

Run `bash scripts/build_frontend.sh` before starting this task to confirm clean build baseline.

---

### Task 11: Frontend Admin — Subscription Page (Plan Cards + Request Modal)

**Files:**
- Modify: `frontend/src/modules/admin/features/subscription/api.ts`
- Create: `frontend/src/modules/admin/features/subscription/plan-cards.tsx`
- Create: `frontend/src/modules/admin/features/subscription/request-modal.tsx`
- Modify: `frontend/src/modules/admin/features/subscription/page.tsx`

- [ ] **Step 1: Extend API types**

```typescript
// frontend/src/modules/admin/features/subscription/api.ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type SubscriptionData = {
  billing_email: string;
  status: string;
  plan: string;
  expires_at: string | null;
  cost_cap_usd_daily: number;
  last_invoice: null;
  upgrade_url: string | null;
};

export type Plan = {
  id: number;
  name: string;
  label: string;
  limits: {
    max_active_groups: number | null;
    max_active_tools: number | null;
    max_active_channels: number | null;
    mcp_slots: number | null;
    duration_days: number | null;
    cost_cap_usd_daily: number | null;
  };
};

export type SubscriptionRequest = {
  id: number;
  status: string;
  plan_name: string;
  plan_label: string;
  note: string | null;
  amount_paid_vnd: number | null;
  reviewer_note: string | null;
  refund_requested: boolean;
  created_at: string;
  reviewed_at: string | null;
  cancelled_at: string | null;
};

export type EffectiveLimits = {
  max_active_groups: number | null;
  max_active_tools: number | null;
  max_active_channels: number | null;
  mcp_slots: number | null;
  cost_cap_usd_daily: number | null;
  over_limit: {
    groups: number;
    tools: number;
    channels: number;
    mcp: number;
    any_over: boolean;
  };
};

export const subscriptionQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription'],
    queryFn: () => api<SubscriptionData>('/api/v1/admin/subscription'),
  });

export const plansQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'plans'],
    queryFn: () => api<Plan[]>('/api/v1/admin/subscription/plans'),
  });

export const requestsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'requests'],
    queryFn: () => api<SubscriptionRequest[]>('/api/v1/admin/subscription/requests'),
  });

export const limitsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'limits'],
    queryFn: () => api<EffectiveLimits>('/api/v1/admin/subscription/limits'),
  });
```

- [ ] **Step 2: Create PlanCards component**

```tsx
// frontend/src/modules/admin/features/subscription/plan-cards.tsx
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Plan, SubscriptionData } from './api';

function fmt(v: number | null) { return v === null ? '∞' : String(v); }

export function PlanCards({
  plans,
  current,
  hasPending,
  onSelect,
}: {
  plans: Plan[];
  current: SubscriptionData;
  hasPending: boolean;
  onSelect: (plan: Plan) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {plans.map((plan) => {
        const isCurrent = plan.name === current.plan;
        const disabled = isCurrent || hasPending;
        return (
          <div
            key={plan.id}
            className={`rounded-xl border p-4 flex flex-col gap-3 ${
              isCurrent ? 'border-primary bg-primary/5' : 'border-border bg-card'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{plan.label}</span>
              {isCurrent && <Badge variant="outline">Đang dùng</Badge>}
            </div>
            <ul className="text-xs text-muted-foreground space-y-0.5">
              <li>{fmt(plan.limits.max_active_groups)} nhóm</li>
              <li>{fmt(plan.limits.max_active_tools)} tools</li>
              <li>{fmt(plan.limits.mcp_slots)} integrations</li>
              {plan.limits.duration_days && (
                <li>{plan.limits.duration_days} ngày</li>
              )}
            </ul>
            <Button
              size="sm"
              variant={isCurrent ? 'outline' : 'default'}
              disabled={disabled}
              onClick={() => onSelect(plan)}
              className="mt-auto"
            >
              {isCurrent ? 'Đang dùng' : hasPending ? 'Chờ duyệt...' : 'Đăng ký'}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Create RequestModal component**

```tsx
// frontend/src/modules/admin/features/subscription/request-modal.tsx
import { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api';
import type { Plan } from './api';

function readCsrf() {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export function RequestModal({
  plan,
  open,
  onClose,
}: {
  plan: Plan | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');
  const [amount, setAmount] = useState('');
  const [content, setContent] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const mut = useMutation({
    mutationFn: async () => {
      if (!plan) return;
      const fd = new FormData();
      fd.append('plan_id', String(plan.id));
      fd.append('amount_paid_vnd', amount);
      fd.append('transfer_content', content);
      if (note) fd.append('note', note);
      const file = fileRef.current?.files?.[0];
      if (file) fd.append('payment_proof', file);
      const res = await fetch('/api/v1/admin/subscription/requests', {
        method: 'POST',
        headers: { 'X-CSRF-Token': readCsrf() },
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Gửi yêu cầu thất bại');
      }
      return res.json();
    },
    onSuccess: () => {
      toast.success('Đã gửi yêu cầu đăng ký');
      qc.invalidateQueries({ queryKey: ['admin', 'subscription'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Đăng ký gói {plan?.label}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Số tiền chuyển khoản (VND)</Label>
            <Input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="490000"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Nội dung chuyển khoản</Label>
            <Input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="SMART PRO ten_cua_ban"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Minh chứng chuyển khoản</Label>
            <Input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.pdf" />
          </div>
          <div className="space-y-1.5">
            <Label>Ghi chú (tuỳ chọn)</Label>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !amount || !content}>
            {mut.isPending ? 'Đang gửi...' : 'Gửi yêu cầu'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Update subscription page**

```tsx
// frontend/src/modules/admin/features/subscription/page.tsx
import { useState } from 'react';
import { useSuspenseQuery, useQuery } from '@tanstack/react-query';
import { CreditCard, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { StatusDot } from '@/components/status-dot';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { subscriptionQuery, plansQuery, requestsQuery } from './api';
import { PlanCards } from './plan-cards';
import { RequestModal } from './request-modal';
import type { Plan } from './api';

function planDot(status: string): 'ok' | 'warn' | 'err' | 'idle' {
  if (status === 'active') return 'ok';
  if (status === 'trial') return 'warn';
  if (status === 'expired' || status === 'canceled') return 'err';
  return 'idle';
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Đang chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  cancelled: 'Đã huỷ',
};

export default function SubscriptionPage() {
  const { data: sub } = useSuspenseQuery(subscriptionQuery());
  const { data: plans = [] } = useQuery(plansQuery());
  const { data: requests = [] } = useQuery(requestsQuery());
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);

  const hasPending = requests.some((r) => r.status === 'pending');
  const pendingRequest = requests.find((r) => r.status === 'pending');

  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader title="Gói cước" subtitle="Quản lý gói dịch vụ và giới hạn sử dụng." />

      {/* Current plan */}
      <PageSection className="rounded-[12px] bg-card-grad surface-section overflow-hidden">
        <div className="flex items-center gap-3 p-4 border-b border-border">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-semibold capitalize">{sub.plan}</p>
            <p className="text-xs text-muted-foreground">{sub.billing_email}</p>
          </div>
          <div className="ml-auto">
            <StatusDot status={planDot(sub.status)} label={sub.status} />
          </div>
        </div>
        <div className="px-4 py-3 text-sm text-muted-foreground">
          {sub.expires_at
            ? `Hết hạn: ${new Date(sub.expires_at).toLocaleDateString('vi-VN')}`
            : 'Không giới hạn thời gian'}
        </div>
      </PageSection>

      {/* Pending banner */}
      {hasPending && pendingRequest && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm flex items-center gap-2">
          <Clock className="h-4 w-4 text-yellow-500 shrink-0" />
          <span>Yêu cầu đăng ký gói <strong>{pendingRequest.plan_label}</strong> đang chờ duyệt.</span>
        </div>
      )}

      {/* Plan cards */}
      {plans.length > 0 && (
        <PageSection>
          <h2 className="text-sm font-semibold mb-3">Nâng cấp gói</h2>
          <PlanCards
            plans={plans}
            current={sub}
            hasPending={hasPending}
            onSelect={setSelectedPlan}
          />
        </PageSection>
      )}

      {/* Request history */}
      {requests.length > 0 && (
        <PageSection>
          <h2 className="text-sm font-semibold mb-3">Lịch sử yêu cầu</h2>
          <div className="divide-y divide-border rounded-lg border">
            {requests.map((req) => (
              <div key={req.id} className="flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <span className="font-medium">{req.plan_label}</span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {new Date(req.created_at).toLocaleDateString('vi-VN')}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={req.status === 'approved' ? 'default' : 'secondary'}>
                    {STATUS_LABELS[req.status] ?? req.status}
                  </Badge>
                  {req.reviewer_note && (
                    <span className="text-xs text-muted-foreground">{req.reviewer_note}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </PageSection>
      )}

      <RequestModal
        plan={selectedPlan}
        open={!!selectedPlan}
        onClose={() => setSelectedPlan(null)}
      />
    </PageWrap>
  );
}
```

- [ ] **Step 5: Build and verify**

```bash
bash scripts/build_frontend.sh 2>&1 | tail -5
```

Expected: `✓ built in ...ms`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/admin/features/subscription/
git commit -m "feat(ui): subscription page — plan cards, request modal, history"
```

---

### Task 12: Frontend Admin — Resolution Screen

**Files:**
- Create: `frontend/src/modules/admin/features/subscription/resolution-screen.tsx`
- Modify: `frontend/src/modules/admin/features/subscription/page.tsx` (add screen trigger)

- [ ] **Step 1: Create resolution screen**

```tsx
// frontend/src/modules/admin/features/subscription/resolution-screen.tsx
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { EffectiveLimits } from './api';

export function ResolutionScreen({
  limits,
  onGoToUpgrade,
}: {
  limits: EffectiveLimits;
  onGoToUpgrade: () => void;
}) {
  const { over_limit } = limits;
  const items = [
    { label: 'nhóm', count: over_limit.groups },
    { label: 'tools', count: over_limit.tools },
    { label: 'kênh', count: over_limit.channels },
    { label: 'integrations', count: over_limit.mcp },
  ].filter((i) => i.count > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 backdrop-blur">
      <div className="max-w-md w-full rounded-2xl border border-border bg-card p-8 shadow-xl space-y-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-6 w-6 text-yellow-500 shrink-0 mt-0.5" />
          <div>
            <h2 className="font-semibold text-lg">Gói đã thay đổi</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Số lượng tính năng đang bật vượt quá giới hạn gói mới. Vui lòng tắt bớt hoặc nâng cấp gói để tiếp tục.
            </p>
          </div>
        </div>

        <ul className="rounded-lg border border-border divide-y text-sm">
          {items.map((item) => (
            <li key={item.label} className="flex justify-between px-4 py-2.5">
              <span className="text-muted-foreground capitalize">{item.label}</span>
              <span className="text-destructive font-medium">vượt {item.count}</span>
            </li>
          ))}
        </ul>

        <div className="text-xs text-muted-foreground">
          Vào trang quản lý tương ứng (Nhóm / Tools / Kênh) để tắt bớt, hoặc đăng ký gói cao hơn.
        </div>

        <Button className="w-full" onClick={onGoToUpgrade}>
          Nâng cấp gói
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire into subscription page**

In `frontend/src/modules/admin/features/subscription/page.tsx`, add limits query and conditional render:

```tsx
// Add at top of SubscriptionPage():
const { data: limits } = useQuery(limitsQuery());

// Add before closing </PageWrap>:
{limits?.over_limit.any_over && (
  <ResolutionScreen
    limits={limits}
    onGoToUpgrade={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
  />
)}
```

Also add import: `import { ResolutionScreen } from './resolution-screen';` and `import { limitsQuery } from './api';`

- [ ] **Step 3: Build and verify**

```bash
bash scripts/build_frontend.sh 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/modules/admin/features/subscription/
git commit -m "feat(ui): subscription resolution screen for over-limit state"
```

---

### Task 13: Frontend Admin — Tools Page

**Files:**
- Create: `frontend/src/modules/admin/features/tools/api.ts`
- Create: `frontend/src/modules/admin/features/tools/page.tsx`
- Modify: `frontend/src/modules/admin/routes.tsx`
- Modify: `frontend/src/modules/admin/nav.ts`

- [ ] **Step 1: Create tools API**

```typescript
// frontend/src/modules/admin/features/tools/api.ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Tool = { name: string; description: string; active: boolean };

export const toolsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'tools'],
    queryFn: () => api<Tool[]>('/api/v1/admin/tools'),
  });

export async function toggleTool(name: string): Promise<{ active: boolean }> {
  const csrf = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/)?.[1] ?? '';
  const res = await fetch(`/api/v1/admin/tools/${name}/toggle`, {
    method: 'PATCH',
    headers: { 'X-CSRF-Token': decodeURIComponent(csrf) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Không thể thay đổi tool');
  }
  return res.json();
}
```

- [ ] **Step 2: Create tools page**

```tsx
// frontend/src/modules/admin/features/tools/page.tsx
import { useSuspenseQuery, useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Switch } from '@/components/ui/switch';
import { toolsQuery, toggleTool } from './api';
import { limitsQuery } from '../subscription/api';

export default function ToolsPage() {
  const qc = useQueryClient();
  const { data: tools } = useSuspenseQuery(toolsQuery());
  const { data: limits } = useQuery(limitsQuery());

  const activeCount = tools.filter((t) => t.active).length;
  const maxTools = limits?.max_active_tools ?? null;

  const mut = useMutation({
    mutationFn: toggleTool,
    onSuccess: (data, name) => {
      qc.invalidateQueries({ queryKey: ['admin', 'tools'] });
      toast.success(data.active ? `Đã bật tool "${name}"` : `Đã tắt tool "${name}"`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title="Công cụ"
        subtitle={
          maxTools !== null
            ? `${activeCount}/${maxTools} tools đang bật`
            : `${activeCount} tools đang bật`
        }
      />
      <PageSection>
        <div className="divide-y divide-border rounded-xl border">
          {tools.map((tool) => {
            const atLimit = !tool.active && maxTools !== null && activeCount >= maxTools;
            return (
              <div key={tool.name} className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0 mr-4">
                  <p className="text-sm font-medium">{tool.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{tool.description}</p>
                  {atLimit && (
                    <p className="text-xs text-yellow-500 mt-0.5">
                      Đã đạt giới hạn — nâng cấp gói để bật thêm
                    </p>
                  )}
                </div>
                <Switch
                  checked={tool.active}
                  disabled={mut.isPending || atLimit}
                  onCheckedChange={() => mut.mutate(tool.name)}
                />
              </div>
            );
          })}
        </div>
      </PageSection>
    </PageWrap>
  );
}
```

- [ ] **Step 3: Wire routes and nav**

In `frontend/src/modules/admin/routes.tsx`, add:
```tsx
{ path: 'tools', lazy: async () => ({ Component: (await import('./features/tools/page')).default }), handle: { breadcrumb: 'Tools' } },
```

In `frontend/src/modules/admin/nav.ts`, add tools nav item (import `Wrench` from lucide-react):
```ts
{ label: 'Công cụ', href: '/app/admin/tools', icon: Wrench },
```

- [ ] **Step 4: Build and verify**

```bash
bash scripts/build_frontend.sh 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/admin/features/tools/ frontend/src/modules/admin/routes.tsx frontend/src/modules/admin/nav.ts
git commit -m "feat(ui): admin tools page with toggle and limit enforcement"
```

---

### Task 14: Frontend Superadmin — Subscriptions Page

**Files:**
- Create: `frontend/src/modules/superadmin/features/subscriptions/api.ts`
- Create: `frontend/src/modules/superadmin/features/subscriptions/page.tsx`
- Modify: `frontend/src/modules/superadmin/routes.tsx`
- Modify: `frontend/src/modules/superadmin/nav.ts`

- [ ] **Step 1: Create superadmin subscriptions API**

```typescript
// frontend/src/modules/superadmin/features/subscriptions/api.ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type AdminRequest = {
  id: number;
  status: string;
  plan_name: string;
  plan_label: string;
  plan_limits: Record<string, unknown>;
  boss_email: string;
  boss_name: string | null;
  current_plan_name: string | null;
  current_status: string;
  note: string | null;
  amount_paid_vnd: number | null;
  transfer_content: string | null;
  payment_proof_path: string | null;
  reviewer_note: string | null;
  refund_requested: boolean;
  refund_qr_path: string | null;
  created_at: string;
  reviewed_at: string | null;
};

export const requestsQuery = (status?: string) =>
  queryOptions({
    queryKey: ['superadmin', 'subscription-requests', status],
    queryFn: () =>
      api<AdminRequest[]>(
        `/api/v1/superadmin/subscription-requests${status ? `?status=${status}` : ''}`
      ),
  });

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function approveRequest(id: number, overrides: Record<string, unknown>) {
  const res = await fetch(`/api/v1/superadmin/subscription-requests/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
    body: JSON.stringify({ overrides }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function rejectRequest(id: number, reviewer_note: string) {
  const res = await fetch(`/api/v1/superadmin/subscription-requests/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
    body: JSON.stringify({ reviewer_note }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}
```

- [ ] **Step 2: Create subscriptions page**

```tsx
// frontend/src/modules/superadmin/features/subscriptions/page.tsx
import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet';
import { requestsQuery, approveRequest, rejectRequest, type AdminRequest } from './api';

function StatusBadge({ status }: { status: string }) {
  const v = status === 'pending' ? 'destructive'
    : status === 'approved' ? 'default' : 'secondary';
  return <Badge variant={v}>{status}</Badge>;
}

function RequestDetail({
  req, onClose,
}: { req: AdminRequest; onClose: () => void }) {
  const qc = useQueryClient();
  const [rejectNote, setRejectNote] = useState('');
  const [overrides, setOverrides] = useState('{}');

  const approveMut = useMutation({
    mutationFn: () => {
      let parsed: Record<string, unknown> = {};
      try { parsed = JSON.parse(overrides); } catch {}
      return approveRequest(req.id, parsed);
    },
    onSuccess: () => {
      toast.success('Đã duyệt');
      qc.invalidateQueries({ queryKey: ['superadmin', 'subscription-requests'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rejectMut = useMutation({
    mutationFn: () => rejectRequest(req.id, rejectNote),
    onSuccess: () => {
      toast.success('Đã từ chối');
      qc.invalidateQueries({ queryKey: ['superadmin', 'subscription-requests'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const proofFilename = req.payment_proof_path?.split('/').pop();

  return (
    <div className="space-y-4 text-sm">
      <div className="rounded-lg border p-3 space-y-1.5">
        <p><span className="text-muted-foreground">Boss:</span> {req.boss_email}</p>
        <p><span className="text-muted-foreground">Gói hiện tại:</span> {req.current_plan_name ?? '—'} ({req.current_status})</p>
        <p><span className="text-muted-foreground">Gói yêu cầu:</span> {req.plan_label}</p>
        {req.amount_paid_vnd && (
          <p><span className="text-muted-foreground">Số tiền:</span> {req.amount_paid_vnd.toLocaleString('vi-VN')}đ</p>
        )}
        {req.transfer_content && (
          <p><span className="text-muted-foreground">Nội dung CK:</span> {req.transfer_content}</p>
        )}
        {req.note && <p><span className="text-muted-foreground">Ghi chú:</span> {req.note}</p>}
      </div>

      {proofFilename && (
        <div>
          <Label className="mb-1 block">Minh chứng</Label>
          <a
            href={`/api/v1/superadmin/payment-proof/${proofFilename}`}
            target="_blank"
            rel="noreferrer"
            className="text-primary underline text-xs"
          >
            Xem ảnh minh chứng ↗
          </a>
        </div>
      )}

      {req.refund_requested && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3">
          <p className="font-medium text-yellow-600">Yêu cầu hoàn tiền</p>
          {req.refund_qr_path && (
            <a
              href={`/api/v1/superadmin/payment-proof/${req.refund_qr_path.split('/').pop()}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline text-xs"
            >
              Xem QR hoàn tiền ↗
            </a>
          )}
        </div>
      )}

      {req.status === 'pending' && (
        <>
          <div className="space-y-1.5">
            <Label>Override limits (JSON, tuỳ chọn)</Label>
            <Textarea
              value={overrides}
              onChange={(e) => setOverrides(e.target.value)}
              rows={3}
              className="font-mono text-xs"
              placeholder='{"max_active_groups": 50}'
            />
          </div>
          <div className="space-y-1.5">
            <Label>Lý do từ chối (nếu từ chối)</Label>
            <Input value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => rejectMut.mutate()}
              disabled={rejectMut.isPending || !rejectNote}
              className="flex-1"
            >
              Từ chối
            </Button>
            <Button
              onClick={() => approveMut.mutate()}
              disabled={approveMut.isPending}
              className="flex-1"
            >
              Duyệt ✓
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export default function SubscriptionsPage() {
  const [filter, setFilter] = useState<string | undefined>('pending');
  const [selected, setSelected] = useState<AdminRequest | null>(null);
  const { data: requests } = useSuspenseQuery(requestsQuery(filter));

  const pending = requests.filter((r) => r.status === 'pending').length;

  return (
    <PageWrap className="max-w-[960px]">
      <PageHeader
        title="Yêu cầu nâng gói"
        subtitle={pending > 0 ? `${pending} đang chờ duyệt` : 'Không có yêu cầu mới'}
      />

      <div className="flex gap-2 mb-4">
        {['pending', 'approved', 'rejected', 'cancelled', undefined].map((s) => (
          <button
            key={String(s)}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
              filter === s ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-muted'
            }`}
          >
            {s ?? 'Tất cả'}
          </button>
        ))}
      </div>

      <PageSection>
        <div className="divide-y divide-border rounded-xl border">
          {requests.length === 0 && (
            <p className="text-sm text-muted-foreground p-4">Không có yêu cầu nào.</p>
          )}
          {requests.map((req) => (
            <div
              key={req.id}
              className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/40"
              onClick={() => setSelected(req)}
            >
              <div>
                <p className="text-sm font-medium">{req.boss_email}</p>
                <p className="text-xs text-muted-foreground">
                  {req.current_plan_name} → {req.plan_label} ·{' '}
                  {new Date(req.created_at).toLocaleDateString('vi-VN')}
                </p>
              </div>
              <StatusBadge status={req.status} />
            </div>
          ))}
        </div>
      </PageSection>

      <Sheet open={!!selected} onOpenChange={(v) => !v && setSelected(null)}>
        <SheetContent className="w-[420px] sm:w-[480px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Chi tiết yêu cầu #{selected?.id}</SheetTitle>
          </SheetHeader>
          {selected && (
            <div className="mt-4">
              <RequestDetail req={selected} onClose={() => setSelected(null)} />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </PageWrap>
  );
}
```

- [ ] **Step 3: Wire routes and nav**

In `frontend/src/modules/superadmin/routes.tsx`, add:
```tsx
{ path: 'subscriptions', lazy: async () => ({ Component: (await import('./features/subscriptions/page')).default }), handle: { breadcrumb: 'Subscriptions' } },
```

In `frontend/src/modules/superadmin/nav.ts`, add (import `CreditCard` from lucide-react):
```ts
{ label: 'Subscriptions', href: '/app/superadmin/subscriptions', icon: CreditCard },
```

- [ ] **Step 4: Build and verify**

```bash
bash scripts/build_frontend.sh 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/superadmin/features/subscriptions/ frontend/src/modules/superadmin/routes.tsx frontend/src/modules/superadmin/nav.ts
git commit -m "feat(ui): superadmin subscriptions management page"
```

---

### Task 15: Frontend Superadmin — Plans Management

**Files:**
- Create: `frontend/src/modules/superadmin/features/plans/api.ts`
- Create: `frontend/src/modules/superadmin/features/plans/page.tsx`
- Modify: `frontend/src/modules/superadmin/routes.tsx`
- Modify: `frontend/src/modules/superadmin/nav.ts`

- [ ] **Step 1: Create plans API**

```typescript
// frontend/src/modules/superadmin/features/plans/api.ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type AdminPlan = {
  id: number;
  name: string;
  label: string;
  limits_json: Record<string, number | null>;
  is_active: boolean;
  sort_order: number;
};

export const adminPlansQuery = () =>
  queryOptions({
    queryKey: ['superadmin', 'plans'],
    queryFn: () => api<AdminPlan[]>('/api/v1/superadmin/plans'),
  });

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function updatePlan(id: number, payload: Partial<AdminPlan>) {
  const res = await fetch(`/api/v1/superadmin/plans/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}
```

- [ ] **Step 2: Create plans page**

```tsx
// frontend/src/modules/superadmin/features/plans/page.tsx
import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { adminPlansQuery, updatePlan, type AdminPlan } from './api';

const LIMIT_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'max_active_groups', label: 'Nhóm tối đa' },
  { key: 'max_active_tools', label: 'Tools tối đa' },
  { key: 'max_active_channels', label: 'Kênh tối đa' },
  { key: 'mcp_slots', label: 'MCP slots' },
  { key: 'duration_days', label: 'Số ngày' },
  { key: 'cost_cap_usd_daily', label: 'Cost cap USD/ngày' },
];

function PlanEditSheet({ plan, onClose }: { plan: AdminPlan; onClose: () => void }) {
  const qc = useQueryClient();
  const [label, setLabel] = useState(plan.label);
  const [limits, setLimits] = useState<Record<string, string>>(
    Object.fromEntries(
      LIMIT_FIELDS.map((f) => [f.key, plan.limits_json[f.key] == null ? '' : String(plan.limits_json[f.key])])
    )
  );

  const mut = useMutation({
    mutationFn: () => {
      const parsed: Record<string, number | null> = {};
      for (const f of LIMIT_FIELDS) {
        const v = limits[f.key].trim();
        parsed[f.key] = v === '' ? null : Number(v);
      }
      return updatePlan(plan.id, { label, limits_json: parsed });
    },
    onSuccess: () => {
      toast.success('Đã lưu gói');
      qc.invalidateQueries({ queryKey: ['superadmin', 'plans'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4 mt-4">
      <div className="space-y-1.5">
        <Label>Tên hiển thị</Label>
        <Input value={label} onChange={(e) => setLabel(e.target.value)} />
      </div>
      {LIMIT_FIELDS.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <Label>{f.label} <span className="text-muted-foreground text-xs">(để trống = không giới hạn)</span></Label>
          <Input
            type="number"
            value={limits[f.key]}
            onChange={(e) => setLimits((prev) => ({ ...prev, [f.key]: e.target.value }))}
            placeholder="∞"
          />
        </div>
      ))}
      <Button onClick={() => mut.mutate()} disabled={mut.isPending} className="w-full">
        {mut.isPending ? 'Đang lưu...' : 'Lưu thay đổi'}
      </Button>
    </div>
  );
}

export default function PlansPage() {
  const { data: plans } = useSuspenseQuery(adminPlansQuery());
  const [editing, setEditing] = useState<AdminPlan | null>(null);

  return (
    <PageWrap className="max-w-[760px]">
      <PageHeader title="Quản lý gói" subtitle="Cấu hình giới hạn cho từng gói dịch vụ." />
      <PageSection>
        <div className="divide-y divide-border rounded-xl border">
          {plans.map((plan) => (
            <div key={plan.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-medium">{plan.label}</p>
                <p className="text-xs text-muted-foreground">
                  {Object.entries(plan.limits_json)
                    .map(([k, v]) => `${k}: ${v ?? '∞'}`)
                    .join(' · ')}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => setEditing(plan)}>
                Sửa
              </Button>
            </div>
          ))}
        </div>
      </PageSection>

      <Sheet open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <SheetContent className="w-[400px] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Sửa gói {editing?.label}</SheetTitle>
          </SheetHeader>
          {editing && <PlanEditSheet plan={editing} onClose={() => setEditing(null)} />}
        </SheetContent>
      </Sheet>
    </PageWrap>
  );
}
```

- [ ] **Step 3: Wire routes and nav**

In `frontend/src/modules/superadmin/routes.tsx`, add:
```tsx
{ path: 'plans', lazy: async () => ({ Component: (await import('./features/plans/page')).default }), handle: { breadcrumb: 'Plans' } },
```

In `frontend/src/modules/superadmin/nav.ts`, add (import `Package` from lucide-react):
```ts
{ label: 'Plans', href: '/app/superadmin/plans', icon: Package },
```

- [ ] **Step 4: Final build**

```bash
bash scripts/build_frontend.sh 2>&1 | tail -5
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Final commit**

```bash
git add frontend/src/modules/superadmin/features/plans/ frontend/src/modules/superadmin/routes.tsx frontend/src/modules/superadmin/nav.ts
git commit -m "feat(ui): superadmin plans management page"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `plans` table with `limits_json` | Task 1 |
| `subscription_requests` with payment proof + refund | Task 1 |
| `boss_active_tools` table | Task 1 |
| `mcp_catalog` + `mcp_servers` tables | Task 1 (tables only, API deferred) |
| `users.plan_id` + `plan_overrides_json` | Task 1 |
| `effective_limits()` merging plan + overrides | Task 2 |
| `check_over_limit()` | Task 2 |
| File upload utility | Task 3 |
| Admin: list plans | Task 4 |
| Admin: list effective limits + over_limit | Task 4 |
| Admin: create request with payment proof | Task 4 |
| Admin: cancel request + refund QR | Task 4 |
| Admin: tools toggle with limit enforcement | Task 5 |
| Agent filters by boss active tools | Task 6 |
| Superadmin: list/approve/reject requests | Task 7 |
| Superadmin: plans CRUD | Task 8 |
| Scheduler: expired_grace degrade | Task 9 |
| Admin subscription page with plan cards | Task 11 |
| Resolution screen (over-limit) | Task 12 |
| Admin tools page | Task 13 |
| Superadmin subscriptions page | Task 14 |
| Superadmin plans page | Task 15 |
| Partial unique index for one pending per boss | Task 1 |
| `apply_plan_to_user` atomic transaction | Task 2 |

**Deferred (noted in spec):** MCP catalog API, MCP server self-service API.

**Edge cases covered:**
- Duplicate pending request → 409 (partial unique index, Task 4)
- Cancel approved request → 400 (only pending cancellable, Task 4)
- Toggle tool at limit → 400 with clear message (Task 5)
- Approve non-pending request → 400 (Task 7)
- Deactivate plan with users → 400 (Task 8)
- expired_grace → degrade to trial limits (Task 9)
- Over-limit on plan change → resolution screen (Task 12)
