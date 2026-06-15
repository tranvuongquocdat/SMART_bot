from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class BossContext:
    boss_id: int
    user_role: str  # 'boss' | 'superadmin'
    ui_language: str = "vi"  # 'vi' | 'en' — web UI language for localizing API messages


class BossScopedRepo:
    """Inject (db_pool, boss_context) via constructor.

    Subclasses must filter every query by self.ctx.boss_id (unless the
    operation is explicitly superadmin-only, in which case assert role).
    """

    def __init__(self, pool: asyncpg.Pool, ctx: BossContext):
        self.pool = pool
        self.ctx = ctx
