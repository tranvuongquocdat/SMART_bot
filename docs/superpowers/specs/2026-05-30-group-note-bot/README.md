# Group Note Bot — Thiết kế chi tiết (v1, pass 3)

**Trạng thái:** Pass 4 — dispatch/extension model rewrite (capability bundle, registry pattern), retrieval pipeline RRF+MMR, MemoryProvider abstraction, LLMGateway abstraction, prompt caching MVP, feature_budgets DB.
**Ngày tạo:** 2026-05-30 · pass 3: 2026-05-31 · pass 4: 2026-05-31
**Branch:** `main` (rebuild, đã collapse)
**Tham chiếu code cũ:** `git show archive/legacy:<path>`

Spec chia thành nhiều file, mỗi section 1 file. Mỗi file edit độc lập,
review độc lập, ít loãng token khi sửa.

## Cách đọc & lặp

- Mỗi section nằm trong 1 file đánh số `01`–`11`.
- Anh sửa thẳng file, hoặc reply: `01 expand` · `04: <thay đổi>` · `09 looks good`.
- Open questions tổng hợp ở [`11-open-questions.md`](./11-open-questions.md);
  close bằng cú pháp ngắn (`media ingest: B`).
- Khi tất cả OK → em invoke `writing-plans` tạo implementation plan.

## Mục lục

| # | File | Tóm tắt |
|---|---|---|
| 1 | [01-product-vision-scope.md](./01-product-vision-scope.md) | Vấn đề, persona, MVP scope (đã update: reminder, project view, Zalo personal, bot acc pool) |
| 2 | [02-architecture-overview.md](./02-architecture-overview.md) | Phân lớp, channel capability matrix, data flow, multi-tenant, topology |
| 3 | [03-identity-channel-linking.md](./03-identity-channel-linking.md) | Web account, deep-link, multi-platform, bot_accounts + assignment pool |
| 4 | [04-group-note.md](./04-group-note.md) | Schema 7 section (de-emoji), lifecycle, edit/merge, versioning, kỹ thuật tham khảo |
| 5 | [05-capture-flow-data-model.md](./05-capture-flow-data-model.md) | Pipeline, messages, FTS+Qdrant, media ingest (legacy port), retention |
| 6 | [06-agent-layer.md](./06-agent-layer.md) | Operation Router, single-agent, tool calling, feature × tier |
| 7 | [07-llm-abstraction.md](./07-llm-abstraction.md) | LLMGateway, ModelRegistry DB+seed, llm_routes, fallback, prompt caching MVP, feature_budgets |
| 8 | [08-plugin-architecture.md](./08-plugin-architecture.md) | Plugin vs channel, folder, manifest, OAuth, settings auto-render |
| 9 | [09-web-admin.md](./09-web-admin.md) | Design principles, sitemap user + super (bot-accounts, models, reminders, projects) |
| 10 | [10-tech-stack-infra.md](./10-tech-stack-infra.md) | Stack, project structure, deployment, env, migration discipline (7-step) |
| 11 | [11-open-questions.md](./11-open-questions.md) | Pass 2 — đã chốt + 4 question còn lại |
| 12 | [12-security.md](./12-security.md) | Auth/session/CSRF/rate-limit/HMAC/authz/secrets/PII redact + credential isolation boss-owned |
| 13 | [13-reminders-tasks.md](./13-reminders-tasks.md) | scheduled_reminders, action_items index, projects view, follow-task path |
| 14 | [14-performance-observability.md](./14-performance-observability.md) | EventBus internal, OTel GenAI trace schema, latency targets per op + mitigation playbook |
| 15 | [15-agent-dispatch-extension.md](./15-agent-dispatch-extension.md) | Pattern dispatch + extension model: capability bundle, event dispatcher, tool/memory/retrieval/LLM registry, config code-vs-DB |

## Tiến độ

| File | Status | Latest pass changes |
|---|---|---|
| 01 | reviewed-v3 | drop Telegram, dual-mode bot acc, 4 optimizations + 3 add-on |
| 02 | reviewed-v3 | drop Telegram block, capability matrix mark Phase 1, EventBus + Telegram task background |
| 03 | reviewed-v3 | dual-mode (platform/boss_owned + accept flow), §3.7 multi-platform Phase 1, §3.10 switch mode, drop Telegram from enum |
| 04 | reviewed-v3 | §4.9 note template system (sections_json, behaviors, system templates) |
| 05 | reviewed-v2 | §5.4 legacy media port + image vision-LLM extract-once |
| 06 | reviewed-v3 | memory tier (boss_profile + session scratchpad), tools pin_message/find_exact_quote/update_boss_profile, pins schema |
| 07 | reviewed-v3 | §7.6 prompt registry DB (key/version/active, /admin/prompts CRUD) |
| 08 | reviewed-v3 | drop Telegram example, channel = Zalo only MVP |
| 09 | reviewed-v3 | dual-mode wizard, admin filter Platform/Boss-owned, /admin/prompts /admin/templates /admin/audit-log, SSE live preview, Pinned tab |
| 10 | reviewed-v3 | drop Telegram stack row, project structure thêm events/ + prompts/ + bot_accounts ownership, repositories thêm pins/note_templates/prompts |
| 11 | reviewed-v3 | close pass 2.2 (dual-mode + 4 opt + 3 add-on + drop Tele + §14) |
| 12 | reviewed-v3 | drop TelegramVerifier (Phase 1), credential isolation boss-owned vs platform, audit log |
| 13 | reviewed-v3 | no major change (link to §9.8 only) |
| 14 | new | EventBus internal, OTel GenAI trace schema, latency budget + mitigation playbook |
| 15 | new (pass 4) | Dispatch + extension model — capability bundle, registry pattern, declarative > imperative |

Em update status `reviewed-v3 → approved` khi anh duyệt. Hoặc reply
`Spec OK` để duyệt toàn bộ.
