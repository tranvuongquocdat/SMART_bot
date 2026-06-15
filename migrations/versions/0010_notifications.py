"""notifications — chuông thông báo (broadcast + theo từng boss) + trạng thái đã đọc

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-12
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE notifications (
      id          BIGSERIAL PRIMARY KEY,
      audience    TEXT NOT NULL,              -- 'broadcast' (mọi user) | 'boss' (một boss)
      boss_id     BIGINT REFERENCES users(id) ON DELETE CASCADE,  -- set khi audience='boss'
      kind        TEXT NOT NULL DEFAULT 'system',  -- announcement | subscription | system
      title       TEXT NOT NULL,
      body        TEXT,
      link        TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CHECK ((audience='broadcast' AND boss_id IS NULL) OR (audience='boss' AND boss_id IS NOT NULL))
    )
    """)
    op.execute("CREATE INDEX idx_notifications_boss ON notifications(boss_id, created_at DESC)")
    op.execute("CREATE INDEX idx_notifications_broadcast ON notifications(created_at DESC) WHERE audience='broadcast'")

    op.execute("""
    CREATE TABLE notification_reads (
      notification_id BIGINT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
      user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      read_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (notification_id, user_id)
    )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE notification_reads")
    op.execute("DROP TABLE notifications")
