# Platform-Agnostic Channel Layer + Layered Architecture Refactor

**Date:** 2026-04-28
**Status:** Design — awaiting implementation plan
**Author:** Brainstormed with Claude

## Problem

The codebase has three coupled problems:

1. **Channel abstraction is half-applied.** `src/channels/base.py` defines a clean `Messenger` Protocol and `IncomingMessage` event, but core code still imports `from src.services import telegram` everywhere — `agent.py`, `tools/tasks.py`, `tools/group.py`, `tools/communication.py`, `tools/join.py`, `tools/reset.py`, `onboarding.py`. `agent.handle_message` uses Telegram-shaped positional arguments (`chat_id: int, sender_id: int, is_group, bot_mentioned, ...`); the polling bridge in `src/services/telegram.py` destructures `IncomingMessage` back into those args, defeating the abstraction. `main.py` hardcodes `telegram.init_telegram()` + `telegram.start_polling()`.

2. **No layering.** `db.py` is 1,134 lines of flat functions covering messages, bosses, memberships, groups, notes, reminders, token usage, identity. `agent.py` is 695 lines that mix routing (DM vs group, onboarding vs normal), context building, LLM loop, tool dispatch, DB writes, qdrant upserts, and Telegram I/O. Tools mix business logic with direct calls to Lark, DB, qdrant, and Telegram.

3. **No data model for multi-platform.** `chat_id INTEGER` is used as a primary key everywhere. Telegram `123` and Zalo `123` would collide. There is no notion of person identity separate from external chat id.

## Goals

- **Provider-agnostic core.** Adding a new platform = writing one `Messenger` adapter + one capability config + one webhook route (if applicable). No edits to agent, services, repos, or tools.
- **Strict layered architecture** (Controller → Service → Repository / Infrastructure). LLM agent code only calls services. Tools become handler classes that call services.
- **Multi-platform schema.** Synthetic `internal_id` (UUID) for both persons and conversations. External (provider, external_id) maps to internal_id.
- **Explicit DI.** Single `AppContainer` built in FastAPI lifespan; constructor injection everywhere.

## Non-Goals

- Not a domain-driven redesign with aggregate roots / entity classes. Repos still return dicts. Services own business rules.
- Not migrating to a job queue. `asyncio.create_task` for fire-and-forget stays (qdrant upsert, identity harvest).
- Not introducing Pydantic / SQLAlchemy / ORM. SQLite + raw SQL stays.
- Not splitting into multiple processes. Single FastAPI app serves all providers.

## Target Platform Set

| Provider | Runtime mode | Group ops | Proactive window | Notes |
|---|---|---|---|---|
| Telegram | Polling (httpx long-poll) | Yes (admin ops) | Unrestricted | Existing |
| Zalo | Library event loop (zlapi or equivalent) | Yes (personal-account scope) | Unrestricted | NOT Zalo OA bot |
| Messenger (FB) | Webhook | No | 24h reply window | Future |
| WhatsApp Cloud | Webhook | No | 24h reply window | Future |
| Web | WebSocket / SSE | N/A | Unrestricted | Future |

`MessengerCapabilities` already covers per-feature flags. Add `requires_proactive_window: bool` so `MessagingService.can_send_proactive` knows when to check window state.

## Architecture

### Layer breakdown

```
src/
├── channels/                 # INTEGRATION — inbound + outbound messaging adapters
│   ├── base.py               # Messenger Protocol, IncomingMessage, MessengerCapabilities, …
│   ├── telegram.py           # TelegramMessenger (polling)
│   ├── zalo.py               # ZaloMessenger (library event loop)
│   ├── messenger.py          # FB Messenger (webhook)
│   ├── whatsapp.py           # WhatsApp Cloud (webhook)
│   ├── web.py                # Web SSE/WebSocket
│   └── registry.py           # Build messengers from settings
│
├── infrastructure/           # External system clients (HTTP wrappers, no business logic)
│   ├── lark_client.py
│   ├── qdrant_client.py
│   ├── openai_client.py
│   └── cohere_client.py
│
├── repositories/             # SQLite data access — 1 module per aggregate
│   ├── boss_repo.py
│   ├── membership_repo.py
│   ├── message_repo.py       # chat history + outbound DM log
│   ├── group_repo.py
│   ├── note_repo.py
│   ├── reminder_repo.py
│   ├── token_usage_repo.py
│   ├── identity_repo.py      # person external_identity table
│   └── conversation_repo.py  # conversation external_id → internal_chat_id
│
├── services/                 # Domain logic — composition over repos + infrastructure + channels
│   ├── identity_service.py        # resolve_or_create person, lookup_external, harvest
│   ├── conversation_service.py    # resolve conversation internal_id, save_message + embed + qdrant
│   ├── messaging_service.py       # outbound dispatch via correct messenger; can_send_proactive
│   ├── workspace_service.py       # boss / membership / onboarding state
│   ├── person_service.py          # Lark People CRUD + resolve_person + link_contact
│   ├── task_service.py            # Lark + notification + qdrant
│   ├── reminder_service.py        # CRUD + scheduling + render via reminder_agent
│   ├── project_service.py
│   ├── group_service.py           # capability-aware group ops
│   └── context_service.py         # build ChatContext + per-turn LLM context
│
├── agent/                    # LLM-DRIVEN BOT CORE — provider-agnostic
│   ├── prompts.py            # SECRETARY_PROMPT, REMINDER_PROMPT, ADVISOR_PROMPT, ONBOARDING_PROMPT
│   ├── tool_definitions.py   # OpenAI tool schema (data only)
│   ├── tool_dispatcher.py    # tool name → handler class; runs handlers in parallel
│   ├── handlers/             # 1 class per tool — see "Tool handlers" below
│   │   ├── tasks.py          # CreateTaskHandler, ListTasksHandler, …
│   │   ├── people.py
│   │   ├── reminder.py
│   │   ├── group.py
│   │   ├── communication.py
│   │   └── …
│   ├── secretary_agent.py    # main LLM loop (chat_with_tools, MAX_ROUNDS, thinking UX)
│   ├── reminder_agent.py     # LLM-rendered reminder text
│   ├── advisor_agent.py      # strategic advisor LLM
│   └── onboarding_agent.py   # onboarding LLM flow
│
├── controllers/              # ROUTING — entry per source
│   ├── message_router.py     # IncomingMessage → which agent / onboarding / silent index
│   ├── reminder_dispatcher.py    # Scheduler tick → reminder_agent → messaging_service
│   └── webhooks/
│       ├── messenger.py      # FB webhook route + signature verify
│       ├── whatsapp.py       # WhatsApp webhook route + signature verify
│       └── zalo_oa.py        # (only if Zalo OA is added later — Zalo lib doesn't need this)
│
├── utils/                    # Pure helpers — no I/O, no state
│   ├── dates.py              # ms↔date, parse_relative_date ("thứ 6"→YYYY-MM-DD), tz
│   ├── text.py               # full_name, normalize_vi, token_match
│   ├── validation.py         # enum-match (status, priority)
│   └── markdown.py           # safe_markdown_escape, strip_to_plain
│
├── config.py
├── container.py              # AppContainer dataclass + build_container(settings)
└── main.py                   # FastAPI app, lifespan, channel start
```

### Layer rules (strict)

- **Controller** → Service only. Never Repo / Infrastructure / Channel directly.
- **Service** → Repo, Infrastructure, Channel registry, other Service. Never Controller.
- **Repo** → SQLite only. No business logic. No HTTP.
- **Infrastructure** → external system only. No DB. No business logic.
- **Channel** → external messaging API only. Emits `IncomingMessage` → Controller.
- **Agent (LLM)** → Service only. Never Channel, Repo, Infrastructure directly. The "thinking placeholder" UX is just two regular messaging primitives — `MessagingService.send(ctx, text, save_history=False)` returns a message id, `MessagingService.edit(ctx, message_id, text)` updates it. There is no `show_thinking` method; "thinking" is an agent-loop concept, not a domain primitive.
- **Handler (tool)** → Service only. Returns string for LLM.
- **Utils** → no imports from any other layer.

### Mapping from current code

| Current file | Target |
|---|---|
| `src/agent.py` | Split: `controllers/message_router.py` (routing) + `agent/secretary_agent.py` (LLM loop) + `agent/reminder_agent.py` (`send_reminder`) |
| `src/db.py` (1,134 LOC) | Split into ~9 repos by aggregate |
| `src/tools/__init__.py` (1,324 LOC of definitions) | Schema → `agent/tool_definitions.py`; dispatcher → `agent/tool_dispatcher.py` |
| `src/tools/<domain>.py` | Logic → `services/<domain>_service.py`; LLM-facing wrapper → `agent/handlers/<domain>.py` |
| `src/services/telegram.py` | **Delete** |
| `src/services/lark.py` | Rename → `infrastructure/lark_client.py`; pure HTTP only |
| `src/services/qdrant.py` | Rename → `infrastructure/qdrant_client.py` |
| `src/services/cohere.py` | Rename → `infrastructure/cohere_client.py` |
| `src/services/openai_client.py` | Move → `infrastructure/openai_client.py` |
| `src/context.py`, `src/context_builder.py` | Merge → `services/context_service.py` |
| `src/onboarding.py`, `src/group_onboarding.py` | State/persistence → `services/workspace_service.py`; LLM flow → `agent/onboarding_agent.py`; routing → `controllers/message_router.py` |
| `src/identity.py` | → `services/identity_service.py` (uses `repositories/identity_repo.py`) |
| `src/scheduler.py` | Trigger logic → `controllers/reminder_dispatcher.py`; cron mechanics stay |
| `src/advisor.py` | → `agent/advisor_agent.py` |

### Why this layout

- One file per aggregate / domain keeps files small and edits local.
- Channel and Infrastructure are siblings, not parent/child — Lark/Qdrant are not "channels" (no IncomingMessage), but also not domain logic.
- `agent/` and `controllers/` are separate because controllers route inbound events to **either** an agent **or** a non-LLM flow (silent group indexing, onboarding state machine), and there are non-message controllers (scheduler dispatcher).

## Data Model

### Identity

External-id space lives in **two** tables — one for persons, one for conversations:

```sql
-- One row per (provider, external_user_id). Internal id is the canonical reference.
CREATE TABLE external_identity (
    internal_id   TEXT PRIMARY KEY,           -- UUID
    provider      TEXT NOT NULL,              -- 'telegram' | 'zalo' | 'messenger' | …
    external_id   TEXT NOT NULL,
    name          TEXT,
    username      TEXT,
    created_at    INTEGER NOT NULL,
    UNIQUE(provider, external_id)
);

-- One row per (provider, external_chat_id). Conversations are DMs or groups.
CREATE TABLE conversation (
    internal_chat_id  TEXT PRIMARY KEY,       -- UUID
    provider          TEXT NOT NULL,
    external_chat_id  TEXT NOT NULL,
    chat_type         TEXT NOT NULL,          -- 'dm' | 'group'
    title             TEXT,                   -- group name; '' for DM
    created_at        INTEGER NOT NULL,
    UNIQUE(provider, external_chat_id)
);
```

**Cross-platform rule:** same external id on different providers = different person / different conversation. No automatic merging across providers. (Future: explicit `merge_identities(a, b)` when product needs it. Schema is forward-compatible.)

**Schema for tomorrow, logic for today:** `external_identity` has `UNIQUE(provider, external_id)` only — not `UNIQUE(internal_id)`. So a person can later have multiple rows (Telegram + Zalo for same human). Current product behavior treats one external account = one person; the data model does not block future multi-mapping.

**External id type is `TEXT` everywhere.** Telegram supergroup ids today are large negative integers (`-1001234567890`); the migration converts them to strings (`"-1001234567890"`). Zalo / Messenger / WhatsApp ids are non-numeric to start with. Inside the codebase, external ids are always strings — `int(chat_id)` casts disappear.

### Business tables (post-migration)

All FKs are internal ids. No business table carries `provider`.

```sql
-- Examples; not exhaustive
bosses (internal_id PK, name, company, language, lark_base_token, …)
memberships (boss_internal_id, person_internal_id, person_type, name, status)
messages (id PK, internal_chat_id, role, content, sender_internal_id, ts)
groups (internal_chat_id PK, boss_internal_id, project_id, group_note)
outbound_dm_log (id PK, boss_internal_id, to_internal_id, content, trigger_type, ts)
reminders (id PK, boss_internal_id, target_internal_id, …)
```

### Conversion API (`services/identity_service.py`, `services/conversation_service.py`)

Channel adapters call these on every inbound:

```python
# IdentityService
async def resolve_or_create_person(provider: str, external_id: str, name: str = "", username: str = "") -> str: ...
async def lookup_external_for_person(internal_id: str) -> tuple[str, str] | None: ...

# ConversationService
async def resolve_or_create_conversation(provider: str, external_chat_id: str, chat_type: str, title: str = "") -> str: ...
async def lookup_external_for_conversation(internal_chat_id: str) -> tuple[str, str]: ...
```

`IncomingMessage` keeps `channel: str` and string `chat_id` / `sender_id` (provider-native external ids). The **router** (`controllers/message_router.py`) is the boundary that converts external → internal before invoking any service. Services and the agent see only internal ids.

## Channel Layer

### `MessengerCapabilities` additions

`frozen=True` because it's stored inside `ChatContext` (also frozen) and must be hashable. Capabilities are static — set at adapter construction, never mutated at runtime. Rate-limit / per-chat restrictions surface as runtime errors via `[TOOL_ERROR:…]` instead.

```python
@dataclass(frozen=True)
class MessengerCapabilities:
    supports_groups: bool = False
    supports_group_admin: bool = False
    supports_invite_links: bool = False
    supports_edit: bool = True
    supports_delete: bool = True
    supports_typing: bool = True
    supports_photos: bool = True
    supports_files: bool = True
    supports_voice: bool = False
    supports_markdown: bool = True
    requires_proactive_window: bool = False     # NEW — Messenger / WhatsApp / Zalo OA
    proactive_window_hours: int = 0             # NEW — 24 for Messenger / WhatsApp
```

### Per-provider config (initial set)

| Capability | Telegram | Zalo (lib) | Messenger | WhatsApp | Web |
|---|---|---|---|---|---|
| supports_groups | ✓ | ✓ | ✗ | ✗ | ✓ |
| supports_group_admin | ✓ | partial | ✗ | ✗ | ✓ |
| supports_markdown | ✓ | ✗ | ✗ | ✗ | ✓ |
| requires_proactive_window | ✗ | ✗ | ✓ (24h) | ✓ (24h) | ✗ |

### Runtime

`main.py` lifespan:

```python
async def lifespan(_app: FastAPI):
    settings = Settings()
    container = await build_container(settings)

    # Webhook providers register routes (mounted before yield)
    register_webhook_routes(_app, container)

    # Polling / library-event-loop providers spawn background tasks
    bg_tasks = []
    for name, messenger in container.messengers.items():
        if name in ("telegram", "zalo"):                  # event-loop providers
            task = asyncio.create_task(
                messenger.start(container.message_router.handle)
            )
            bg_tasks.append(task)

    await container.scheduler.start(container)            # reminder_dispatcher tick
    yield

    container.scheduler.stop()
    for t in bg_tasks: t.cancel()
    for m in container.messengers.values(): await m.stop()
    await container.db.close()
```

### Webhooks (Messenger / WhatsApp)

Per-provider file under `controllers/webhooks/<provider>.py`. Each owns its signature verification (Messenger HMAC-SHA1, WhatsApp HMAC-SHA256, Zalo OA MAC) and parses payload → `IncomingMessage`, then calls `message_router.handle(incoming)`. Verify token / secrets from `Settings`.

### Proactive-window handling

```python
# MessagingService
async def can_send_proactive(self, internal_id: str) -> bool:
    provider, external_id = await self.identity_service.lookup_external_for_person(internal_id)
    messenger = self.messengers[provider]
    if not messenger.capabilities.requires_proactive_window:
        return True
    last_inbound_ts = await self.message_repo.last_inbound_ts(internal_id, provider)
    if last_inbound_ts is None:
        return False
    age_h = (now() - last_inbound_ts) / 3600
    return age_h < messenger.capabilities.proactive_window_hours
```

When `False`, callers (reminder_service, broadcast handler) decide fallback: skip / queue / notify boss / use template (future work). Service layer owns this decision — channel layer only reports state.

## Wiring (DI)

`AppContainer` is a frozen dataclass built once in `lifespan()`. Constructor injection throughout — every class declares its dependencies in `__init__`.

```python
@dataclass(frozen=True)
class AppContainer:
    settings: Settings

    db: Database
    lark: LarkClient
    qdrant: QdrantClient
    openai: OpenAIClient
    cohere: CohereClient

    boss_repo: BossRepo
    membership_repo: MembershipRepo
    message_repo: MessageRepo
    group_repo: GroupRepo
    note_repo: NoteRepo
    reminder_repo: ReminderRepo
    token_usage_repo: TokenUsageRepo
    identity_repo: IdentityRepo
    conversation_repo: ConversationRepo

    messengers: dict[str, Messenger]                  # keyed by provider name

    identity_service: IdentityService
    conversation_service: ConversationService
    messaging_service: MessagingService
    workspace_service: WorkspaceService
    person_service: PersonService
    task_service: TaskService
    reminder_service: ReminderService
    project_service: ProjectService
    group_service: GroupService
    context_service: ContextService

    secretary_agent: SecretaryAgent
    reminder_agent: ReminderAgent
    advisor_agent: AdvisorAgent
    onboarding_agent: OnboardingAgent

    message_router: MessageRouter
    reminder_dispatcher: ReminderDispatcher
    scheduler: Scheduler
```

`build_container(settings)` constructs in dependency order: **infrastructure → repos → channels → services → agents → controllers → scheduler**. Cycles are prevented by layer rules: controllers depend on agents + services; agents depend on services; services depend on services + repos + channels; no service depends on a controller. Service-to-service dependencies form a DAG with `IdentityService` and `ConversationService` at the root (they have no service deps, only repos), `MessagingService` next (depends on `IdentityService` + channels), and the rest above.

Frozen dataclass + `dict[str, Messenger]`: `frozen=True` prevents reassigning the field but does not freeze the dict's contents — that is intentional. The dict is populated once during `build_container` and never mutated afterward; we rely on convention rather than `MappingProxyType` to keep the wiring code readable.

`ChatContext` is a **pure DTO** (no service references, no messenger) — see below. Services receive `ctx: ChatContext` plus their own dep fields; they never go through `ctx` to reach another service.

## `ChatContext` (post-refactor)

```python
@dataclass(frozen=True)
class ChatContext:
    # Identity (internal ids only)
    sender_internal_id: str
    sender_name: str
    sender_type: str                  # 'boss' | 'member' | 'partner' | 'unknown'
    boss_internal_id: str
    boss_name: str

    # Conversation
    internal_chat_id: str
    is_group: bool
    group_name: str

    # Provider context — needed because tool dispatch + capability checks happen per-turn
    channel: str                      # 'telegram' | 'zalo' | …
    capabilities: MessengerCapabilities

    # Lark workspace pointers
    lark_base_token: str
    lark_table_people: str
    lark_table_tasks: str
    lark_table_projects: str
    lark_table_ideas: str
    lark_table_reminders: str
    lark_table_notes: str

    # Qdrant collection names
    messages_collection: str
    tasks_collection: str

    # Memberships across workspaces (read-only snapshot)
    all_memberships: list[dict] = field(default_factory=list)
```

`ChatContext` is rebuilt per turn by `ContextService.resolve(incoming, container)`. It never carries live references to services or messengers.

## Tool Layer (LLM Handlers)

### Definitions

`agent/tool_definitions.py` is the OpenAI schema **only** — pure data, no logic, no imports from services:

```python
TOOL_DEFINITIONS: list[dict] = [
    {"type": "function", "function": {"name": "create_task", "description": "...", "parameters": {...}}},
    ...
]
```

### Handlers

`agent/handlers/<domain>.py` — one **handler class** per tool. Constructor injection:

```python
class CreateTaskHandler:
    name = "create_task"

    def __init__(self, task_service: TaskService, person_service: PersonService):
        self._tasks = task_service
        self._people = person_service

    async def handle(self, args: dict, ctx: ChatContext) -> str:
        # parse args → call service → format string for LLM
        try:
            task = await self._tasks.create(ctx, **args)
        except DomainError as e:
            return f"[TOOL_ERROR:{e.code}] {e.message}"
        return f"Task '{task.name}' đã tạo, deadline {task.deadline}."
```

### Dispatcher

`agent/tool_dispatcher.py` is a small registry that maps tool name → handler instance:

```python
class ToolDispatcher:
    def __init__(self, handlers: list[ToolHandler]):
        self._by_name = {h.name: h for h in handlers}

    async def execute(self, name: str, args_json: str, ctx: ChatContext) -> str:
        handler = self._by_name.get(name)
        if handler is None:
            return f"[TOOL_ERROR:unknown_tool] {name}"
        try:
            args = json.loads(args_json)
        except json.JSONDecodeError:
            return "[TOOL_ERROR:bad_args]"
        return await handler.handle(args, ctx)
```

`AppContainer` constructs all handlers and assembles them into a `ToolDispatcher` instance.

### Capability handling

LLM sees the **full** tool list every turn (chosen 5c=ii). When a tool unsupported by the current channel is invoked, the handler returns `[TOOL_ERROR:unsupported_on_channel:<feature>]`. The agent prompt instructs the LLM to handle this and fall back / explain to the user. Tradeoff accepted: occasional extra round-trip in exchange for no per-turn schema rebuild and simpler handler design.

## Inbound Flow

```
External event
   ↓
Channel adapter (TelegramMessenger.start loop or POST /webhook/<provider>)
   ↓
IncomingMessage (channel, external chat_id, external sender_id, …)
   ↓
MessageRouter.handle(incoming, container)
   ├── identity_service.resolve_or_create_person(channel, sender.id, …) → sender_internal_id
   ├── conversation_service.resolve_or_create_conversation(channel, chat_id, type, title) → internal_chat_id
   ├── async harvest mentions / reply_to / new_members (fire-and-forget)
   ├── group? not mentioned? → conversation_service.save_message_silently  (return)
   ├── group? not registered? → onboarding_agent.handle_group(…)            (return)
   ├── DM? unknown user? → onboarding_agent.handle_dm(…)                    (return)
   └── workspace_service.resolve_context(...) → ChatContext
        ↓
        secretary_agent.run(ctx, incoming, container)
          ├── context_service.build_turn(ctx, incoming) → messages
          ├── thinking_id = messaging_service.send(ctx, "Đang xử lý…", save_history=False)
          ├── for round in 1..MAX_ROUNDS:
          │     openai.chat_with_tools(messages, TOOL_DEFINITIONS)
          │     if tool_calls: dispatcher.execute() each → append → continue
          │     else: reply = response.content; break
          ├── messaging_service.edit(ctx, thinking_id, reply)
          └── conversation_service.save_assistant_reply(ctx, reply)
```

## Outbound Flow

Any service that wants to send a message goes through `MessagingService`:

```python
# MessagingService
async def send(
    self,
    ctx: ChatContext,
    internal_id: str,                    # recipient — for the current ctx, can pass ctx.internal_chat_id
    text: str,
    *,
    format: str = "markdown",
    save_history: bool = True,           # False for ephemeral "thinking" placeholders
    reply_to: str | None = None,
) -> OutgoingMessage: ...

async def edit(self, ctx: ChatContext, message_id: str, text: str, *, format: str = "markdown") -> None: ...

async def can_send_proactive(self, internal_id: str) -> bool: ...
```

The "thinking placeholder" UX is built from these primitives — `send(..., save_history=False)` to post the placeholder, `edit(...)` to replace with the final reply. There is no `show_thinking` method: the agent loop owns that pattern, the service stays domain-clean.

`MessagingService` looks up `(provider, external_id)` from `IdentityService`, picks `messengers[provider]`, calls its native send. It also writes to `outbound_dm_log` for proactive sends (reminder, broadcast, send_dm tool). Agent never imports a channel.

## Configuration & Deployment

### `Settings` shape (per provider)

Settings grow per provider. Each new platform adds a small block:

```python
class Settings(BaseSettings):
    # Core
    db_path: str
    timezone: str
    openai_api_key: str
    openai_chat_model: str
    openai_embedding_model: str
    qdrant_url: str
    cohere_api_key: str
    lark_app_id: str
    lark_app_secret: str
    recent_messages: int = 20
    rag_messages: int = 8

    # Provider toggles — only enabled providers are constructed
    enabled_providers: list[str] = ["telegram"]      # ["telegram", "zalo", "messenger", "whatsapp", "web"]

    # Telegram
    telegram_bot_token: str = ""

    # Zalo (library-based)
    zalo_session_path: str = "data/zalo_session.json"
    zalo_phone: str = ""
    zalo_password: str = ""             # only used for first-time login; afterwards relies on session

    # Messenger (FB)
    messenger_page_access_token: str = ""
    messenger_app_secret: str = ""      # for HMAC-SHA1 signature verify
    messenger_verify_token: str = ""

    # WhatsApp (Cloud API)
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_secret: str = ""       # for HMAC-SHA256 signature verify
    whatsapp_verify_token: str = ""

    # Web
    web_jwt_secret: str = ""
```

`channels/registry.build_messengers(settings)` reads `enabled_providers` and constructs only those. Disabled providers don't show up in `container.messengers` — `MessagingService` returning `KeyError` is treated as a misconfig (caught and logged).

### Public webhook URL

Webhook providers (Messenger, WhatsApp) need a public HTTPS endpoint. In dev: `ngrok` or equivalent → set provider's webhook URL in their developer console. In prod: domain + reverse proxy (nginx/caddy) → FastAPI app. Document in `README.md` per provider when added.

### Persistent state on disk

- `data/secretary.db` — SQLite (existing).
- `data/zalo_session.json` — Zalo cookie/session, gitignored. If missing or expired, `ZaloMessenger.start` triggers password login (`zalo_phone` + `zalo_password` from settings) then writes the session back.

### Tool-development cost (after refactor)

Adding a new tool requires touching **4 places** vs the current **2**:

| Step | Current | After refactor |
|---|---|---|
| Define schema for LLM | `tools/__init__.py` `TOOL_DEFINITIONS` | `agent/tool_definitions.py` |
| Implement logic | `tools/<x>.py` async function | `services/<x>_service.py` method |
| Wrap for LLM (parse args, format reply) | (inline in tool function) | `agent/handlers/<x>.py` handler class |
| Wire dependencies | (none — module-level singletons) | `container.py` constructs handler with services |

Trade-off accepted: the extra two edits are a one-time per tool and they buy mockability + clear layer separation. Auto-discovery (e.g., decorator-registered handlers) was considered and rejected as too magic for this codebase.

## Forward-Compatibility for Scale

The bot today is **self-hosted, single-tenant**. Some future directions — multi-LLM-provider, per-boss credentials, SaaS multi-tenant operations, observability — are intentionally **not** built now, but the changes that are *expensive to retrofit* (schema columns, boundary abstractions, ID shape) are folded into Phases 3–6 below so adding the visible features later does not require another data migration like Phase 2.

**The rule:** schema + abstraction = land sooner. UI / dashboards / actual provider integrations = defer to demand.

What is folded in:

| Concern | Folded into | Mechanism (default no-op) |
|---|---|---|
| Tenant lifecycle | Phase 3 schema | `bosses.status` (default `'active'`), `plan` (NULL), `expires_at` (NULL) |
| Per-boss LLM keys + model choice | Phase 3 schema | `bosses.llm_provider`, `llm_model`, `llm_api_key_encrypted`, `embedding_provider`, `embedding_model`, `embedding_dim` (all NULL → fall back to `Settings`) |
| Audit trail | Phase 3 schema + Phase 4 service | `audit_log` table; `AuditService.log()` no-op until wired by callers |
| LLM provider abstraction | Phase 4 | `LLMClient` Protocol with one impl (`OpenAILLMClient`); services depend on Protocol |
| Embedding-dim collision (future model swap) | Phase 4 | Qdrant collection name `messages_{boss_uuid}_{embed_dim}`; old collection survives until explicit rebuild |
| Tenant gating + observability | Phase 5 | `MessageRouter` boundary check `if boss.status != 'active'`; `infrastructure/observability.py` (OpenTelemetry tracer + structured logging context) |
| Capability gating per plan | Phase 6 | `BossPolicy.can_use_feature(name)` hook called by services that gate features |

What is **not** folded in (deferred until product needs them):
- Admin UI / dashboard, alerting, billing — front-end of data the schema already exposes.
- Self-serve signup — UI work.
- Real Groq / Gemini / Anthropic adapters — Phase 4 only ships `OpenAILLMClient`; new providers are 1 file each later.
- Suspend / resume admin commands — gated by `status` already; flipping it = future admin endpoint, no schema change.

**Cost of folding:** ~20–30% extra effort on Phases 3–4–5. **Cost of retrofit (avoided):** 1–2 weeks per multi-tenant feature later, like Phase 2 was.

## Phasing (6 PRs)

End-state above is the destination. The migration is split into 6 phases; each phase is a standalone PR that leaves the bot in a working state. Free-hand choice (no production users) means we can break behavior between phases as long as each merges to a green build.

**Ordering principle:** schema migration happens **before** repositories, so repos are written against the final schema once. Doing schema after repos would mean rewriting every repo a second time.

**Phase 1 — Infrastructure + utils carve-out**
- Create `src/utils/` with `dates.py`, `text.py`, `validation.py`, `markdown.py`. Move pure helpers from `tools/tasks.py`, `channels/telegram.py`, `identity.py`. No callers change yet (re-export from old locations until next phase).
- Create `src/infrastructure/`. Move `services/lark.py` → `infrastructure/lark_client.py`, same for qdrant / openai / cohere. Update imports across the codebase.
- Strip business logic from infrastructure clients (none expected — these are already thin HTTP wrappers).
- **Smoke test:** boot bot, send DM, get reply, create one task. Existing behavior unchanged.

**Phase 2 — Schema migration (synthetic internal id)**
- Add `external_identity` and `conversation` tables.
- Write migration script in `scripts/migrate_to_internal_id.py`: assign one UUID per existing person (`bosses.chat_id`, `memberships.chat_id`, harvested `seen_contacts`) and per existing conversation (`groups.chat_id`, every distinct `messages.chat_id`). Populate mapping rows with `provider='telegram'`. Convert all external ids to `TEXT`.
- Rebuild every business table via SQLite copy-pattern (`CREATE TABLE new`, `INSERT … SELECT`, `DROP`, `RENAME`) — `ALTER COLUMN` is not supported. Test on a copy of `data/` before running.
- Existing `db.py` functions are updated to use internal ids in their signatures; the function-style API is preserved (Phase 3 splits into repos).
- The Telegram channel adapter is updated to look up internal ids inline. Temporary — moves to `MessageRouter` in Phase 5.
- **Smoke test:** Phase 1 flows + group registration + reminder firing + onboarding for a fresh boss.

**Phase 3 — Repositories + forward-compat schema**
- Create `src/repositories/` with one module per aggregate. Migrate functions from `db.py` (group by table). Each repo takes `Database` in `__init__`. All methods use internal ids (already done in Phase 2).
- `src/db.py` becomes a thin facade: keeps `get_db()` + delegates remaining function-style calls to repos. Goal: zero behavior change.
- Update direct `db.<func>` callers in tools / agent / onboarding to call repos. Where context-coupling is awkward, leave as `db.<func>` and address in Phase 4.
- **Schema additions (forward-compat, all default-safe):**
  - `bosses.status TEXT DEFAULT 'active'` — values: `'trial' | 'active' | 'suspended' | 'cancelled'`. No code reads it yet (Phase 5 wires the check).
  - `bosses.plan TEXT DEFAULT NULL`, `bosses.expires_at TIMESTAMP DEFAULT NULL` — informational; no enforcement until a future admin layer.
  - `bosses.llm_provider TEXT DEFAULT NULL`, `bosses.llm_model TEXT DEFAULT NULL`, `bosses.llm_api_key_encrypted TEXT DEFAULT NULL`, `bosses.embedding_provider TEXT DEFAULT NULL`, `bosses.embedding_model TEXT DEFAULT NULL`, `bosses.embedding_dim INTEGER DEFAULT NULL` — NULL = fall back to `Settings` (current behaviour).
  - New `audit_log(id PK, actor_internal_id TEXT, action TEXT NOT NULL, target_table TEXT, target_id TEXT, payload_json TEXT, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)`.
  - Encryption: introduce `Settings.boss_credential_encryption_key` (env, Fernet). Helper module `infrastructure/crypto.py` with `encrypt(plain) -> str` / `decrypt(cipher) -> str`. Not used yet; ready when first caller needs it.
- **Smoke test:** same as Phase 2 — no behavior change expected. The new columns / table exist but every code path still reads from `Settings` and skips audit writes.

**Phase 4 — Services + handler classes + tool dispatcher + LLM abstraction**
- Create `src/services/` modules. Port logic from `tools/<x>.py` + `agent.py` reminder/advisor/onboarding helpers into services. Services use repos + infrastructure + channel registry.
- Create `src/agent/handlers/` — one class per tool. Each wraps a service call + formats string for LLM.
- Create `agent/tool_dispatcher.py` (registry, `execute(name, args, ctx)`) and `agent/tool_definitions.py` (data only). The current `agent.execute_tool()` in `tools/__init__.py` is replaced.
- Create `agent/secretary_agent.py`, `agent/reminder_agent.py`, `agent/advisor_agent.py`, `agent/onboarding_agent.py`. LLM loop stays mechanically identical to today; only deps change to constructor injection.
- Delete `tools/` folder once no callers remain.
- **LLM provider abstraction (forward-compat, single impl):**
  - `infrastructure/llm/base.py` — `LLMClient` Protocol: `async chat_with_tools(messages, tools, model, **kwargs)`, `async embed(text) -> tuple[list[float], int]` returning `(vector, dim)`.
  - `infrastructure/llm/openai_client.py` — only impl this phase; thin wrapper around existing `infrastructure/openai_client.py` adapting it to the Protocol.
  - `infrastructure/llm/factory.py` — `get_llm_client(boss: Boss, settings: Settings) -> LLMClient`. Today: always returns `OpenAILLMClient` with key from `boss.llm_api_key_encrypted` (decrypted) if set, else `settings.openai_api_key`. Same lookup for model name. Future Groq/Gemini = add a file + a branch.
  - Services that call LLM accept `LLMClient` via constructor injection — no service imports a concrete provider.
  - `AuditService` interface added (one method: `async log(actor_id, action, target_table, target_id, payload)`). Wired but called from zero places this phase; future admin / boss-DM-trace work calls it.
- **Embedding-dim collision avoidance:** Qdrant collection naming changes from `messages_{boss_uuid}` to `messages_{boss_uuid}_{embed_dim}` (and `tasks_{boss_uuid}_{embed_dim}`). Migration sub-step inside Phase 4: rename existing collections to include the current dim suffix (single Qdrant rename per boss).
- **Smoke test:** end-to-end LLM tool calls — task create + list, reminder create + fire, person resolve, broadcast, group operations. Plus: boot with a boss row that has `llm_api_key_encrypted` set, confirm that key is used (decryption + per-boss client construction works).

**Phase 5 — Controllers + AppContainer + delete telegram shim + observability**
- Create `src/container.py` with `AppContainer` dataclass + `build_container(settings)`. Construction order documented in code comments (infrastructure → repos → channels → services → agents → controllers).
- Create `controllers/message_router.py` with `handle(incoming, container)`. Move routing logic out of `agent.py` (group-not-mentioned, group-not-registered, DM-unknown-user, normal flow). Router is the single boundary that calls `IdentityService.resolve_or_create_person` + `ConversationService.resolve_or_create_conversation`.
- **Tenant lifecycle gate at the router boundary:** after `WorkspaceService.resolve_context`, the router checks `boss.status`. If `'suspended'` or `'cancelled'`, drop silently (or reply with a static "your workspace is paused" message — choice deferred). If `'active'` or `'trial'`, proceed. Single boundary check — no service or tool needs to know about tenant status.
- Refactor `main.py`: call `build_container`, start messengers via the registry. Lifespan loop spawns event-loop providers as background tasks; webhook routes (none yet) registered.
- **Observability scaffold (forward-compat, no external dep yet required):**
  - `infrastructure/observability.py` — context-local logger that injects `boss_internal_id`, `internal_chat_id`, `request_id` (UUID per inbound message) into structured log records. The logger writes to stdout in JSON format if `Settings.log_format == 'json'`, otherwise current human-readable format.
  - OpenTelemetry tracer setup is **optional**: if `OTEL_EXPORTER_OTLP_ENDPOINT` is set in env, install + configure the SDK; otherwise use a no-op tracer. The `MessageRouter.handle` and each `Service` method are wrapped in spans regardless — the no-op tracer makes it free.
  - Shape the API so a Prometheus `/metrics` route can be mounted later as a sibling to `/admin` without touching services.
- **Delete `src/services/telegram.py`** — no caller remains.
- `agent.handle_message` is removed; entry point is `MessageRouter.handle(IncomingMessage)`.
- `ChatContext` is rebuilt as the pure DTO described above.
- **Smoke test:** all previous flows plus routing edge cases — group with bot un-mentioned (silent index), unknown DM (onboarding trigger), reset flow. Plus: flip a boss row to `status='suspended'`, confirm router drops the message.

**Phase 6 — Add Zalo provider + capability-aware messaging + plan policy hook**
- Implement `ZaloMessenger` using chosen library (zlapi or equivalent). Session bootstrap reads cookies from `data/zalo_session.json` (gitignored); relogin path on session expiry.
- `MessengerCapabilities` for Zalo (groups: yes; markdown: no; admin ops: per-library support; `requires_proactive_window=False`).
- Implement `MessagingService.can_send_proactive`. Update `ReminderService` and broadcast handler to call it; log + skip when `False`.
- Add `controllers/webhooks/` skeleton (placeholder for future Messenger / WhatsApp). Not wired this phase.
- **Plan-policy hook (forward-compat, default-allow):**
  - `services/policy.py` — `BossPolicy` with one method: `async can_use_feature(boss: Boss, feature_name: str) -> bool`. Default impl: returns `True` always. Reads `boss.plan` but treats unknown / NULL as unrestricted.
  - Services that gate features call `policy.can_use_feature(boss, '<feature>')` before the work. Initial gating points (each one line, all return `True` today): `MessagingService.broadcast`, `ReminderService.create_reminder`, `TaskService.create_task`. Future tier limits = swap the impl, no new boundary.
- **Smoke test:** boss onboards on Telegram, then on Zalo (different `internal_id` because cross-platform = different person); reminder fires on whichever provider the target is on. Plus: confirm `BossPolicy.can_use_feature` is called from at least one path (log line) — wiring smoke, not behavior smoke.

### Per-phase smoke-test checklist (rationale)

No automated tests survive the refactor. Each phase merges only after running through a manual checklist that exercises the major flows. The checklist is the safety net for Phases 4 and 5 in particular, which reroute everything.

| Flow | What it exercises |
|---|---|
| DM "tạo task X cho Y deadline thứ 6" | tool dispatch, LLM loop, lark write, identity resolve |
| Reminder fires at scheduled time | scheduler, reminder_agent, messaging_service |
| Bot mentioned in unregistered group | group_onboarding flow |
| Reset workspace | reset tool, lark base teardown |
| Boss DMs after fresh install | DM onboarding flow |
| Boss switches from Telegram to Zalo (Phase 6) | identity resolve treats as distinct person |

## Open Questions / Risks

- **Zalo library choice.** zlapi (Python) vs zca-js (Node, would need IPC). Lock before Phase 6 — affects `ZaloMessenger` shape (sync callback wrapping vs subprocess bridge). zca-js requires a separate Node process and message passing (e.g., zeromq or stdin/stdout JSONL); zlapi runs in-process but is less actively maintained.
- **SQLite + UUID migration (Phase 2).** No `ALTER TABLE ALTER COLUMN`. Migration uses copy-table-and-rename. Largest table is `messages` — copy is O(n) but feasible since no prod users. Mitigation: take a `data/secretary.db.backup` before running; migration script must be idempotent (detect already-migrated DB and exit cleanly).
- **`ChatContext.capabilities` snapshot.** Capabilities are static per process. Runtime restrictions (rate limits, per-chat blocks) flow through `[TOOL_ERROR:…]`. Revisit only if a real provider needs dynamic caps.
- **Group identity across providers.** A team using Telegram group + Zalo group for the same project is plausible. Schema supports distinct `internal_chat_id`s; cross-platform group linking is future work and would add a `group_link(internal_chat_id_a, internal_chat_id_b)` table without touching the rest of the schema.
- **Tests.** Existing `tests/` will not survive the refactor (per user signal: tests don't reflect business logic). Plan: write new tests against services in Phase 4 (after services exist) and against repos in Phase 3. Channel adapters tested via `IncomingMessage` parsing fixtures in Phase 6. Smoke-test checklist is the safety net for Phases 4–5.
- **Phase 4 + 5 are the highest-risk phases.** Phase 4 reroutes every tool through new dispatcher + handlers. Phase 5 reroutes every entry point through `MessageRouter`. If a regression slips, the smoke checklist surfaces it; if not, we'll find it later. Budget extra time for these two phases.
- **Multi-provider in `enabled_providers`.** The system serves multiple providers concurrently in one process. Asyncio is single-threaded, so there's no thread safety concern, but a slow webhook can block the loop briefly. If this becomes real, move webhook handlers to use `asyncio.create_task` for the heavy work (router → agent) and ack the webhook immediately.
- **Encryption key rotation (Phase 3).** `boss_credential_encryption_key` is a Fernet key in env. If lost, every encrypted `llm_api_key_encrypted` row becomes unrecoverable — bosses must re-enter keys. If rotated, existing rows must be re-encrypted. We don't build rotation tooling yet; document the constraint in `README.md` when the field is first populated. For self-hosted: just back up the env. For future SaaS: introduce a `key_id` column referencing a separate KMS-managed key.
- **Embedding-dim mismatch on model switch (Phase 4).** Naming Qdrant collections `messages_{boss_uuid}_{embed_dim}` keeps old collection alive when boss changes embedding model — old vectors stay searchable in the old collection until a future "rebuild embeddings" admin action. We do **not** auto-migrate vectors. Acceptable trade-off: search recall on old messages drops temporarily; new messages index fine.
- **OpenTelemetry / Prometheus opt-in (Phase 5).** Spans are always created (no-op tracer when no exporter configured), so production turn-on is just env vars. Concern: span overhead on hot paths. Sample rate config (`Settings.otel_sample_rate`, default 0.1) included from day one.
- **`BossPolicy` default-allow risk (Phase 6).** Until a real plan-tier impl ships, `can_use_feature` returns `True` for everything. This is intentional but means a future tightening (e.g., adding a `'free'` tier with reminder cap) would silently start denying — needs a release note. Mitigation: log every call at DEBUG level so it's visible when behavior changes.
- **Audit log volume (Phase 3 schema, Phase 4 service).** Wired but not called this round. When callers light up, `audit_log` will grow unbounded. Add a retention sweeper before turning on heavy audit writes (90-day default). Out of scope for the 6 phases.
- **Self-hosted vs. SaaS tension.** The forward-compat layer adds ~20–30% per phase 3–6. If product direction settles on "self-hosted only forever", these are dead weight. If product moves toward SaaS, retrofit cost would have been multiples of this. Accept the bet because the schema additions are default-no-op (zero behaviour change) and the abstractions stay one-impl until a second is needed.
