# Group Note Bot — Thiết kế chi tiết (v1, pass 2)

**Trạng thái:** Đã review pass 2 — 15 thay đổi + 4 Q close. Sẵn sàng cho implementation plan.
**Ngày tạo:** 2026-05-30 · pass 2 cập nhật: 2026-05-31
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
| 7 | [07-llm-abstraction.md](./07-llm-abstraction.md) | LLMClient, ModelRegistry DB+seed, feature_routing, fallback |
| 8 | [08-plugin-architecture.md](./08-plugin-architecture.md) | Plugin vs channel, folder, manifest, OAuth, settings auto-render |
| 9 | [09-web-admin.md](./09-web-admin.md) | Design principles, sitemap user + super (bot-accounts, models, reminders, projects) |
| 10 | [10-tech-stack-infra.md](./10-tech-stack-infra.md) | Stack, project structure, deployment, env, migration discipline (7-step) |
| 11 | [11-open-questions.md](./11-open-questions.md) | Pass 2 — đã chốt + 4 question còn lại |
| 12 | [12-security.md](./12-security.md) | Auth/session/CSRF/rate-limit/HMAC/authz/secrets/PII redact — hooks bật từ ngày 1 |
| 13 | [13-reminders-tasks.md](./13-reminders-tasks.md) | scheduled_reminders, action_items index, projects view, follow-task path |

## Tiến độ

| File | Status | Pass 1 changes |
|---|---|---|
| 01 | reviewed-v2 | drop Lark Msg, drop voice, add reminder/projects MVP |
| 02 | reviewed-v2 | capability matrix, drop Lark Msg, bot_account in router |
| 03 | reviewed-v2 | bot_accounts schema + assignment pool, §3.7 multi-platform |
| 04 | reviewed-v2 | de-emoji heading, §4.8 techniques (Anthropic/Bytedance) |
| 05 | reviewed-v2 | §5.4 legacy media port, drop voice/OCR |
| 06 | reviewed-v2 | Operation Router, feature × tier, reminder tools |
| 07 | reviewed-v2 | DB-backed registry, feature_routing table |
| 08 | reviewed-v2 | plugin vs channel split, Lark Base = plugin |
| 09 | reviewed-v2 | design principles, new admin pages, projects/reminders |
| 10 | reviewed-v2 | Zalo personal stack, §10.7 migration discipline |
| 11 | reviewed-v2 | close resolved + 4 Q còn lại |
| 12 | new | security & hardening hooks |
| 13 | new | reminders + tasks + projects view |

Em update status `reviewed-v2 → approved` khi anh duyệt từng file. Hoặc
reply `Spec OK` để duyệt toàn bộ.
