"""subscription plans, requests, mcp tables, boss_active_tools, group_notes.is_active

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-08
"""

from alembic import op
from sqlalchemy import text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE plans (
      id           SERIAL PRIMARY KEY,
      name         TEXT NOT NULL UNIQUE,
      label        TEXT NOT NULL,
      limits_json  JSONB NOT NULL DEFAULT '{}',
      is_active    BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order   INTEGER NOT NULL DEFAULT 0,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # Use text() to avoid SQLAlchemy misinterpreting :N patterns in JSON as bind params.
    # Spaces after colons also prevent false matches.
    op.execute(text("""
    INSERT INTO plans (name, label, limits_json, sort_order) VALUES
      ('trial',   'Trial',   '{"max_active_groups": 2,"max_active_tools": 5,"max_active_channels": 1,"mcp_slots": 0,"duration_days": 14,"cost_cap_usd_daily": 0.5}'::jsonb,   0),
      ('starter', 'Starter', '{"max_active_groups": 5,"max_active_tools": 10,"max_active_channels": 1,"mcp_slots": 0,"duration_days": 30,"cost_cap_usd_daily": 2.0}'::jsonb,  1),
      ('pro',     'Pro',     '{"max_active_groups": 30,"max_active_tools": null,"max_active_channels": 3,"mcp_slots": 2,"duration_days": 30,"cost_cap_usd_daily": 5.0}'::jsonb, 2),
      ('custom',  'Custom',  '{"max_active_groups": null,"max_active_tools": null,"max_active_channels": null,"mcp_slots": null,"duration_days": null,"cost_cap_usd_daily": null}'::jsonb, 3)
    """))

    op.execute("""
    CREATE TABLE subscription_requests (
      id                  BIGSERIAL PRIMARY KEY,
      boss_id             BIGINT NOT NULL REFERENCES users(id),
      plan_id             INTEGER NOT NULL REFERENCES plans(id),
      status              TEXT NOT NULL DEFAULT 'pending',
      note                TEXT,
      payment_proof_path  TEXT,
      amount_paid_vnd     INTEGER,
      transfer_content    TEXT,
      reviewer_note       TEXT,
      reviewed_at         TIMESTAMPTZ,
      cancel_reason       TEXT,
      refund_requested    BOOLEAN NOT NULL DEFAULT FALSE,
      refund_qr_path      TEXT,
      cancelled_at        TIMESTAMPTZ,
      created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_one_pending_per_boss
      ON subscription_requests(boss_id)
      WHERE status = 'pending'
    """)

    op.execute("""
    CREATE TABLE boss_active_tools (
      boss_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      tool_name  TEXT NOT NULL,
      enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (boss_id, tool_name)
    )
    """)

    # Seed all existing bosses with all currently registered tools active
    op.execute("""
    INSERT INTO boss_active_tools (boss_id, tool_name)
    SELECT u.id, t.name
    FROM users u
    CROSS JOIN (VALUES
      ('search_history'),('count_messages'),('list_groups'),('list_reminders'),
      ('set_reminder'),('cancel_reminder'),('list_action_items'),('mark_action_item'),
      ('pin_message'),('unpin_message'),('find_exact_quote'),('remember'),('forget'),
      ('fetch_url'),('edit_group_note'),('read_group_note'),
      ('refresh_group_note'),('current_time')
    ) AS t(name)
    WHERE u.role = 'boss'
    ON CONFLICT DO NOTHING
    """)

    # MCP tables (API deferred to future milestone)
    op.execute("""
    CREATE TABLE mcp_catalog (
      id                    SERIAL PRIMARY KEY,
      name                  TEXT NOT NULL,
      description           TEXT,
      url                   TEXT NOT NULL,
      config_template_json  JSONB NOT NULL DEFAULT '[]',
      icon_url              TEXT,
      is_active             BOOLEAN NOT NULL DEFAULT TRUE,
      created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE mcp_servers (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      catalog_id      INTEGER REFERENCES mcp_catalog(id),
      name            TEXT NOT NULL,
      url             TEXT NOT NULL,
      auth_json_enc   TEXT,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # group_notes: add explicit is_active toggle (separate from existing status field)
    op.execute(
        "ALTER TABLE group_notes ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )

    # users: structured plan FK + per-boss limit overrides
    op.execute("ALTER TABLE users ADD COLUMN plan_id INTEGER REFERENCES plans(id)")
    op.execute(
        "ALTER TABLE users ADD COLUMN plan_overrides_json JSONB NOT NULL DEFAULT '{}'"
    )

    # Set existing bosses on trial plan
    op.execute("""
    UPDATE users SET plan_id = (SELECT id FROM plans WHERE name = 'trial')
    WHERE role = 'boss' AND plan_id IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_overrides_json")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_id")
    op.execute("ALTER TABLE group_notes DROP COLUMN IF EXISTS is_active")
    op.execute("DROP TABLE IF EXISTS mcp_servers")
    op.execute("DROP TABLE IF EXISTS mcp_catalog")
    op.execute("DROP TABLE IF EXISTS boss_active_tools")
    op.execute("DROP INDEX IF EXISTS uq_one_pending_per_boss")
    op.execute("DROP TABLE IF EXISTS subscription_requests")
    op.execute("DROP TABLE IF EXISTS plans")
