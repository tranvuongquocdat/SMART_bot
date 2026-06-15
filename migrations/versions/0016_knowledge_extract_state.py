"""Add last_extracted_message_id to group_notes (knowledge write-pipeline trigger state).

Tách khỏi last_seen_message_id (của note_updater) — knowledge extraction có cadence/cursor riêng.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-14
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE group_notes "
        "ADD COLUMN IF NOT EXISTS last_extracted_message_id BIGINT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE group_notes DROP COLUMN IF EXISTS last_extracted_message_id"
    )
