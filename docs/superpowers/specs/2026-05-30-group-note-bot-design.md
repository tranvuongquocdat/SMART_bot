# Group Note Bot — Design Spec (Draft v1, Đợt 1)

**Status:** Draft · Đợt 1 of 2 (Product · Architecture · Identity · Group Note · Capture)
**Created:** 2026-05-30
**Branch:** `main` (rebuild, post-collapse)
**Reference (legacy code):** `git show archive/legacy:<path>`

## How to read this document

This is the first half of the design spec. Đợt 2 will cover Agent layer, LLM
abstraction, Plugin architecture, Web admin, Tech stack, and consolidated open
questions.

**Iteration:**
- Read each section. Reply per section.
- Phrases: `section X: <change>` · `section X expand` · `section X looks good` · `Đợt 1 OK`.
- Sections marked **(open)** carry unresolved decisions surfaced inline.
- When Đợt 1 is approved, I write Đợt 2. When the full spec is approved, we
  invoke `writing-plans` to generate the implementation plan.

## Contents

1. Product Vision & Scope
2. Architecture Overview
3. Identity & Channel Linking
4. Group Note (Core Artifact)
5. Capture Flow & Data Model

Sections 6–11 in Đợt 2.

---

## 1. Product Vision & Scope

### 1.1 Problem statement

Vietnamese SME bosses ("sếp") live inside chat — Zalo primary, Telegram
secondary. They manage multiple group chats (sales, marketing, tech,
partners). They:

- Miss decisions buried in long threads.
- Forget what was agreed last week.
- Don't know what action items are open across groups.
- Can't easily find "who said what about X" weeks ago.
- Spend mornings scrolling.

Existing tools (Asana, Notion, Slack AI, Otter) don't fit: they require
migrating off Zalo, target English-first desktop users, or are too
generic/heavy.

### 1.2 Target user

Primary persona — Vietnamese SME owner / team leader who:

- Uses Zalo for >80% of work communication
- Manages 3–15 group chats
- Has 5–50 employees / partners
- Is non-technical (won't paste API keys without a UI guiding them)
- Pays VND, prefers bank transfer over card

Secondary user — employees of the sếp. They interact with the bot **only**
in groups where their sếp is present. They cannot DM the bot or own
configuration. This sidesteps the entire identity-resolution problem.

### 1.3 Product anchor — the "group note"

The bot's primary artifact is a **living document per group chat**. Each
group has ONE markdown note that is auto-updated from conversation,
manually editable, and the source of truth for every other op:

- Summaries → re-emit the note
- Q&A → search the note + raw history
- Action items → extracted view of the note's "Việc đang mở" section
- Cross-group digest (deferred) → roll-up of all notes for one sếp

This collapses many features into one persistent artifact: **1 group = 1
always-updated note**.

### 1.4 MVP scope (Phase 0)

| Layer | Capability |
|---|---|
| **Capture** | All messages in any group where the linked sếp is a member. Raw text + sender display name. |
| **Group note** | One markdown note per group, 7 sections (§4.2). Auto-update on debounce + threshold. User-editable on web. |
| **In-group ops** | `@bot summarize` / `@bot refresh note` · `@bot Q&A` over note + history · auto action-item detection embedded in note |
| **DM with sếp** | Cross-group Q&A · "tóm tắt group X tuần này" · list open action items · No scheduled push. |
| **Web (user)** | 8-section sidebar (Dashboard, Groups, Action Items, Digests-disabled, Channels, Plugins, Usage, Settings). See Đợt 2 §9. |
| **Web (super)** | 3 pages — Bosses, Payments, Revenue. Role-gated via env var. |
| **Channel** | Zalo (priority) + Telegram. Lark Messenger deferred. |
| **AI** | Provider abstraction (OpenAI / Groq / Anthropic / Gemini / Custom). 2-tier fast/smart. BYO key. |
| **Plugins** | Architecture wired; **0 plugins ship.** |
| **DB** | PostgreSQL + Qdrant. |
| **Auth (user)** | Google OAuth + email/password fallback. |
| **Auth (channel)** | Deep-link linking via DM `/start <token>`. |
| **Subscription** | Manual: VietQR display + admin marks paid in superadmin. |

### 1.5 Deferred (Phase 1+)

- Daily digest DM (toggleable + scheduled)
- Stalled-work alerts
- **Media ingest beyond text** — decision in §1.7
- Plugins shipped: Google Calendar, Lark Base
- Lark Messenger channel
- Auto-detect payment (Casso/SePay webhook)
- People insights, mood analytics
- Multi-currency, international subscription

### 1.6 Non-goals

- We do not build a billing engine. Sếp pays via bank transfer; we mark
  paid in admin. No Stripe, no auto-invoice.
- We do not build cross-channel identity resolution. "Anh Tân" stays as
  display text — no map to a `user_id`.
- We do not DM employees. The bot only DMs the linked sếp.
- We do not offer self-hosted single-tenant. Multi-tenant from day 1.

### 1.7 Open

- **(open) Media ingest in MVP** — see §5.4 for the A / B / C
  trade-off. Recommendation: B (URL + voice transcribe).

---

## 2. Architecture Overview

### 2.1 Component layers

```
┌─────────────────────────────────────────────────────────────────┐
│              Channels (inbound + outbound)                      │
│  ┌──────────┐  ┌─────────────┐  ┌──────────────────┐            │
│  │  Zalo    │  │  Telegram   │  │  Lark Messenger  │ (deferred) │
│  │  OA SDK  │  │  Bot SDK    │  │  (Phase 1)       │            │
│  └────┬─────┘  └──────┬──────┘  └────────┬─────────┘            │
└───────┼───────────────┼──────────────────┼──────────────────────┘
        ▼               ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Channel Router                            │
│   Normalises inbound events → InboundMessage                   │
│   Resolves sender boss_id via account_links                    │
│   Drops if no linked boss is a member of the chat              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Capture & Indexing                          │
│   • messages table (PostgreSQL)                                │
│   • FTS tsvector index (unaccent + simple)                     │
│   • Qdrant vector store (semantic) — async upsert              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Layer                               │
│   (Đợt 2 §6)                                                    │
│                                                                 │
│   Operations:                                                   │
│     - GroupNoteUpdater  (debounce/threshold)                   │
│     - InGroupResponder  (@bot mention)                          │
│     - DMResponder       (sếp DM)                                │
│                                                                 │
│   Tools:                                                        │
│     - core: search_history, refresh_note, edit_note, ...       │
│     - plugin: dynamically loaded per boss                      │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LLM Abstraction                           │
│   (Đợt 2 §7)                                                    │
│                                                                 │
│   Provider clients (1 file each):                              │
│     - OpenAICompatibleClient (OpenAI, Groq, OpenRouter, …)     │
│     - AnthropicClient                                          │
│     - GeminiClient                                             │
│                                                                 │
│   ModelRegistry: name → capabilities, cost, tier               │
│   Router: pick(boss_config, op_type) → (provider, model)       │
└─────────────────────────────────────────────────────────────────┘

  Side surfaces
  ─────────────

┌─────────────────────────────────────────────────────────────────┐
│                       Web Application                           │
│   (Đợt 2 §9)                                                    │
│                                                                 │
│   - User pages: Dashboard, Groups, Notes, Channels, ...        │
│   - Superadmin pages: Bosses, Payments, Revenue                │
│   - OAuth callback (Google login, plugin OAuth)                │
│   - Channel linking endpoint (deep-link tokens)                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       Scheduler                                 │
│                                                                 │
│   - Note debounce flush                                        │
│   - Subscription expiry checks                                 │
│   - (Phase 1) Daily digest send                                │
│   - (Phase 1) Stalled-work alerts                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data flow — happy paths

**Passive capture** (every inbound message):

```
Channel webhook
   ▼
Channel adapter normalises
   ▼
Router lookups account_links → boss_id   (if none → drop)
   ▼
messages INSERT  (Postgres + FTS index + Qdrant upsert async)
   ▼
NoteUpdater.schedule(boss_id, chat_id)   (debounce 10 min, threshold 30 msg)
   ▼
LLM (smart tier) rebuilds group_note markdown
   ▼
group_notes UPDATE + group_note_versions INSERT
```

**On-demand op** (`@bot` mention in group):

```
Tagged message → router → boss_id resolved
   ▼
Agent.handle(InGroupResponder)
   ▼     tools = core + enabled plugins for boss
         context = current group_note + recent messages (capped)
LLM (smart for reasoning ops, fast for short ack ops)
   ▼
Outbound: reply in same group
   ▼
outbound_messages INSERT
```

### 2.3 Tenant model

- Multi-tenant from day 1. One server process, N bosses.
- Every domain table has `boss_id`. Every query filters by `boss_id` at
  the repository layer. No PG row-level-security (kept simple, enforced
  in code).
- Cross-boss objects: `users` (which contains superadmin), platform-wide
  configs (LLM defaults, plugin manifests).

### 2.4 Runtime topology

```
┌─────────────────────────────────────────────────┐
│ Single FastAPI app (one Python process)         │
│                                                 │
│ Routers:                                        │
│   /api/channels/zalo/webhook                    │
│   /api/channels/telegram/webhook                │
│   /api/oauth/google/callback                    │
│   /api/oauth/plugin/<name>/callback             │
│   /admin/*  (role-gated)                        │
│   /app/*   (user pages)                         │
│                                                 │
│ Background tasks (asyncio):                     │
│   - NoteUpdater queue worker                    │
│   - Subscription expiry checker (daily)         │
│   - (Phase 1) digest scheduler                  │
└─────────────────────────────────────────────────┘
       │
       ├─ Postgres  (asyncpg)
       ├─ Qdrant    (HTTP)
       └─ External LLM APIs
```

Single process keeps deploy simple. If scale demands, NoteUpdater lifts
to a separate worker process trivially (its inputs are message events).

### 2.5 Open

- **(open) Single-process vs split web/worker** — single is fine for first
  ~50 bosses. Split deferred until LLM calls saturate request handling.

---

## 3. Identity & Channel Linking

### 3.1 Web account (boss → users)

- Sếp signs up via Google OAuth (primary) or email/password (fallback).
- One `users` row per sếp. Stores: id, email, name, google_sub,
  password_hash (nullable), role, subscription_status, subscription_plan,
  subscription_expiry.
- `role ∈ {boss, superadmin}`. Superadmin auto-set when email matches
  `SUPERADMIN_EMAILS` env var at login.

### 3.2 Channel linking via deep-link

Bot is platform-owned (1 Zalo OA, 1 Telegram bot, 1 Lark app). Each boss
links their channel identity via DM-deep-link:

```
Web (logged-in sếp):
  Click [Connect Zalo] on /channels page
     │
     ▼  server generates token (16 url-safe bytes), TTL 10 min
     │  stores in linking_tokens
     │
     ▼  redirect to deep-link:
        https://zalo.me/<OA_ID>?param=<token>            (Zalo)
        https://t.me/<BOT_USERNAME>?start=<token>        (Telegram)

Sếp's phone:
  Zalo/Telegram opens chat with our bot.
  Pre-populates "/start <token>" — sếp taps send.
     │
     ▼  bot receives DM
     │  parses token from payload
     │  looks up linking_tokens → boss_id
     │  INSERT into account_links (boss_id, provider, provider_user_id, linked_at)
     │  DELETE the token row
     │  replies "✓ Đã kết nối Zalo. Em là bot của anh ở đây."

Web (auto-refresh):
  Channels page shows: Zalo ✓ Connected
```

### 3.3 Schema

```sql
account_links (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT    NOT NULL,                  -- 'zalo' | 'telegram' | 'lark_msg'
  provider_user_id TEXT    NOT NULL,
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX idx_account_links_boss ON account_links(boss_id);

linking_tokens (
  token       TEXT PRIMARY KEY,
  boss_id     INTEGER NOT NULL REFERENCES users(id),
  provider    TEXT NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at);
```

### 3.4 Group membership detection

When a message arrives from a group chat:

```python
# Pseudo
async def resolve_group_owner(chat_id, provider):
    member_ids = await channel.list_members(chat_id)
    if not member_ids:
        # Lazy fallback if channel API restricts membership read:
        member_ids = await message_repo.distinct_senders(chat_id, days=30)
    rows = await db.fetch(
        "SELECT boss_id FROM account_links "
        "WHERE provider = $1 AND provider_user_id = ANY($2)",
        provider, member_ids,
    )
    return [r["boss_id"] for r in rows]
```

If no linked boss in chat → bot drops the event silently (no reply, no
capture).

### 3.5 Multi-boss in same group (edge case)

If two linked bosses are in the same group, both should see the group in
their respective dashboards.

- `group_notes` is keyed by `(boss_id, provider, chat_id)` — same group
  renders as TWO notes (one per boss), each owned and edited independently.
- Bot replies in the group once. Attribution: whichever boss `@bot`
  mentioned; on bare mention, the older-linked boss.

### 3.6 Open

- **(open) Multi-boss UX: split vs dedupe.** Split is simpler (each boss's
  experience is independent). Listed for Đợt 2.

---

## 4. Group Note (Core Artifact)

### 4.1 Why one note per group

Without a persistent artifact, every Q&A starts from raw messages →
expensive context, inconsistent answers. With a rolling note:

- Decision history is preserved (not lost in scroll-back).
- Action items have a single home.
- LLM Q&A context shrinks from ~50k tokens of raw chat to ~1k tokens of
  current note + relevant retrieval.
- Sếp has a UI to read: "the state of this group" in one screen.

### 4.2 Section schema (7 fixed sections)

Sections without content are hidden on render. Headers are templated by
code; the LLM fills sections.

```markdown
# {group_name}
Last updated: {iso_timestamp} · {msg_count_7d}/day · status: {emoji}

## ⚡ Cần sếp xử lý          (hide if empty)
- short bullets that explicitly need the boss's action

## 📌 Đang focus              (3–5 bullets max)
- what the group is actively working on right now

## ✅ Việc đang mở            (task list with owner + deadline)
- [ ] {person} — {task} · {deadline_or_open}
- ⚠ {person} — {task} · OVERDUE {Nd}

## 🚧 Đang tắc / Rủi ro      (hide if empty)
- blockers, stalled work, risks

## 📜 Đã quyết                (decisions log, append-only)
- {decision} ({attributed_to}, {date})

## 💬 Câu hỏi treo            (hide if empty)
- open questions visible to the team

## 👥 Người active (7d)
- {name} ({count}) · ...

## 📦 Lưu trữ
- [{period}](archive link)
```

**Design rules:**
- Exceptions first (⚡, 🚧). Boss scans top.
- Persistent value below. `📜 Đã quyết` is append-only history.
- LLM never deletes from `📜 Đã quyết`. Manual edit only.
- `👥 Người active` is computed from message counts, not LLM-inferred.

### 4.3 Update lifecycle

Three triggers (any of which queues an update):

| Trigger | When | Why |
|---|---|---|
| **Debounce 10 min** | Group has had a message in the last X minutes; X has elapsed since the last new message | Conversation has settled |
| **Threshold 30 msg** | 30 messages have arrived since the last note update | Don't wait too long for active groups |
| **On-demand** | `@bot refresh note` in group, or web "Refresh" button | User control |

Update procedure:

```
1. Acquire lock (boss_id, chat_id)   (asyncio.Lock for MVP)
2. Load current group_note.content
3. Load new messages since group_note.last_seen_message_id
4. Build LLM prompt:
   - System: "Update the group note. Preserve sections X, Y as-is
              (manually edited). Update only D, E, F, G.
              Preserve '📜 Đã quyết' as append-only."
   - Input: current note + delta messages
5. LLM (smart tier) emits new markdown
6. Validate: all 7 section headers present (renderer hides empties)
7. UPDATE group_notes SET content, last_seen_message_id, updated_at
   INSERT INTO group_note_versions for history
8. Release lock
```

### 4.4 Manual edits & conflict resolution

Web UI shows the note in a markdown editor. Sếp clicks "Edit", saves.

To prevent the next auto-update from overwriting manual changes:

- On save, record `manually_edited_sections` (set of header names whose
  content differs from the LLM's last-emitted version).
- On next auto-update, LLM is instructed: "Sections {A, B, C} were
  manually edited and must be preserved as-is. Update only {D, E, F, G}."
- Per-section granularity, not per-line. A `Let bot manage this section
  again` toggle clears the flag for that section.

`group_notes.manually_edited_sections` is a JSONB array of section
header strings.

### 4.5 Versioning & archive

- Every update inserts a row into `group_note_versions`. ~few kB each.
- Web shows version timeline with diff view.
- After 30 days, old versions compact to: 50 most recent + monthly
  snapshot rows.

### 4.6 Storage schema

```sql
group_notes (
  id                         BIGSERIAL PRIMARY KEY,
  boss_id                    INTEGER NOT NULL REFERENCES users(id),
  provider                   TEXT NOT NULL,
  chat_id                    TEXT NOT NULL,
  group_name                 TEXT,
  content                    TEXT NOT NULL DEFAULT '',
  manually_edited_sections   JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_seen_message_id       BIGINT,
  status                     TEXT NOT NULL DEFAULT 'active',  -- active | quiet | stalled
  msg_count_7d               INTEGER NOT NULL DEFAULT 0,
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, provider, chat_id)
);
CREATE INDEX idx_group_notes_boss ON group_notes(boss_id);

group_note_versions (
  id            BIGSERIAL PRIMARY KEY,
  group_note_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  content       TEXT NOT NULL,
  emitted_by    TEXT NOT NULL,  -- 'llm' | 'user'
  emitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_group_note_versions_note ON group_note_versions(group_note_id, emitted_at DESC);
```

### 4.7 Open

- **(open) Section schema fixed vs configurable per boss.** Fixed for MVP.
  Configurable adds prompt-template parameterisation. Listed for Đợt 2.

---

## 5. Capture Flow & Data Model

### 5.1 Inbound message pipeline

```
Channel webhook
   ▼
Channel adapter parses platform event → InboundMessage
   ▼
Router resolves boss_id via account_links
   │   if no linked boss in chat → drop silently
   ▼
Persist:
  1. INSERT INTO messages
  2. tsvector auto-built (Postgres TRIGGER)
  3. EMBED + UPSERT to Qdrant   (async, doesn't block webhook ack)
   ▼
Schedule NoteUpdater for (boss_id, chat_id)
   ▼
Return 200 OK to channel webhook
```

Embedding is async because it adds 100–500ms latency and shouldn't block
webhook acks (channels retry on slow responses).

### 5.2 `messages` schema

```sql
messages (
  id                 BIGSERIAL PRIMARY KEY,
  boss_id            INTEGER NOT NULL REFERENCES users(id),
  provider           TEXT NOT NULL,
  chat_id            TEXT NOT NULL,
  chat_type          TEXT NOT NULL,        -- 'group' | 'dm'

  provider_msg_id    TEXT,                 -- platform's msg id, for dedup
  reply_to_msg_id    BIGINT REFERENCES messages(id),

  sender_provider_id TEXT,                 -- platform user id
  sender_name        TEXT,                 -- display name (no resolution!)

  text               TEXT,                 -- raw text body
  media_kind         TEXT,                 -- NULL | 'voice' | 'image' | 'file' | 'sticker' | 'url'
  media_url          TEXT,                 -- where to fetch
  media_text         TEXT,                 -- extracted text (transcript, OCR, fetched body)

  ts                 TIMESTAMPTZ NOT NULL, -- platform timestamp
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  fts                tsvector,             -- updated by trigger

  UNIQUE (provider, chat_id, provider_msg_id)
);
CREATE INDEX idx_messages_chat ON messages(boss_id, provider, chat_id, ts DESC);
CREATE INDEX idx_messages_fts ON messages USING GIN(fts);
```

**Notes:**
- `media_text` is the searchable text equivalent of media. Voice →
  transcript. URL → fetched article body. Image → OCR (Phase 1). FTS
  indexes both `text` and `media_text`.
- `sender_name` is the display name **at capture time**. No lookup, no
  normalisation. Explicit "no identity resolution" choice.
- Dedup via `UNIQUE(provider, chat_id, provider_msg_id)` so channel
  retries are idempotent.

### 5.3 Indexing: FTS + Qdrant

**Postgres FTS:**
- Used for keyword lookups ("did anyone say X").
- Vietnamese: `simple` config + `unaccent` extension + `pg_trgm` for
  diacritic-insensitive matching.
- Indexes `text` and `media_text`.

**Qdrant:**
- **Single collection**, `boss_id` in payload filter. Avoids
  N-collection management overhead. Boss-filter is fast.
- Embedding: `text-embedding-3-small` (1536 dims) for MVP. Switchable
  via the LLM-abstraction layer in Đợt 2.
- Granularity: **per-message** for MVP. Most Zalo messages are short.
  Paragraph chunking deferred.
- Payload: `{boss_id, provider, chat_id, ts, sender_name}` for
  filterable retrieval.

**Hybrid retrieval (Q&A):**
```
1. FTS pre-filter (boss_id, chat_id?, optional date range) → ≤500 candidates
2. Vector rank top-20 of those (Qdrant with payload filter)
3. Pass to LLM together with current group_note
```

### 5.4 Media handling — open decision

| Option | What lands in MVP | Effort | Risk if we skip |
|---|---|---|---|
| **A. Text only** | Voice / image / file / URL stored as `media_kind` + `media_url`; `media_text` empty. Note ignores. | 0 | Note misses ~30–50% of group content for typical Zalo SME. |
| **B. URL fetch + voice transcribe** | `media_text` populated for URL (fetched body) and voice (Whisper-style transcribe). Note covers their content. | +2 weeks | Image OCR + file extract still missing — smaller gap. |
| **C. Full media ingest** | A + B + image OCR + PDF/docx extract. | +4 weeks | Slow ship. |

Recommendation: **B**. Voice-heavy Zalo reality justifies the cost.
Image / file in Phase 1.

### 5.5 Retention & privacy

**MVP policy:**
- `messages`: retained indefinitely while subscription active.
- On subscription expiry: bot stops capturing (channel webhook drops).
  Existing data retained 90 days; then a "delete or export" prompt is
  shown on web; default action after 30 days post-prompt is delete.
- `group_note_versions` older than 30 days are compacted: 50 most recent
  + monthly snapshots.
- No analytics dataset is shared off-platform. No third-party
  content telemetry.

**Per-boss data export (Phase 1):** Web button "Download my data" → ZIP
of messages + notes as markdown. Trust feature.

### 5.6 Outbound message logging

```sql
outbound_messages (
  id                  BIGSERIAL PRIMARY KEY,
  boss_id             INTEGER NOT NULL REFERENCES users(id),
  provider            TEXT NOT NULL,
  chat_id             TEXT NOT NULL,
  reply_to_message_id BIGINT REFERENCES messages(id),
  content             TEXT NOT NULL,
  trigger             TEXT NOT NULL,        -- 'mention' | 'dm' | 'scheduled' | 'system'
  sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status              TEXT NOT NULL,        -- 'sent' | 'failed'
  error               TEXT
);
```

Used for debugging, observability, audit ("did the bot actually reply?"),
and future digest construction.

### 5.7 Open

- **(open) Voice transcription** — API (OpenAI/Groq Whisper) vs own
  (whisper.cpp). API for MVP; own for Phase 2 if cost matters.
- **(open) Image OCR** — deferred to Phase 1.
- **(open) GDPR-style right-to-be-forgotten for individuals** — defer.

---

## Đợt 2 preview

Coming after Đợt 1 is approved:

- §6 Agent layer — operation routing, tool calling chain, **multi-agent
  decision**, context window management
- §7 LLM abstraction — provider clients, ModelRegistry, 2-tier routing,
  capability gap fallback
- §8 Plugin architecture — manifest format, OAuth flow, settings auto-render
- §9 Web admin — user pages + superadmin pages, auth, channels wizard
- §10 Tech stack & infra — PG + Qdrant + FastAPI + HTMX, Docker, env,
  observability
- §11 Consolidated open questions
