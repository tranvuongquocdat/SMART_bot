"""plans.prices_json (giá theo chu kỳ 1/3/12 tháng) + subscription_requests.billing_months

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-12
"""

from alembic import op
from sqlalchemy import text

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE plans
      ADD COLUMN prices_json JSONB NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute("""
    ALTER TABLE subscription_requests
      ADD COLUMN billing_months INTEGER
    """)

    # Giá tham khảo (VND theo chu kỳ): 3 tháng ~8% off, 12 tháng ~17% off.
    # Trial miễn phí, Custom để trống (liên hệ).
    op.execute(text("""
    UPDATE plans SET prices_json = '{"1": 199000,"3": 549000,"12": 1990000}'::jsonb
    WHERE name = 'starter'
    """))
    op.execute(text("""
    UPDATE plans SET prices_json = '{"1": 499000,"3": 1390000,"12": 4990000}'::jsonb
    WHERE name = 'pro'
    """))


def downgrade() -> None:
    op.execute("ALTER TABLE subscription_requests DROP COLUMN billing_months")
    op.execute("ALTER TABLE plans DROP COLUMN prices_json")
