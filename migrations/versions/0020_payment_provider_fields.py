"""Payment provider fields on subscription_requests (mở đường auto-payment).

User chốt 2026-07-02: thanh toán giữ MANUAL nhưng code mở đường tích hợp
tự động đa kênh sau (SePay/Casso webhook, PayOS...). Mỗi request ghi nguồn
xác nhận thanh toán + mã giao dịch phía provider. Additive, reversible.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-02
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscription_requests "
        "ADD COLUMN IF NOT EXISTS payment_provider TEXT NOT NULL DEFAULT 'manual_bank'"
    )
    op.execute(
        "ALTER TABLE subscription_requests "
        "ADD COLUMN IF NOT EXISTS provider_txn_id TEXT"
    )
    # Webhook tương lai dedupe theo mã giao dịch của provider.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_requests_provider_txn "
        "ON subscription_requests(payment_provider, provider_txn_id) "
        "WHERE provider_txn_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_subscription_requests_provider_txn")
    op.execute("ALTER TABLE subscription_requests DROP COLUMN IF EXISTS provider_txn_id")
    op.execute("ALTER TABLE subscription_requests DROP COLUMN IF EXISTS payment_provider")
