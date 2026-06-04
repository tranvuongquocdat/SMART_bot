"""Add projects table and project_id FK to action_items.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-04
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE projects (
      id          BIGSERIAL PRIMARY KEY,
      boss_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name        TEXT NOT NULL,
      description TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX idx_projects_boss_id ON projects(boss_id)"
    )

    op.execute(
        "ALTER TABLE action_items ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES projects(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE action_items DROP COLUMN IF EXISTS project_id")
    op.execute("DROP TABLE IF EXISTS projects CASCADE")
