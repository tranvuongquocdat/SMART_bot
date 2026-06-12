"""tách ngôn ngữ web (ui_language) khỏi ngôn ngữ bot (language)

users.language = ngôn ngữ trợ lý trả lời (nối vào prompt agent).
users.ui_language = ngôn ngữ giao diện web.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-12
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Kế thừa giá trị language hiện có làm ui_language ban đầu (pilot i18n đang
    # lưu ngôn ngữ web vào language) để không mất lựa chọn của user.
    op.execute("ALTER TABLE users ADD COLUMN ui_language TEXT NOT NULL DEFAULT 'vi'")
    op.execute("UPDATE users SET ui_language = language WHERE language IN ('vi', 'en')")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN ui_language")
