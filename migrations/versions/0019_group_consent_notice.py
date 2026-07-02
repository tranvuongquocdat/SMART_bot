"""Group consent notice: consent_notified_at on group_notes (PDPL).

Bot gửi 1 tin thông báo ghi nhận khi bắt đầu capture một nhóm (spec
2026-07-02-zalo-automation §5). Đánh dấu theo (provider, chat_id) — nhiều boss
chung nhóm/acc vẫn chỉ 1 tin. Additive, reversible.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-02
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE group_notes ADD COLUMN IF NOT EXISTS consent_notified_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE group_notes DROP COLUMN IF EXISTS consent_notified_at")
