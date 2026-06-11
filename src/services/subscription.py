"""Subscription plan limits, over-limit detection, and plan application."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    """Merge plan limits_json with per-boss plan_overrides_json.

    plan_overrides_json keys win over plan limits_json.
    null values mean unlimited.
    """
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

    plan_limits = row["plan_limits"]
    plan_overrides = row["plan_overrides_json"]
    # asyncpg returns JSONB as str unless a codec is registered
    if isinstance(plan_limits, str):
        plan_limits = json.loads(plan_limits)
    if isinstance(plan_overrides, str):
        plan_overrides = json.loads(plan_overrides)
    merged = {**plan_limits, **plan_overrides}

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
            "SELECT COUNT(*) FROM bot_account_assignments WHERE boss_id=$1 AND status='active'",
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
    """Apply an approved plan to a boss user atomically."""
    async with pool.acquire() as c:
        async with c.transaction():
            plan = await c.fetchrow(
                "SELECT limits_json FROM plans WHERE id=$1", plan_id
            )
            if not plan:
                raise ValueError(f"Plan {plan_id} not found")

            merged = {**dict(plan["limits_json"]), **overrides}
            expiry = None
            if merged.get("duration_days") is not None:
                expiry = datetime.now(timezone.utc) + timedelta(
                    days=int(merged["duration_days"])
                )
            cap = (
                float(merged["cost_cap_usd_daily"])
                if merged.get("cost_cap_usd_daily") is not None
                else 5.0
            )

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
                cap,
            )


async def provision_new_boss(db: Any, boss_id: int) -> None:
    """Khởi tạo mặc định cho boss mới: gán gói trial + seed bộ tools active.

    - Boss chưa có gói → trial (UI hiển thị full tools, limit active theo trial).
    - Seed tools active cắt theo max_active_tools của gói hiệu lực.
    - Runtime filter là strict intersect nên boss 0 rows = không tool nào;
      mọi đường tạo user role=boss đều phải gọi hàm này.

    ``db`` nhận cả pool lẫn connection (đường promotion tạo user trong
    transaction đang mở).
    """
    if hasattr(db, "acquire"):
        async with db.acquire() as c:
            await _provision_new_boss_on_conn(c, boss_id)
    else:
        await _provision_new_boss_on_conn(db, boss_id)


async def _provision_new_boss_on_conn(c: Any, boss_id: int) -> None:
    from src.tools.registry import _REGISTRY

    await c.execute(
        """
        UPDATE users SET plan_id = (SELECT id FROM plans WHERE name = 'trial')
        WHERE id = $1 AND plan_id IS NULL
        """,
        boss_id,
    )
    names = list(_REGISTRY.keys())
    if not names:
        return
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
    if row:
        plan_limits = row["plan_limits"]
        plan_overrides = row["plan_overrides_json"]
        # asyncpg returns JSONB as str unless a codec is registered
        if isinstance(plan_limits, str):
            plan_limits = json.loads(plan_limits)
        if isinstance(plan_overrides, str):
            plan_overrides = json.loads(plan_overrides)
        cap = {**plan_limits, **plan_overrides}.get("max_active_tools")
        if cap is not None:
            names = names[: int(cap)]
    await c.executemany(
        """
        INSERT INTO boss_active_tools (boss_id, tool_name)
        VALUES ($1, $2) ON CONFLICT DO NOTHING
        """,
        [(boss_id, n) for n in names],
    )


async def is_group_active(pool: Any, boss_id: int, provider: str, chat_id: str) -> bool:
    """Nhóm bị tắt (is_active=FALSE) → bot ngừng xử lý tin nhắn nhóm đó.

    Nhóm chưa có row group_notes → coi như active (chưa được theo dõi,
    không phải bị tắt).
    """
    async with pool.acquire() as c:
        active = await c.fetchval(
            """
            SELECT is_active FROM group_notes
            WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
            """,
            boss_id,
            provider,
            chat_id,
        )
    return True if active is None else bool(active)
