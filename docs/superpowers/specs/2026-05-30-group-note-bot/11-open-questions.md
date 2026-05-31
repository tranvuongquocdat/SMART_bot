[← Index](./README.md)

# §11. Open questions (pass 4)

Pass 4 — rewrite dispatch/extension model theo pattern 2026 (Pydantic
AI capability + OpenAI Agents SDK handoff + AG2 event-driven). Đã close
toàn bộ:

| § | Thay đổi pass 4 | Driver |
|---|---|---|
| **15 (new)** | Section riêng cho dispatch/extension pattern: capability bundle, event dispatcher (no if/elif), registry decorator-based cho tool/memory/retrieval/LLM/trigger/media/resolver, config classification code-vs-DB | Pydantic AI, OpenAI Agents SDK, AG2 v0.4 |
| **6.1** | Operation Router if/elif → **xoá**; thay bằng EventBus dispatcher với predicate `when=` | §15.3 |
| **6.2** | Single-agent kết luận giữ, argumentation đổi sang capability bundle | §15.2 |
| **6.3** | `CORE_TOOLS` constant → tool registry decorator; whitelist per-op qua `@operation.tools` (security boundary) | §15.4 |
| **6.4** | 4 tier hardcoded → MemoryProvider Protocol + 3 scope chuẩn (semantic/episodic/procedural); `InternalMemoryProvider` MVP, mem0/Letta Phase 1 | §15.5, Mem0/Letta/Zep 2026 |
| **6.5** | feature_routing flat → llm_routes table (condition_cel + fallback_chain + weight) | §15.7.1 |
| **5.3** | FTS→vector sequential → retrieval pipeline (parallel_fanout + RRF + MMR; reranker Phase 1) | §15.6, RAG 2026 |
| **7.1** | LLMClient → LLMGateway Protocol; NativeGateway MVP, LiteLLM/Portkey Phase 1+ | §15.7 |
| **7.5** | Prompt caching `defer Phase 2` → **bật ngay MVP** qua stable prefix structure + `cache_prefix_hint` | §15.7.2, Anthropic 2026 default |
| **7.6** | Token budget hardcoded → feature_budgets DB + trim_policy + compression_strategy | §15.7.3 |
| **4.3** | NoteUpdater triggers hardcoded → `@trigger` decorator + agent_triggers DB | §15.8 |
| **5.4** | Media adapter mapping → `@media_adapter` registry | §15.9 |
| **3.4** | resolve_group_owner if-else → resolver chain | §15.10 |
| **10.2** | src/ tree: thêm domain/, memory/, retrieval/, media/, resolvers/, services/, tools/registry; agent/ → agents/; pattern rule entity-not-dict, BossContext constructor, no db.py free-fn | §15.1, layering review |
| **10.7** | 7-step → **8-step** migration checklist (thêm step 8 regression test from snapshot) | feedback memory |
| **10.8 (new)** | Config classification code vs DB rule + cache invalidation pattern | §15.11 |
| **10.9 (new)** | Test strategy section: layer × test kind, coverage target, fixture conventions | review pass 4 |

## Đã chốt pass 1–3 (snapshot trước rewrite)

## Đã chốt

| § | Câu hỏi cũ | Chốt |
|---|---|---|
| [1.7/5.4](./05-capture-flow-data-model.md#54-media-ingest) | Media ingest trong MVP | Port từ legacy: URL / YouTube / TikTok / PDF / docx / xlsx. Voice + OCR → Phase 1. |
| [2.5](./02-architecture-overview.md#25-đã-chốt) | Single-process vs split | Single-process MVP; split khi >50 sếp |
| [3.6](./03-identity-channel-linking.md#36-đã-chốt--ux-nhiều-sếp) | Nhiều sếp cùng nhóm | Tách — mỗi sếp 1 note độc lập |
| [3.9](./03-identity-channel-linking.md#39-đã-chốt) | Channel MVP | Zalo personal (zlapi-py port legacy) + Telegram bot. Zalo OA defer. Lark Messenger không làm. |
| [3.8](./03-identity-channel-linking.md#38-mô-hình-bot-account--dual-mode) | Bot acc pool | Platform sở hữu pool; 1 sếp × provider → 1 acc; 1 acc → N sếp; auto-assign least-loaded |
| [4.7](./04-group-note.md#47-đã-chốt) | Schema 7 section | Cố định; **không emoji** trong heading |
| [5.7](./05-capture-flow-data-model.md#57-đã-chốt--hoãn) | Voice / OCR | Phase 1 |
| [5.7](./05-capture-flow-data-model.md#57-đã-chốt--hoãn) | RTBF cá nhân được mention | Phase 1+ chờ user request |
| [6.6](./06-agent-layer.md#66-đã-chốt--defer) | Multi-agent (LangGraph) | Defer Phase 2 |
| [6.6](./06-agent-layer.md#66-đã-chốt--defer) | Tool call caching | Defer; xem xét sau khi đo hot calls |
| [7.7](./07-llm-abstraction.md#77-đã-chốt--defer) | Model registry source | DB + seed file; superadmin CRUD `/admin/models` |
| [7.7](./07-llm-abstraction.md#77-đã-chốt--defer) | Streaming LLM | Defer (channel SDK Zalo không hỗ trợ) |
| [7.7](./07-llm-abstraction.md#77-đã-chốt--defer) | Prompt caching | Phase 2 |
| [8.8](./08-plugin-architecture.md#88-đã-chốt--defer) | Plugin sandboxing | Trust 1st-party MVP; Wasm/MCP nếu mở 3rd-party (Phase 2) |
| [8.8](./08-plugin-architecture.md#88-đã-chốt--defer) | Plugin version migrate | Defer; track qua `manifest.version` |
| [8.0](./08-plugin-architecture.md#80-plugin-vs-channel) | Lark Base — channel hay plugin | Plugin |
| [9.10](./09-web-admin.md#910-đã-chốt) | i18n web UI | VN-only MVP |
| [9.10](./09-web-admin.md#910-đã-chốt) | Mobile responsive | Tailwind breakpoint, không PWA |
| [9.0](./09-web-admin.md#90-design-principles) | UI tone | Linear/Stripe Dashboard; không emoji, không AI-themed copy |
| [10.6](./10-tech-stack-infra.md#106-đã-chốt--defer) | Multi-region | Defer |
| [10.6](./10-tech-stack-infra.md#106-đã-chốt--defer) | Backup | pg_dump cron daily; chi tiết bucket defer |
| [13](./13-reminders-tasks.md) | Reminder MVP | Có, lean base; cross-group "Projects" = view |

## Đã chốt pass 2.2 — dual-mode + 4 optimizations + 3 add-on + drop Telegram + §14 latency

### Channel & bot account

- **Drop Telegram khỏi MVP** — khách hiện tại không dùng. Module-ready, ship Phase 1+. Tương tự Messenger / WhatsApp.
- **Dual-mode bot account**: (a) Platform — anh sở hữu pool, gán cho sếp, sếp **accept**; (b) Self-managed — sếp tự login acc Zalo. Cùng tier giá. Default platform. Admin disable boss-owned được (audit log, KHÔNG đọc credentials).
- **Switch mode** bất kỳ lúc nào ở `/channels`; group note giữ nguyên (key theo provider+chat_id).

### 4 architectural optimizations (chống tù túng)

- **Note template system** (§4.9): replace hardcoded 7 section bằng `note_templates` table; seed 3 system (general/sales/partner); custom Phase 1. Section descriptor có `behavior ∈ {rolling, append_only, task_list, manual_pin, computed}`.
- **EventBus + OTel observability** (§14.1, §14.2): in-process pub/sub; events `message.captured / note.updated / reminder.fired / llm.call.completed / tool.call.completed / ...`; OTel GenAI semantic convention naming (trace_id, span_id, gen_ai_system, ...) → Phase 1 Langfuse exporter free.
- **Prompt registry DB** (§7.6): `prompts` table với key/version/is_active; `/admin/prompts` CRUD + rollback; A/B Phase 1; DSPy auto Phase 2.
- **Memory tier 4 cấp** (§6.4): boss_profile (core) + group_note (core/group) + session scratchpad (working LRU) + archival (messages + Qdrant); tool `update_boss_profile` cho agent self-write.

### 3 meeting-note positioning add-on

- Tool `pin_message` + section `Đã pin` (template `behavior='manual_pin'`).
- Tool `find_exact_quote` (FTS exact + context ±3).
- SSE live note preview trên `/groups/:id` (subscribe `note.updated` event).

### §14 NEW — Performance & observability

- Latency budget per op: quick ack 2–4s; in-group Q&A 6–12s; DM Q&A 8–15s; reminder fire <500ms; note rebuild 5–15s background.
- Mitigation: typing indicator, quick ack pattern, parallel tool calls, fast-tier default, pre-warm cache, timeout+degrade. Streaming Phase 1 sau spike Zalo capability.

## Đã chốt pass 2.1 — image MVP + 3 model slot

- **Image vào MVP** (vision-LLM extract-once): port HEIC convert + mime sniff từ legacy, thêm 1 vision call/ảnh lúc capture. Lưu describe + OCR vào `media_text`. Cache theo content-hash. Filter sticker/icon. Voice vẫn defer.
- **3 model slot per sếp** (`/settings/ai`): smart / fast / vision. UI giải thích từng slot dùng cho gì, cost ước tính, fallback rules.
- Cột `users`: thêm `smart_model_id`, `fast_model_id`, `vision_model_id` (REFERENCES `models`).
- Feature mới trong `feature_routing`: `image_extract`, `image_qa` → tier `vision`.

## Đã chốt pass 2

- **Q1 — Cap sếp/bot acc**: cap **per acc**, cột `bot_accounts.max_assigned_bosses` (default 5), superadmin chỉnh từng acc trên `/admin/bot-accounts/:id`.
- **Q2 — TZ**: cột `users.tz`, default `Asia/Ho_Chi_Minh`, sếp đổi ở `/settings/general`. Mọi parse/format thời gian dùng TZ của sếp.
- **Q3 — Reminder scope default**: trong group → `group`; trong DM → `dm`. Override bằng từ khoá ("nhắc riêng tôi", "nhắc ở nhóm X"). Rule cứng, không re-ask.
- **Q4 — Spike Zalo legacy**: làm spike 1–2 ngày trước khi commit design Zalo channel. Verify `zlapi-py` (hoặc legacy custom) còn chạy với Zalo 2026: login, send/receive, list member. Output = note go/no-go.

## Spike — task đầu tiên của implementation plan

```
[SPIKE] Verify Zalo personal account stack
  Timebox: 2 ngày
  Goal: trả lời "thư viện Zalo legacy còn dùng được không?"
  Tasks:
    1. Setup `zlapi-py` (hoặc legacy custom Zalo client) với 1 acc test
    2. Login flow — cookie/QR còn work?
    3. Send/receive trong group test
    4. List member của group — API còn work?
    5. Đọc media (URL/file) qua acc Zalo còn ổn?
  Output:
    - `docs/spikes/zalo-2026-readiness.md`: API matrix (work/break)
    - Kết luận: go / fork / thay thư viện khác
  Block: implementation Zalo channel cho tới khi spike close.
```

Cross-link: spike kết quả update vào [§10.1 stack table](./10-tech-stack-infra.md#101-stack)
+ [§3.8 bot account schema](./03-identity-channel-linking.md#38-mô-hình-bot-account--dual-mode)
nếu cần (vd login flow đổi → schema credentials_blob đổi format).

## Tất cả open question đã close

→ Spec sẵn sàng để em invoke `writing-plans` tạo implementation plan
với spike Zalo là task đầu.
