"""per-provider API key health status

users.ai_key_status = JSONB {provider: {ok: bool, message: str, checked_at: iso}}
— trạng thái sống/chết của từng BYO key, ghi khi lưu (validate) và khi boss bấm
"Kiểm tra". Trang Model đọc trạng thái đã lưu (không gọi provider lúc load).

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-14
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN ai_key_status JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN ai_key_status")
