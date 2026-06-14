"""Knowledge/Memory core (Lớp 1): structured knowledge_items + provenance + revisions.

Tầng tri thức có cấu trúc nuôi từ ingestion. Hybrid model (D1): knowledge_items =
tri thức MỀM (kind nhỏ: decision/fact/note/risk + field), còn task/reminder giữ ở
action_items/scheduled_reminders (typed sẵn có). Provenance trỏ về messages (cho
"ai nói câu đó" + taint chống injection). Revisions = audit append-only + soft-delete
(no silent rewrite — watchlist #1). KHÔNG dùng CHECK trên `kind` để thêm kind sau =
chỉ đổi enum app, không migrate.

Additive, không đụng bảng cũ. Defer (lean): people/aliases, agent_notebook, analytics.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-14
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- knowledge_items: tri thức có cấu trúc (Lớp 1) -----------------------
    op.execute("""
    CREATE TABLE knowledge_items (
      id              BIGSERIAL PRIMARY KEY,
      boss_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      provider        TEXT,                    -- group scope (NULL = boss-level)
      chat_id         TEXT,
      project_id      BIGINT REFERENCES projects(id) ON DELETE SET NULL,
      kind            TEXT NOT NULL,           -- decision|fact|note|risk (validate ở app, KHÔNG CHECK)
      title           TEXT,
      content         TEXT NOT NULL,
      status          TEXT NOT NULL DEFAULT 'active',   -- active|superseded|deleted (soft-delete)
      importance      SMALLINT,                -- LLM 1-10, trọng số xếp hạng (nullable)
      confidence      REAL,                    -- 0..1 (nullable)
      valid_from      TIMESTAMPTZ,             -- temporal validity (cho "đúng gì hồi tháng 3" + recency)
      valid_to        TIMESTAMPTZ,
      qdrant_point_id TEXT,                    -- link vector (NULL tới khi embed)
      meta_json       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- field mở rộng (owner/deadline... promote sau)
      fts             tsvector,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX idx_knowledge_scope "
        "ON knowledge_items(boss_id, provider, chat_id, status)"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_kind "
        "ON knowledge_items(boss_id, kind, status)"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_project "
        "ON knowledge_items(project_id) WHERE project_id IS NOT NULL"
    )
    op.execute("CREATE INDEX idx_knowledge_fts ON knowledge_items USING GIN(fts)")
    op.execute("""
    CREATE OR REPLACE FUNCTION knowledge_items_fts_trigger() RETURNS trigger AS $$
    BEGIN
      NEW.fts := to_tsvector('simple',
        unaccent(coalesce(NEW.title,'') || ' ' || coalesce(NEW.content,'')));
      RETURN NEW;
    END;$$ LANGUAGE plpgsql;
    """)
    op.execute(
        "CREATE TRIGGER trg_knowledge_fts BEFORE INSERT OR UPDATE ON knowledge_items "
        "FOR EACH ROW EXECUTE FUNCTION knowledge_items_fts_trigger()"
    )

    # --- knowledge_provenance: item <- message(s) gốc (many-to-many) ---------
    op.execute("""
    CREATE TABLE knowledge_provenance (
      id                BIGSERIAL PRIMARY KEY,
      knowledge_item_id BIGINT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
      message_id        BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE (knowledge_item_id, message_id)
    )
    """)
    op.execute(
        "CREATE INDEX idx_knowledge_provenance_msg "
        "ON knowledge_provenance(message_id)"
    )

    # --- knowledge_revisions: audit append-only (no silent rewrite) ----------
    op.execute("""
    CREATE TABLE knowledge_revisions (
      id                BIGSERIAL PRIMARY KEY,
      knowledge_item_id BIGINT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
      op                TEXT NOT NULL,           -- add|update|delete|restore
      actor             TEXT NOT NULL,           -- extractor|dreaming|boss|agent
      before_json       JSONB,                   -- snapshot trước (NULL khi add)
      after_json        JSONB,                   -- snapshot sau (NULL khi delete)
      reason            TEXT,                    -- LLM giải thích / message biện minh thay đổi
      source_message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX idx_knowledge_revisions_item "
        "ON knowledge_revisions(knowledge_item_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_revisions CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_provenance CASCADE")
    op.execute("DROP TRIGGER IF EXISTS trg_knowledge_fts ON knowledge_items")
    op.execute("DROP FUNCTION IF EXISTS knowledge_items_fts_trigger()")
    op.execute("DROP TABLE IF EXISTS knowledge_items CASCADE")
