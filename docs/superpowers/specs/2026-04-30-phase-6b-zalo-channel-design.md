# Phase 6b — Zalo Channel via zca-js Node Bridge

**Status:** Spec — ready for plan.
**Date:** 2026-04-30.
**Predecessor:** `2026-04-28-platform-channel-and-layered-architecture-design.md` (Phase 6 placeholder for Zalo). Probe results in `docs/zalo-probe-findings.md` (verdict GREEN). Operational lessons folded in from `reference for SMART/ZaloCRM/backend/src/modules/zalo/`.

---

## 1. Background

The Phase 6 design originally called for a Zalo channel using the Python `zlapi` library. Hands-on review revealed `zlapi` only supports phone+password login, which Zalo's risk model flags as bot behaviour and blocks within hours. The community-maintained Node library `zca-js` (v2.x) supports the same QR-login path the official Zalo Web client uses, and is what the team's reference implementation runs on.

The probe (now at `src/channels/zalo_bridge/{login,bridge}.js`) validated end-to-end:
- QR login (`event.data.image` = base64 PNG) with persisted session.
- Listener event shapes for DM/group, photo, mention, reply, forward.
- Outbound `sendMessage` to a group.

Phase 6b therefore ships a Python ↔ Node subprocess bridge instead of a pure-Python integration, with operational hardening borrowed from the reference implementation (which runs zca-js in production).

---

## 2. Goals & Non-Goals

**Goals:**
1. `ZaloMessenger` satisfies the existing `Messenger` protocol so `MessageRouter` and `AppContainer` see no special case.
2. Run zca-js as a long-running Node child per **Zalo account** (not per boss), with structured JSONL RPC.
3. Support multi-tenancy: 1 Zalo account can serve N bosses (e.g. shared bot account for 3 directors). Self-host = degenerate case (N = 1).
4. Throttle outbound to stay below Zalo's heuristic anti-spam thresholds. Throttle logic is **scoped to the Zalo channel**, not generalized.
5. Persist session credentials encrypted at rest; offer a CLI for first-time QR scan and re-login.
6. Operational hardening: circuit breaker, health check, daily session refresh, status enum, retry-on-close, user-info cache, undo handling.

**Non-Goals:**
1. Multi-account-per-process. One bridge process = one Zalo account. N accounts = N processes.
2. Inline buttons, cards, payments. Use plain text + numbered prompts ("1. Có / 2. Không") as fallback.
3. Generalizing the rate limiter for Messenger / WhatsApp. Each platform has a fundamentally different limit model and gets its own implementation when added.
4. Zalo OA (Official Account) — separate provider, separate codepath; documented as forward path in §11, not built now.
5. Cold-start bot account hardening (account warm-up). Documented as operational requirement, not code.
6. Admin web UI for Zalo account management. CLI suffices for self-host; web UI is Phase 6c+.

---

## 3. Architecture

### 3.1 Account-centric model

The Zalo account is a 1st-class entity, distinct from the boss. **Bosses link to accounts (N:1)** — multiple bosses can share one bot account when the operator wants to consolidate.

```
ZaloAccount (own table, own session, own bridge process)
   ↑ N:1
Boss (boss.default_zalo_account_id → which account sends proactive messages for this boss)
```

Inbound routing identifies the boss via `(account_id, sender_zalo_uid)` → `external_identity(provider="zalo", external_id=sender_uid)` → person → boss. This is identical to the Telegram pattern (one bot token, many users distinguished by sender id) — the identity layer already handles it without changes.

Outbound proactive messages (e.g. reminder fire) look up `boss.default_zalo_account_id` and send via that account's bridge.

### 3.2 Process topology

```
Python main process
├── AppContainer
│   ├── messengers["telegram"] = TelegramMessenger              ← existing
│   ├── messengers["zalo:account:<account_id_A>"] = ZaloMessenger
│   │     └── ZaloBridgeProcess  ─►  Node child (`bridge.js`)
│   ├── messengers["zalo:account:<account_id_B>"] = ZaloMessenger
│   │     └── ZaloBridgeProcess  ─►  Node child (`bridge.js`)
│   └── ...
└── ZaloAccountManager (helper around messengers["zalo:account:*"])
      ├── get_for_boss(boss_id) → ZaloMessenger via boss.default_zalo_account_id
      └── get_for_account(account_id) → ZaloMessenger
```

- One Node child per Zalo account (not per boss).
- Python owns the lifecycle: spawn on container build (for accounts in `connected` or `connecting` state at last shutdown), graceful shutdown via RPC `shutdown` then SIGTERM.
- Stderr forwarded to Python logger as `zalo.bridge.<account_id>` records (metadata only — no message content).

### 3.3 Code layout

```
src/channels/
├── telegram_singleton.py              ← existing
├── zalo.py                            ← NEW: ZaloMessenger + ZaloAccountManager
└── zalo_bridge/                       ← NEW: bridge subpackage
    ├── __init__.py
    ├── bridge.js                      ← long-running Node script
    ├── package.json                   ← zca-js dep, pinned version
    ├── process.py                     ← ZaloBridgeProcess (subprocess + JSONL)
    ├── rate_limiter.py                ← Zalo-scoped, account-keyed
    └── protocol.py                    ← typed dataclasses for RPC payloads

src/repositories/
└── zalo_account_repository.py         ← NEW: CRUD for zalo_account table

src/cli/
└── zalo_login.py                      ← NEW: QR onboarding CLI

src/infrastructure/scheduler/          (existing)
└── zalo_jobs.py                       ← NEW: health check + daily refresh cron

src/controllers/webhooks/              (deferred from Phase 5; skeleton only)
└── README.md                          ← document this is where Zalo OA inbound will land later
```

The `zalo_bridge/` directory is self-contained: owns its own Node code, its own throttling, its own protocol types. Nothing outside `channels/` imports from it directly.

### 3.4 RPC Protocol (JSONL over stdio)

**Framing.** One JSON object per line, UTF-8, terminated with `\n`. The bridge buffers stdin until newline, then parses.

**Bridge identity.** The bridge process is started with `--account-id <uuid>` so every event/log carries it. Python doesn't pass `account_id` in commands (the bridge already knows it).

**Commands (Python → Node):**

| Method | Params | Result |
|---|---|---|
| `login_qr` | `{}` | `{"own_id": str, "session": {...}}` after `login_complete` event fires |
| `login_session` | `{cookie, imei, userAgent}` | `{"own_id": str}` |
| `get_own_id` | `{}` | `{"own_id": str}` |
| `set_typing` | `{thread_id, thread_type}` | `{"ok": true}` |
| `send` | `{thread_id, thread_type, text, mentions?, quote_msg_id?}` | `{"msg_id": str \| null, "ts_ms": int}` |
| `fetch_groups` | `{}` | `{"groups": [{id, name, member_count}]}` |
| `fetch_group_info` | `{group_id}` | `{name, members: [{uid, role}], admins: [uid]}` |
| `fetch_user_info` | `{uid}` | `{zalo_name, avatar, phone?}` (uses bridge's 5-min cache; see §6.4) |
| `shutdown` | `{}` | `{"ok": true}` then process exits |

Every command has an `id` (Python-assigned monotonic int). Replies carry the same `id` plus exactly one of `result` or `error`.

**Errors:** `{"id": N, "error": {"code": str, "message": str, "retriable": bool}}`. Codes: `not_logged_in`, `send_failed`, `rate_limited`, `unknown_thread`, `internal`. `retriable` is informational only — Python applies at-most-once policy regardless (§6.5).

**Events (Node → Python, no `id`, all carry the bridge's `account_id` implicitly via process identity):**

| Event | Data | When |
|---|---|---|
| `qr_generated` | `{image_b64}` | Login QR available |
| `qr_expired` | `{}` | QR rotated; new one will follow |
| `qr_scanned` | `{display_name, avatar?}` | Phone scanned, awaiting confirm |
| `login_complete` | `{own_id, session: {cookie, imei, userAgent}, profile: {display_name, avatar_url}}` | Login finished |
| `status_changed` | `{status: "connecting"\|"connected"\|"disconnected"\|"qr_pending"}` | State transition |
| `message` | (see §3.5) | Inbound chat |
| `message_undo` | `{msg_id, thread_id, thread_type}` | Sender recalled a message |
| `group_event` | passthrough | Member added/removed/etc. |
| `disconnected` | `{reason: str, fatal: bool}` | Bridge lost connection. `fatal=true` → no auto-reconnect, requires QR re-login |
| `bridge_log` | `{level, msg}` | Optional structured log forward |

### 3.5 `message` event — Python-side normalized form

The bridge translates raw zca-js fields into a stable shape so Python doesn't peek at zca-js internals:

```json
{
  "thread_id": "<zalo_thread_id>",
  "thread_type": "user" | "group",
  "uid_from": "<sender_zalo_uid>",
  "msg_id": "<zalo_msg_id>",
  "ts_ms": 1730000000000,
  "text": "<plain text or empty>",
  "content_type": "text" | "image" | "sticker" | "video" | "voice" | "gif" | "link" | "location" | "file" | "contact_card" | "rich",
  "mentions": [{"uid": "...", "pos": 0, "len": 4}],
  "quote": {"msg_id": "...", "owner_uid": "...", "preview": "..."} | null,
  "is_forward": true | false,
  "is_self": false,
  "sender_profile": {"display_name": "...", "avatar_url": "..."},
  "group_name": "..." | null,
  "attachments": [
    {"kind": "photo", "href": "...", "thumb_b64": "...", "filename": null}
  ]
}
```

Mapping rules (in `bridge.js`):
- `data.type === 0` → `thread_type = "user"`; `=== 1` → `"group"`.
- `data.content` is `string` → `text = data.content`, `attachments = []`.
- `data.content` is `object` with `href` → `text = ""`, `attachments` populated.
- `data.reference` truthy → `is_forward = true`.
- `data.mentions` array passed through (uid/pos/len only).
- `data.quote` truthy → `{msg_id: data.quote.globalMsgId, owner_uid: data.quote.ownerId, preview: data.quote.msg}`.
- `content_type` derived from `msgType` per §6.5 detection table.
- `sender_profile` filled from bridge's user-info cache (§6.4); `group_name` from group-info cache.

---

## 4. Persistence

### 4.1 New table: `zalo_account`

```sql
CREATE TABLE zalo_account (
  id                       TEXT PRIMARY KEY,           -- UUID
  display_name             TEXT,                       -- the bot account's own Zalo display name
  zalo_uid                 TEXT,                       -- the bot account's own Zalo uid (set after login)
  avatar_url               TEXT,
  status                   TEXT NOT NULL DEFAULT 'qr_pending',
                           -- enum: 'qr_pending' | 'connecting' | 'connected' | 'disconnected'
  session_encrypted        BLOB,                       -- Fernet-encrypted JSON {cookie, imei, userAgent}
  session_updated_at       INTEGER,                    -- epoch ms; for staleness monitoring
  last_connected_at        INTEGER,
  created_at               INTEGER NOT NULL,
  updated_at               INTEGER NOT NULL
);
CREATE INDEX idx_zalo_account_status ON zalo_account(status);
```

Repo: `src/repositories/zalo_account_repository.py` exposing `create`, `get`, `list_active`, `update_status`, `update_session`, `update_profile`, `set_zalo_uid`.

### 4.2 Boss column

```sql
ALTER TABLE bosses ADD COLUMN default_zalo_account_id TEXT
  REFERENCES zalo_account(id) ON DELETE SET NULL;
```

Nullable. Bosses without it can still receive Zalo inbound (because routing is by `external_identity(zalo_uid)` → person → boss), but `proactive` outbound (reminder fire) needs an account chosen. If null, the proactive layer logs a warning and falls back to Telegram (which the boss already has).

### 4.3 Encryption

Reuse the existing Fernet helper from Phase 3 (per-instance master key from settings). `ZaloAccountRepository.update_session` encrypts on write; `get` decrypts on read. Plaintext `session.json` (the probe artifact) is forbidden in production code paths — `ZaloMessenger.__init__` asserts session is loaded via the repo, not from disk.

### 4.4 Identity rows

Reuse Phase 2 `external_identity` + `conversation`. No schema change.

- `external_identity.provider = "zalo"`.
- `external_identity.external_id = <zalo_uid>` (sender) or `<zalo_thread_id>` for groups.
- `conversation.provider = "zalo"`, `conversation.external_thread_id = <zalo_thread_id>`, `conversation.kind = "dm" | "group"`.

The person-UUID → DM-conversation mapping for outbound (already solved generically in `services/telegram.py`'s `_to_internal_chat_id`) is mirrored in `channels/zalo.py`.

---

## 5. Container & Lifespan

`AppContainer.build_container`:
1. Read `zalo_account_repo.list_active()` — accounts with `status IN ('connected', 'connecting', 'disconnected')` AND a session present.
2. For each, instantiate a `ZaloMessenger`, register under `messengers["zalo:account:<account_id>"]`.
3. Stagger spawn 10s apart (§6.1) to avoid concurrent login burst.

`ZaloAccountManager` is a thin helper (in `channels/zalo.py`) that:
- `get_for_boss(boss_id) -> ZaloMessenger | None` — looks up `boss.default_zalo_account_id`.
- `get_for_account(account_id) -> ZaloMessenger | None` — direct lookup.
- `iter_active() -> Iterable[ZaloMessenger]` — for cron jobs.

Lifespan shutdown: iterate all `ZaloMessenger` instances, call `await msg.close()` → sends `shutdown` RPC, awaits clean exit (5s), SIGTERM (5s more), SIGKILL.

---

## 6. Safety & Reliability

### 6.1 Rate limiter (Zalo-scoped, account-keyed)

Lives in `src/channels/zalo_bridge/rate_limiter.py`. **Not** shared with other channels.

```python
class ZaloRateLimiter:
    PER_THREAD_RATE_PER_SEC = 0.5      # 1 msg / 2s / thread
    PER_THREAD_BURST = 5
    GLOBAL_PER_MIN_PER_ACCOUNT = 25    # sliding window
    DAILY_PER_ACCOUNT = 200            # hard daily cap
    JITTER_MS = (200, 800)

    async def acquire(self, account_id: str, thread_id: str) -> None:
        # 1. Check daily cap (calendar-day reset, account-keyed) — raise if exhausted.
        # 2. Wait for global per-minute window (sliding 60s, account-keyed).
        # 3. Wait for per-thread token bucket.
        # 4. Sleep random(JITTER_MS).
        # 5. Record send.
```

In-memory, per-process. Daily cap from ZaloCRM reference; tighter than per-minute alone and stops "slow drip spam" patterns. If daily exhausted, `ZaloMessenger.send` raises `ZaloDailyLimitError` — caller logs and surfaces to user (e.g. "Đã đạt giới hạn gửi Zalo hôm nay").

3 bosses sharing 1 account share the 25/min and 200/day budget — that's the right scope, since Zalo measures activity at the account level.

### 6.2 Typing indicator

Before each `send`, optionally emit `set_typing` RPC (~1s). Settings flag `ZALO_TYPING_INDICATOR` (default on). Cheap insurance against bot heuristics.

### 6.3 Disconnect, reconnect, circuit breaker

Bridge owns reconnect logic. zca-js's `listener.start({ retryOnClose: true })` handles low-level reconnect attempts. The bridge wraps it with high-level guardrails:

- **Circuit breaker:** if ≥ 5 disconnect events in a 5-minute window → emit `disconnected{fatal: true}` and stop reconnecting. Account moves to `qr_pending`. (Pattern from ZaloCRM.)
- **Backoff between manual reconnect attempts:** 1s → 2s → 4s → 8s → 16s → 32s → 60s, then 60s steady.
- **Initial connect:** if `login_session` fails 3 times in a row at startup, emit fatal — don't hammer Zalo.

Python observes:
- `disconnected{fatal: false}` → log warning, continue (bridge will retry).
- `disconnected{fatal: true}` → mark `zalo_account.status = 'qr_pending'`, audit-log the trip, send a Telegram DM to bosses linked via `default_zalo_account_id`: "Phiên Zalo của bot mất kết nối — chạy `zalo_login --account <id>` để quét QR lại."
- Bridge process exit → `ZaloBridgeProcess.closed` flag. Subsequent `send` raises `ZaloChannelDownError` — `MessageRouter` treats as delivery failure (log + skip), not crash.

### 6.4 Health check & daily session refresh (cron)

`src/infrastructure/scheduler/zalo_jobs.py`, registered with the existing APScheduler.

- **Every 5 minutes:** scan all accounts with sessions; if status ∈ `{disconnected}`, call `messenger.reconnect()`. Stagger 10s per account in the same scan to avoid concurrent login burst.
- **Daily at 04:00 (server time, configurable):** for each connected account, disconnect → wait 5s → reconnect. Stagger 10s per account. Keeps cookies fresh; reduces "session died at 2pm" surprises.

Both cron jobs idempotent and skip accounts in `qr_pending` (those need human action).

### 6.5 Content-type detection

Bridge `bridge.js` extracts `content_type` from `msgType`:

| msgType contains | content_type |
|---|---|
| `photo` / `image` | `image` |
| `sticker` | `sticker` |
| `video` | `video` |
| `voice` | `voice` |
| `gif` | `gif` |
| `link` | `link` |
| `location` | `location` |
| `file` / `doc` | `file` |
| `recommended` / `card` | `contact_card` |
| (object content, no match) | `rich` |
| (otherwise) | `text` |

Python downstream uses `content_type` to decide handling — e.g. `voice` → STT tool, `file` → store in attachment table. The agent layer remains channel-agnostic.

### 6.6 Send semantics — at-most-once

We **do not** retry sends from Python.
- Idempotency keys would require Zalo to honour them, which it does not.
- Duplicates are user-visible and worse than occasional drops.
- Reminder fire on Telegram is already at-most-once; consistent across channels.

If Python doesn't get a reply within 10s, log timeout and surface `send_failed` to the caller. For reminder fire, log and move on. For interactive replies, the user can resend.

### 6.7 Backpressure

Bridge maintains a bounded outbound event queue (max 1000). Overflow drops oldest + emits `bridge_log` warning. Python reads stdout in a tight loop and dispatches into `asyncio.Queue` consumed by handler tasks — no synchronous work in the read loop.

### 6.8 Log redaction

- Bridge: log only metadata (`account_id`, `thread_id`, `msg_id`, `text_len`). **Never log `data.content` or attachment URLs.**
- Python: structured records via `observability.request_context`; `text` excluded from default formatter.
- Audit log: records the *fact* of send (boss_id, account_id, thread_id, msg_id, ts) — not the body.

### 6.9 Media handling

zca-js photo/file URLs are short-lived CDN links. For Phase 6b we **skip download** — pass `attachments[].href` through; downstream consumers ignore or download themselves. Protocol leaves `bytes_b64` slot for later without breaking change.

### 6.10 User-info cache (in bridge)

Bridge keeps an in-memory `Map<zalo_uid, {display_name, avatar, phone, cached_at}>` with **5-minute TTL**. Used to populate `sender_profile` on `message` events without hammering `getUserInfo`. (Pattern from ZaloCRM.) Same for group-info (`Map<group_id, {name, members?, cached_at}>`).

### 6.11 Avatar / profile fetch on connect

When `login_qr` or `login_session` succeeds, bridge calls `api.getUserInfo(ownId)` once and includes the profile in the `login_complete` event. Python persists `display_name` and `avatar_url` to `zalo_account` so the operator knows which account is which.

### 6.12 Avatar update on first-seen contact

When inbound message arrives from a `zalo_uid` that the bridge cache doesn't have yet, after fetching `getUserInfo` the bridge attaches `sender_profile` to the event. Python on receiving: fire-and-forget update of `person.avatar_url` (via repo) when null. Cheap profile enrichment, no extra round-trip.

### 6.13 Stagger on bulk reconnect

Container startup, daily refresh, health check — anywhere the system reconnects multiple accounts — wait 10s between each spawn. Avoids N concurrent logins from the same IP, which Zalo flags.

---

## 7. Onboarding (QR login CLI)

`python -m src.cli.zalo_login --account <account_id>` (re-login)
`python -m src.cli.zalo_login --new --label "OA chính"` (create new account row + login)

Flow:
1. If `--new`: insert `zalo_account` row with `status='qr_pending'`, generate UUID.
2. Resolve account row; if it has an active session and not `--force`, abort.
3. Spawn a one-shot bridge in `qr` mode (no listener loop — quits after `login_complete`).
4. On `qr_generated`, save to a temp `qr.png` and `open` in the system viewer (mac/linux/windows fallbacks like in the probe).
5. On `login_complete`, encrypt and persist via `ZaloAccountRepository.update_session`; persist `display_name` + `avatar_url` from the `profile` payload.
6. Print `OK — account <id> linked to Zalo user <uid> (<display_name>)` and exit.

This is operator-facing for self-host. SaaS web UI is Phase 6c+.

To **link a boss to an account:** `python -m src.cli.zalo_link --boss <boss_id> --account <account_id>` → writes `bosses.default_zalo_account_id`.

---

## 8. Inbound flow (boss resolution)

When `ZaloMessenger` receives a `message` event from the bridge:

1. Convert to internal `IncomingMessage` shape (channel-agnostic).
2. Resolve the **person**: `external_identity(provider="zalo", external_id=uid_from)` → person, creating both rows if absent (write-side person creation).
3. Resolve the **conversation**: `(provider="zalo", external_thread_id=thread_id, kind="dm"|"group")` → conversation, creating if absent.
4. Resolve the **boss**: walk `person.owner_boss_id` (a person can be the boss themselves, in which case this DM is "boss talking to bot") OR look at the conversation's existing boss linkage. For group conversations, the boss is whoever first registered the conversation — same logic Telegram uses.
5. Hand the message to `MessageRouter.handle()` with `provider="zalo"`, `account_id=<self.account_id>` in the request context for observability/audit.

The account_id is metadata for tracing — it does not influence routing (because identity is sender-uid-driven, not account-driven). But it's logged so we can answer "which account received this message?" later.

---

## 9. Outbound flow

`messenger.send(internal_target, text, ...)` where `internal_target` is a person UUID or conversation UUID:

1. Resolve `internal_target` → external `(thread_id, thread_type)` via `_to_internal_chat_id`-style helper (mirror Telegram). Person UUID → DM conversation lookup → external thread id.
2. `await self._rate_limiter.acquire(self.account_id, thread_id)` — gates daily/per-min/per-thread budget.
3. Optional `await self._bridge.set_typing(thread_id, thread_type)` then `asyncio.sleep(1)`.
4. `result = await self._bridge.send(thread_id, thread_type, text, mentions, quote_msg_id)`.
5. `audit_service.log_send(boss_id, account_id, thread_id, msg_id, ts_ms)`.
6. Return `result.msg_id` (may be None if zca-js version omits it).

Errors propagate as structured exceptions: `ZaloDailyLimitError`, `ZaloRateLimitError`, `ZaloChannelDownError`, `ZaloSendFailedError`. `MessageRouter` catches and decides whether to surface UX.

---

## 10. Testing strategy

**Unit:**
- `ZaloRateLimiter` — assert per-thread spacing, global cap, daily cap reset at midnight, jitter range, correct account isolation.
- `ZaloBridgeProcess` JSONL framing — feed crafted stdin/stdout via fake streams; verify id correlation, error parsing, event dispatch, partial-line handling.
- Event normalization (`bridge.js`) — Node-side unit tests (`jest`) with fixture events from the probe (DM, group, photo, mention, reply, forward, undo).
- `ZaloMessenger` — mock bridge, assert send pipeline (rate limiter → typing → send → audit) and inbound resolution (event → IncomingMessage).
- `ZaloAccountRepository` — round-trip session encryption.

**Integration (no live Zalo):**
- `FakeBridge` Python class spawns a Python script that speaks JSONL on stdio. Exercise login/send/listen end-to-end without a real Zalo account.

**Smoke (live Zalo, manual):**
- `python -m src.cli.zalo_login --new --label test` → scan QR.
- Verify inbound message flows through `MessageRouter` to the agent.
- Verify outbound `send` lands in app.
- Verify `kill -9` of bridge → fatal disconnect → Telegram alert to linked boss.
- Verify daily refresh cron runs without flapping.

---

## 11. Forward path to Zalo Official Account (future, not built now)

When the operator graduates to Zalo OA (business verification + business model), it lives **as a separate provider**, not a refactor of personal Zalo:

| Aspect | Personal (this spec) | Zalo OA (future) |
|---|---|---|
| Auth | QR + cookie | OAuth + access_token (refresh) |
| Inbound | Long-running listener | Webhook HTTP POST |
| Outbound | Socket | REST API |
| Rate limit | Heuristic | Documented + ZNS quota |
| 24h window | None | Yes |
| Buttons / cards | None | Yes (templates) |

**No refactor needed when OA arrives.** The current spec is forward-compatible:

- Provider name = `"zalo"` (personal). OA = `"zalo_oa"`. No collision in `external_identity` / `conversation`. No data migration.
- New code: `src/channels/zalo_oa.py` (separate `Messenger` impl), `src/controllers/webhooks/zalo_oa.py` (webhook receiver — `controllers/webhooks/` skeleton from Phase 5d ready), `src/repositories/zalo_oa_account_repository.py` (different shape: token + refresh + expiry instead of cookie + imei), `src/channels/zalo_oa/rate_limiter.py` (quota-tier model, not heuristic).
- Boss gets a 2nd nullable column `default_zalo_oa_account_id`. Independent of the personal one — boss can link both.
- Identity layer, MessageRouter, agent layer: no changes.

This section exists to *anchor* the architecture decision; no tasks ship for OA in Phase 6b.

---

## 12. Task list (high-level — to be expanded into a plan)

| # | Task | Files |
|---|------|-------|
| 1 | RPC protocol dataclasses | `src/channels/zalo_bridge/protocol.py` |
| 2 | `zalo_account` table migration + `bosses.default_zalo_account_id` | `src/migrations/00NN_zalo_account.py` |
| 3 | `ZaloAccountRepository` (CRUD + Fernet session) | `src/repositories/zalo_account_repository.py` |
| 4 | `bridge.js` long-running script — JSONL dispatcher, event normalizer (incl. content_type, undo, sender_profile, group_name), reconnect with circuit breaker, user/group info cache, retryOnClose, profile fetch on connect, log redaction | `src/channels/zalo_bridge/bridge.js`, `package.json` |
| 5 | `ZaloBridgeProcess` Python client | `src/channels/zalo_bridge/process.py` |
| 6 | `ZaloRateLimiter` (per-thread + per-min/account + daily/account + jitter) | `src/channels/zalo_bridge/rate_limiter.py` |
| 7 | `ZaloMessenger` + `ZaloAccountManager` | `src/channels/zalo.py` |
| 8 | Container + lifespan wiring (per-account spawn, staggered) | `src/container.py`, `src/main.py` |
| 9 | Inbound integration in `MessageRouter` (provider="zalo" branch) + first-seen avatar update | `src/controllers/message_router.py` |
| 10 | Disconnect (fatal) → audit + Telegram alert to linked bosses | inside `ZaloMessenger` |
| 11 | QR onboarding CLI (`zalo_login`) + boss-link CLI (`zalo_link`) | `src/cli/zalo_login.py`, `src/cli/zalo_link.py` |
| 12 | Cron jobs: 5-min health check, daily refresh (staggered) | `src/infrastructure/scheduler/zalo_jobs.py` |
| 13 | Webhook controller skeleton (for future OA) | `src/controllers/webhooks/__init__.py`, `README.md` |
| 14 | Unit tests (rate limiter, process, messenger, repo) | `tests/test_zalo_*.py` |
| 15 | Node-side tests (event normalization fixtures) | `src/channels/zalo_bridge/bridge.test.js` |
| 16 | Operational docs | `docs/runbook/zalo.md` (re-QR, warm-up, rate-limit tuning, account linking) |

---

## 13. Open questions (to resolve in plan or first iteration)

1. **Settings keys.** Names: `ZALO_BRIDGE_NODE_PATH`, `ZALO_TYPING_INDICATOR`, `ZALO_RATE_LIMIT_PER_MIN`, `ZALO_RATE_LIMIT_DAILY`, `ZALO_DAILY_REFRESH_HOUR`. Default to env-var-overridable, baked-in safe values.
2. **Fernet key scope.** Same per-instance master key as Phase 3, not per-account-derived. Boss-derived adds complexity without a concrete threat model improvement at this stage.
3. **Bridge log forwarding.** Forward stderr line-by-line to Python `logging` with logger name `zalo.bridge.<account_id>`, level INFO. `bridge_log` event reserved for future structured-log shipping (no-op in v1).
4. **`msg_id` from send.** Defensively probe the zca-js response shape; fall back to `null` if absent. Caller treats `msg_id` as optional (audit log records null cleanly).
5. **Daily refresh hour.** ZaloCRM uses 04:00 UTC. For VN deployment, 04:00 local (= 21:00 UTC previous day) is quieter and avoids global midnight contention. Settle in plan.
6. **Health-check stagger when many accounts.** With staggered 10s/account, 30 accounts = 5min — overlaps the next health check tick. If we ever exceed ~25 accounts on one host, refactor to async/parallel with a small concurrency cap. Not a problem for current scale (≤ 5 accounts foreseen).
