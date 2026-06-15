"""custom / self-hosted AI provider base URLs per boss

users.ai_provider_urls = JSON {provider: base_url} cho các provider tuỳ chỉnh /
self-hosted (OpenAI-compatible: vLLM, Ollama, OpenRouter, ...). Provider built-in
(openai/groq/gemini) không cần — dùng PROVIDER_DEFAULTS. Key vẫn ở api_keys_enc.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-13
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN ai_provider_urls JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN ai_provider_urls")
