"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-31
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("""
    CREATE TABLE users (
      id                       SERIAL PRIMARY KEY,
      email                    TEXT NOT NULL UNIQUE,
      name                     TEXT,
      google_sub               TEXT UNIQUE,
      password_hash            TEXT,
      role                     TEXT NOT NULL DEFAULT 'boss',
      subscription_status      TEXT NOT NULL DEFAULT 'trial',
      subscription_plan        TEXT,
      subscription_expiry      TIMESTAMPTZ,
      tz                       TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
      language                 TEXT NOT NULL DEFAULT 'vi',
      smart_model_id           BIGINT,
      fast_model_id            BIGINT,
      vision_model_id          BIGINT,
      api_keys_enc             BYTEA,
      cost_cap_usd_daily       NUMERIC(8,2) NOT NULL DEFAULT 5.0,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE bot_accounts (
      id                       BIGSERIAL PRIMARY KEY,
      provider                 TEXT NOT NULL,
      provider_user_id         TEXT NOT NULL,
      display_name             TEXT,
      account_kind             TEXT NOT NULL,
      ownership                TEXT NOT NULL,
      owner_boss_id            INTEGER REFERENCES users(id),
      credentials_blob_enc     BYTEA,
      status                   TEXT NOT NULL DEFAULT 'active',
      status_reason            TEXT,
      max_assigned_bosses      INTEGER NOT NULL DEFAULT 5,
      last_seen_at             TIMESTAMPTZ,
      msgs_received_total      BIGINT NOT NULL DEFAULT 0,
      msgs_sent_total          BIGINT NOT NULL DEFAULT 0,
      notes                    TEXT,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (provider, provider_user_id),
      CHECK (
        (ownership = 'platform'   AND owner_boss_id IS NULL) OR
        (ownership = 'boss_owned' AND owner_boss_id IS NOT NULL)
      )
    )
    """)

    op.execute("""
    CREATE TABLE bot_account_assignments (
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
      assignment_kind  TEXT NOT NULL,
      status           TEXT NOT NULL DEFAULT 'pending_accept',
      assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      assigned_by      INTEGER REFERENCES users(id),
      accepted_at      TIMESTAMPTZ,
      PRIMARY KEY (boss_id, provider)
    )
    """)
    op.execute("CREATE INDEX idx_assignments_account ON bot_account_assignments(bot_account_id)")

    op.execute("""
    CREATE TABLE account_links (
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      provider_user_id TEXT NOT NULL,
      linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (provider, provider_user_id)
    )
    """)
    op.execute("CREATE INDEX idx_account_links_boss ON account_links(boss_id)")

    op.execute("""
    CREATE TABLE linking_tokens (
      token            TEXT PRIMARY KEY,
      boss_id          INTEGER NOT NULL REFERENCES users(id),
      provider         TEXT NOT NULL,
      bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
      expires_at       TIMESTAMPTZ NOT NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at)")

    op.execute("""
    CREATE TABLE note_templates (
      id              BIGSERIAL PRIMARY KEY,
      name            TEXT NOT NULL,
      description     TEXT,
      is_system       BOOLEAN NOT NULL DEFAULT FALSE,
      owner_boss_id   INTEGER REFERENCES users(id),
      sections_json   JSONB NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_note_templates_owner ON note_templates(owner_boss_id)")

    op.execute("""
    CREATE TABLE group_notes (
      id                         BIGSERIAL PRIMARY KEY,
      boss_id                    INTEGER NOT NULL REFERENCES users(id),
      provider                   TEXT NOT NULL,
      chat_id                    TEXT NOT NULL,
      group_name                 TEXT,
      content                    TEXT NOT NULL DEFAULT '',
      manually_edited_sections   JSONB NOT NULL DEFAULT '[]'::jsonb,
      last_seen_message_id       BIGINT,
      status                     TEXT NOT NULL DEFAULT 'active',
      msg_count_7d               INTEGER NOT NULL DEFAULT 0,
      template_id                BIGINT REFERENCES note_templates(id),
      updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, provider, chat_id)
    )
    """)
    op.execute("CREATE INDEX idx_group_notes_boss ON group_notes(boss_id)")

    op.execute("""
    CREATE TABLE group_note_versions (
      id            BIGSERIAL PRIMARY KEY,
      group_note_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      content       TEXT NOT NULL,
      emitted_by    TEXT NOT NULL,
      emitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX idx_group_note_versions_note "
        "ON group_note_versions(group_note_id, emitted_at DESC)"
    )

    op.execute("""
    CREATE TABLE messages (
      id                 BIGSERIAL PRIMARY KEY,
      boss_id            INTEGER NOT NULL REFERENCES users(id),
      provider           TEXT NOT NULL,
      chat_id            TEXT NOT NULL,
      chat_type          TEXT NOT NULL,
      provider_msg_id    TEXT,
      reply_to_msg_id    BIGINT REFERENCES messages(id),
      sender_provider_id TEXT,
      sender_name        TEXT,
      text               TEXT,
      media_kind         TEXT,
      media_url          TEXT,
      media_text         TEXT,
      ts                 TIMESTAMPTZ NOT NULL,
      ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      fts                tsvector,
      UNIQUE (provider, chat_id, provider_msg_id)
    )
    """)
    op.execute(
        "CREATE INDEX idx_messages_chat ON messages(boss_id, provider, chat_id, ts DESC)"
    )
    op.execute("CREATE INDEX idx_messages_fts ON messages USING GIN(fts)")
    op.execute("""
    CREATE OR REPLACE FUNCTION messages_fts_trigger() RETURNS trigger AS $$
    BEGIN
      NEW.fts := to_tsvector('simple',
        unaccent(coalesce(NEW.text,'') || ' ' || coalesce(NEW.media_text,'')));
      RETURN NEW;
    END;$$ LANGUAGE plpgsql;
    """)
    op.execute(
        "CREATE TRIGGER trg_messages_fts BEFORE INSERT OR UPDATE ON messages "
        "FOR EACH ROW EXECUTE FUNCTION messages_fts_trigger()"
    )

    op.execute("""
    CREATE TABLE media_cache (
      id              BIGSERIAL PRIMARY KEY,
      source_key      TEXT NOT NULL,
      source_kind     TEXT NOT NULL,
      media_text      TEXT NOT NULL,
      title           TEXT,
      fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      expires_at      TIMESTAMPTZ,
      UNIQUE (source_key, source_kind)
    )
    """)
    op.execute("CREATE INDEX idx_media_cache_expires ON media_cache(expires_at)")

    op.execute("""
    CREATE TABLE outbound_messages (
      id                  BIGSERIAL PRIMARY KEY,
      boss_id             INTEGER NOT NULL REFERENCES users(id),
      provider            TEXT NOT NULL,
      chat_id             TEXT NOT NULL,
      reply_to_message_id BIGINT REFERENCES messages(id),
      content             TEXT NOT NULL,
      trigger             TEXT NOT NULL,
      sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      status              TEXT NOT NULL,
      error               TEXT
    )
    """)

    op.execute("""
    CREATE TABLE pins (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      message_id      BIGINT NOT NULL REFERENCES messages(id),
      note            TEXT,
      pinned_by       INTEGER NOT NULL REFERENCES users(id),
      pinned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (group_note_id, message_id)
    )
    """)
    op.execute("CREATE INDEX idx_pins_group ON pins(group_note_id)")

    op.execute("""
    CREATE TABLE memory_entries (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      scope           TEXT NOT NULL,
      key             TEXT,
      content         TEXT NOT NULL,
      meta_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
      qdrant_point_id TEXT,
      source          TEXT NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, scope, key)
    )
    """)
    op.execute("CREATE INDEX idx_memory_boss_scope ON memory_entries(boss_id, scope)")

    op.execute("""
    CREATE TABLE models (
      id                       BIGSERIAL PRIMARY KEY,
      name                     TEXT NOT NULL,
      provider                 TEXT NOT NULL,
      endpoint_kind            TEXT NOT NULL,
      base_url                 TEXT,
      tier                     TEXT NOT NULL,
      ctx_max                  INTEGER NOT NULL,
      capabilities             JSONB NOT NULL DEFAULT '[]'::jsonb,
      cost_per_1m_input_usd    NUMERIC(10,4),
      cost_per_1m_output_usd   NUMERIC(10,4),
      is_platform_default      BOOLEAN NOT NULL DEFAULT FALSE,
      is_active                BOOLEAN NOT NULL DEFAULT TRUE,
      notes                    TEXT,
      created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (provider, name)
    )
    """)

    op.execute("""
    CREATE TABLE llm_routes (
      id                  BIGSERIAL PRIMARY KEY,
      feature             TEXT NOT NULL,
      condition_cel       TEXT,
      target_tier         TEXT NOT NULL,
      fallback_chain      JSONB NOT NULL DEFAULT '[]'::jsonb,
      weight              INTEGER NOT NULL DEFAULT 100,
      is_active           BOOLEAN NOT NULL DEFAULT TRUE,
      notes               TEXT,
      updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_llm_routes_feature ON llm_routes(feature) WHERE is_active")

    op.execute("""
    CREATE TABLE feature_budgets (
      feature                  TEXT PRIMARY KEY,
      max_input_tokens         INTEGER NOT NULL,
      max_output_tokens        INTEGER NOT NULL,
      trim_policy_json         JSONB NOT NULL,
      compression_strategy     TEXT NOT NULL DEFAULT 'none',
      cache_prefix_hint        TEXT,
      updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE retrieval_pipelines (
      feature        TEXT PRIMARY KEY,
      stages_json    JSONB NOT NULL,
      description    TEXT,
      updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE agent_triggers (
      id              BIGSERIAL PRIMARY KEY,
      op_name         TEXT NOT NULL,
      event_name      TEXT NOT NULL,
      debounce_json   JSONB,
      threshold_json  JSONB,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE prompts (
      id          BIGSERIAL PRIMARY KEY,
      key         TEXT NOT NULL,
      version     INTEGER NOT NULL,
      body        TEXT NOT NULL,
      is_active   BOOLEAN NOT NULL DEFAULT FALSE,
      notes       TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_by  INTEGER REFERENCES users(id),
      UNIQUE (key, version)
    )
    """)
    op.execute("CREATE UNIQUE INDEX idx_prompts_active_per_key ON prompts(key) WHERE is_active")

    op.execute("""
    CREATE TABLE token_usage (
      id                      BIGSERIAL PRIMARY KEY,
      boss_id                 INTEGER NOT NULL REFERENCES users(id),
      feature                 TEXT NOT NULL,
      operation               TEXT NOT NULL,
      provider                TEXT NOT NULL,
      model                   TEXT NOT NULL,
      tokens_in               INTEGER NOT NULL,
      tokens_out              INTEGER NOT NULL,
      tokens_cached           INTEGER NOT NULL DEFAULT 0,
      cost_usd                NUMERIC(10,6) NOT NULL,
      cost_saved_cache_usd    NUMERIC(10,6) NOT NULL DEFAULT 0,
      latency_ms              INTEGER NOT NULL,
      trace_id                TEXT,
      span_id                 TEXT,
      parent_span_id          TEXT,
      gen_ai_system           TEXT,
      gen_ai_request_model    TEXT,
      gen_ai_response_model   TEXT,
      gen_ai_operation_name   TEXT,
      called_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      status                  TEXT NOT NULL
    )
    """)
    op.execute("CREATE INDEX idx_token_usage_boss_time ON token_usage(boss_id, called_at DESC)")
    op.execute(
        "CREATE INDEX idx_token_usage_feature_time ON token_usage(feature, called_at DESC)"
    )

    op.execute("""
    CREATE TABLE tool_call_log (
      id              BIGSERIAL PRIMARY KEY,
      trace_id        TEXT NOT NULL,
      span_id         TEXT NOT NULL,
      parent_span_id  TEXT,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      tool_name       TEXT NOT NULL,
      args_hash       TEXT NOT NULL,
      status          TEXT NOT NULL,
      latency_ms      INTEGER NOT NULL,
      error           TEXT,
      called_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_tool_call_log_trace ON tool_call_log(trace_id)")

    op.execute("""
    CREATE TABLE action_items (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
      text            TEXT NOT NULL,
      assignee_name   TEXT,
      due_at          TIMESTAMPTZ,
      status          TEXT NOT NULL DEFAULT 'open',
      source          TEXT NOT NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_action_items_boss_status ON action_items(boss_id, status)")
    op.execute(
        "CREATE INDEX idx_action_items_due ON action_items(boss_id, due_at) WHERE status='open'"
    )

    op.execute("""
    CREATE TABLE scheduled_reminders (
      id                BIGSERIAL PRIMARY KEY,
      boss_id           INTEGER NOT NULL REFERENCES users(id),
      text              TEXT NOT NULL,
      due_at            TIMESTAMPTZ NOT NULL,
      scope             TEXT NOT NULL,
      provider          TEXT,
      chat_id           TEXT,
      bot_account_id    BIGINT REFERENCES bot_accounts(id),
      recurring         TEXT,
      action_item_id    BIGINT REFERENCES action_items(id),
      status            TEXT NOT NULL DEFAULT 'pending',
      fired_at          TIMESTAMPTZ,
      last_error        TEXT,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_by_op     TEXT NOT NULL
    )
    """)
    op.execute(
        "CREATE INDEX idx_reminders_due ON scheduled_reminders(due_at, status) "
        "WHERE status='pending'"
    )
    op.execute("CREATE INDEX idx_reminders_boss ON scheduled_reminders(boss_id, status)")

    op.execute("""
    CREATE TABLE boss_integrations (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id),
      plugin_id       TEXT NOT NULL,
      enabled         BOOLEAN NOT NULL DEFAULT TRUE,
      auth_blob_enc   BYTEA,
      settings_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
      connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (boss_id, plugin_id)
    )
    """)

    op.execute("""
    CREATE TABLE admin_audit_log (
      id              BIGSERIAL PRIMARY KEY,
      actor_user_id   INTEGER NOT NULL REFERENCES users(id),
      action          TEXT NOT NULL,
      target_kind     TEXT,
      target_id       TEXT,
      reason          TEXT,
      payload_json    JSONB,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    # FK from users.smart/fast/vision_model_id deferred (forward ref)
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_smart_model "
        "FOREIGN KEY (smart_model_id) REFERENCES models(id)"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_fast_model "
        "FOREIGN KEY (fast_model_id) REFERENCES models(id)"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT fk_users_vision_model "
        "FOREIGN KEY (vision_model_id) REFERENCES models(id)"
    )


def downgrade():
    for t in [
        "admin_audit_log",
        "boss_integrations",
        "scheduled_reminders",
        "action_items",
        "tool_call_log",
        "token_usage",
        "prompts",
        "agent_triggers",
        "retrieval_pipelines",
        "feature_budgets",
        "llm_routes",
        "models",
        "memory_entries",
        "pins",
        "outbound_messages",
        "media_cache",
        "messages",
        "group_note_versions",
        "group_notes",
        "note_templates",
        "linking_tokens",
        "account_links",
        "bot_account_assignments",
        "bot_accounts",
        "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS messages_fts_trigger()")
