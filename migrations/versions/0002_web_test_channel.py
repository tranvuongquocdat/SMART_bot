"""web test channel sim tables + bot_account seed

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE web_users (
      id            TEXT PRIMARY KEY,
      name          TEXT NOT NULL,
      is_boss       BOOLEAN NOT NULL DEFAULT FALSE,
      boss_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_web_users_boss ON web_users(boss_user_id)")

    op.execute("""
    CREATE TABLE web_groups (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE web_group_members (
      group_id     TEXT NOT NULL REFERENCES web_groups(id) ON DELETE CASCADE,
      web_user_id  TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
      PRIMARY KEY (group_id, web_user_id)
    )
    """)
    op.execute("CREATE INDEX idx_web_group_members_user ON web_group_members(web_user_id)")

    op.execute("""
    INSERT INTO bot_accounts (provider, provider_user_id, display_name,
                              account_kind, ownership, status)
    VALUES ('web', 'web-bot-1', 'Web Test Bot', 'personal', 'platform', 'active')
    ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM bot_accounts WHERE provider='web'")
    op.execute("DROP TABLE IF EXISTS web_group_members")
    op.execute("DROP TABLE IF EXISTS web_groups")
    op.execute("DROP TABLE IF EXISTS web_users")
