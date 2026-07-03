"""Platform settings (key-value, superadmin chỉnh qua UI) + history-window
override per-boss (DM và nhóm riêng — user chốt 2026-07-03).

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-03
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_settings (
            key        TEXT PRIMARY KEY,
            value      JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO platform_settings (key, value) VALUES
          ('history_window_dm', '12'),
          ('history_window_group', '12')
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS history_window_dm INTEGER"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS history_window_group INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS history_window_group")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS history_window_dm")
    op.execute("DROP TABLE IF EXISTS platform_settings")
