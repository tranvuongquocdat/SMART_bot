"""mỗi boss chỉ 1 bot account boss_owned cho mỗi nền tảng

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-12
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dọn bản trùng cũ: mỗi (owner_boss_id, provider) chỉ giữ một boss_owned.
    # Ưu tiên giữ bản đang được assignment trỏ tới, nếu không thì bản mới nhất.
    op.execute("""
    WITH ranked AS (
      SELECT ba.id,
             ROW_NUMBER() OVER (
               PARTITION BY ba.owner_boss_id, ba.provider
               ORDER BY (EXISTS (
                          SELECT 1 FROM bot_account_assignments x
                          WHERE x.bot_account_id = ba.id AND x.status='active'
                        )) DESC,
                        ba.updated_at DESC, ba.id DESC
             ) AS rn
      FROM bot_accounts ba
      WHERE ba.ownership='boss_owned' AND ba.owner_boss_id IS NOT NULL
    )
    DELETE FROM bot_account_assignments
    WHERE bot_account_id IN (SELECT id FROM ranked WHERE rn > 1)
    """)
    op.execute("""
    WITH ranked AS (
      SELECT ba.id,
             ROW_NUMBER() OVER (
               PARTITION BY ba.owner_boss_id, ba.provider
               ORDER BY (EXISTS (
                          SELECT 1 FROM bot_account_assignments x
                          WHERE x.bot_account_id = ba.id AND x.status='active'
                        )) DESC,
                        ba.updated_at DESC, ba.id DESC
             ) AS rn
      FROM bot_accounts ba
      WHERE ba.ownership='boss_owned' AND ba.owner_boss_id IS NOT NULL
    )
    DELETE FROM bot_accounts WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """)

    op.execute("""
    CREATE UNIQUE INDEX uq_boss_owned_one_per_provider
      ON bot_accounts(owner_boss_id, provider)
      WHERE ownership='boss_owned'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_boss_owned_one_per_provider")
