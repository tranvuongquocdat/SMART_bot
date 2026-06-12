"""proxy pool — IP dân cư gán per-boss cho kênh session (zalo/messenger)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-12
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE proxies (
      id          BIGSERIAL PRIMARY KEY,
      label       TEXT NOT NULL,
      url_enc     BYTEA NOT NULL,              -- Fernet(scheme://user:pass@host:port)
      region      TEXT,                        -- 'VN','VN-HN','VN-HCM'...
      status      TEXT NOT NULL DEFAULT 'active',  -- active|dead|disabled
      max_bosses  INTEGER NOT NULL DEFAULT 1,  -- cap số khách/proxy (1 = riêng, >1 = chia sẻ)
      notes       TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    ALTER TABLE users
      ADD COLUMN proxy_id BIGINT REFERENCES proxies(id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX idx_users_proxy ON users(proxy_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_proxy")
    op.execute("ALTER TABLE users DROP COLUMN proxy_id")
    op.execute("DROP TABLE proxies")
