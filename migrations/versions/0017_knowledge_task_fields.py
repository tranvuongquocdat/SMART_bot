"""Knowledge task fields: assignee_name + due_at on knowledge_items (workload Pha B).

Spine làm nguồn workload (quyết định 2026-06-15): item phân-công/cam-kết mang structured
assignee_name + due_at; status active=đang làm, resolved=đã xong. Additive, reversible.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-15
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS assignee_name TEXT")
    op.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_items_assignee "
        "ON knowledge_items(boss_id, assignee_name) WHERE assignee_name IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_items_assignee")
    op.execute("ALTER TABLE knowledge_items DROP COLUMN IF EXISTS due_at")
    op.execute("ALTER TABLE knowledge_items DROP COLUMN IF EXISTS assignee_name")
