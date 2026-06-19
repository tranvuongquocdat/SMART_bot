"""platform_integrations + integration_usage

Superadmin-managed integration provider keys (e.g. Tavily web search):
- platform_integrations: encrypted api key + configurable unit cost + health status
- integration_usage: daily rollup per (provider, boss) for cost charts
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE platform_integrations (
          provider       TEXT PRIMARY KEY,
          api_key_enc    TEXT,
          unit_cost_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
          status         JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE integration_usage (
          provider   TEXT NOT NULL,
          boss_id    INTEGER NOT NULL,
          day        DATE NOT NULL,
          count      INTEGER NOT NULL DEFAULT 0,
          cost_usd   NUMERIC(12,6) NOT NULL DEFAULT 0,
          PRIMARY KEY (provider, boss_id, day)
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS integration_usage")
    op.execute("DROP TABLE IF EXISTS platform_integrations")
