"""Legal documents (ToS/Privacy versioned + acceptances) + capture opt-outs
+ boss group-consent confirmation (spec 2026-07-02-legal-consent-design).

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-02
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_documents (
            id           BIGSERIAL PRIMARY KEY,
            kind         TEXT NOT NULL CHECK (kind IN ('terms', 'privacy')),
            version      INTEGER NOT NULL,
            content_md   TEXT NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE (kind, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_acceptances (
            id          BIGSERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            version     INTEGER NOT NULL,
            accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, kind, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS capture_optouts (
            id               BIGSERIAL PRIMARY KEY,
            provider         TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            display_name     TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (provider, provider_user_id)
        )
        """
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS group_consent_confirmed_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS group_consent_confirmed_at")
    op.execute("DROP TABLE IF EXISTS capture_optouts")
    op.execute("DROP TABLE IF EXISTS legal_acceptances")
    op.execute("DROP TABLE IF EXISTS legal_documents")
