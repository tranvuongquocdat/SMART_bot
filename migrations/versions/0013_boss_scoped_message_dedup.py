"""messages dedup theo boss + index gate group_notes

- messages: UNIQUE (provider, chat_id, provider_msg_id)
            -> UNIQUE (boss_id, provider, chat_id, provider_msg_id)
  Mô hình tenant vốn mỗi sếp một bản sao; cần cho nhóm nhiều sếp.
- group_notes: index (provider, chat_id) WHERE is_active cho bước gate cross-boss.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-14
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "DROP CONSTRAINT IF EXISTS messages_provider_chat_id_provider_msg_id_key"
    )
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT messages_boss_dedup_key "
        "UNIQUE (boss_id, provider, chat_id, provider_msg_id)"
    )
    op.execute(
        "CREATE INDEX idx_group_notes_gate ON group_notes (provider, chat_id) "
        "WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_group_notes_gate")
    op.execute(
        "ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_boss_dedup_key"
    )
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT messages_provider_chat_id_provider_msg_id_key "
        "UNIQUE (provider, chat_id, provider_msg_id)"
    )
