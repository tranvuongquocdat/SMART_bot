"""group_members + group_summaries + decisions + group_artifacts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE group_members (
      id BIGSERIAL PRIMARY KEY,
      group_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      display_name TEXT NOT NULL,
      external_id TEXT,
      role TEXT,
      last_seen_at TIMESTAMPTZ,
      joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(group_id, external_id)
    );
    """)
    op.execute("CREATE INDEX idx_group_members_group ON group_members(group_id);")

    op.execute("""
    CREATE TABLE group_summaries (
      id BIGSERIAL PRIMARY KEY,
      group_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      date_label TEXT NOT NULL,
      body TEXT,
      model TEXT,
      tokens INTEGER,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX idx_group_summaries_group_date ON group_summaries(group_id, date_label);")
    op.execute("CREATE INDEX idx_group_summaries_updated ON group_summaries(updated_at DESC);")

    op.execute("""
    CREATE TABLE decisions (
      id BIGSERIAL PRIMARY KEY,
      group_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      text TEXT NOT NULL,
      decided_by TEXT,
      source_message_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX idx_decisions_group ON decisions(group_id, created_at DESC);")

    op.execute("""
    CREATE TABLE group_artifacts (
      id BIGSERIAL PRIMARY KEY,
      group_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      kind TEXT NOT NULL CHECK (kind IN ('doc','link','image','video')),
      name TEXT NOT NULL,
      url TEXT,
      source_message_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX idx_group_artifacts_group ON group_artifacts(group_id, created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS group_artifacts;")
    op.execute("DROP TABLE IF EXISTS decisions;")
    op.execute("DROP TABLE IF EXISTS group_summaries;")
    op.execute("DROP TABLE IF EXISTS group_members;")
