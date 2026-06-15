"""models.owner_boss_id — phân biệt model nền tảng (được cấp) và model riêng của boss

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-12
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE models
      ADD COLUMN owner_boss_id BIGINT REFERENCES users(id) ON DELETE CASCADE
    """)
    op.execute("CREATE INDEX idx_models_owner_boss ON models(owner_boss_id)")

    # UNIQUE(provider, name) toàn cục chặn 2 boss thêm cùng một model —
    # tách thành: duy nhất trong phạm vi nền tảng, và duy nhất per-boss.
    op.execute("ALTER TABLE models DROP CONSTRAINT models_provider_name_key")
    op.execute("""
    CREATE UNIQUE INDEX uq_models_platform_provider_name
      ON models(provider, name) WHERE owner_boss_id IS NULL
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_models_boss_provider_name
      ON models(provider, name, owner_boss_id) WHERE owner_boss_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DELETE FROM models WHERE owner_boss_id IS NOT NULL")
    op.execute("DROP INDEX IF EXISTS uq_models_boss_provider_name")
    op.execute("DROP INDEX IF EXISTS uq_models_platform_provider_name")
    op.execute("ALTER TABLE models ADD CONSTRAINT models_provider_name_key UNIQUE (provider, name)")
    op.execute("DROP INDEX IF EXISTS idx_models_owner_boss")
    op.execute("ALTER TABLE models DROP COLUMN owner_boss_id")
