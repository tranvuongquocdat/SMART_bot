# Group Note Bot — Thiết kế chi tiết (Bản thảo v1)

**Trạng thái:** Bản thảo · Full v1 (chia file để dễ bàn)
**Ngày tạo:** 2026-05-30
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
| 1 | [01-product-vision-scope.md](./01-product-vision-scope.md) | Vấn đề, persona, MVP scope, deferred, non-goals |
| 2 | [02-architecture-overview.md](./02-architecture-overview.md) | Phân lớp, data flow, multi-tenant, runtime topology |
| 3 | [03-identity-channel-linking.md](./03-identity-channel-linking.md) | Web account, deep-link, account_links, group membership |
| 4 | [04-group-note.md](./04-group-note.md) | Schema 7 section, lifecycle, edit/merge, versioning |
| 5 | [05-capture-flow-data-model.md](./05-capture-flow-data-model.md) | Pipeline, messages, FTS+Qdrant, media, retention |
| 6 | [06-agent-layer.md](./06-agent-layer.md) | 3 op, single-agent decision, tool calling, context budget |
| 7 | [07-llm-abstraction.md](./07-llm-abstraction.md) | LLMClient, ModelRegistry, 2-tier router, fallback |
| 8 | [08-plugin-architecture.md](./08-plugin-architecture.md) | Folder, manifest, OAuth, settings auto-render |
| 9 | [09-web-admin.md](./09-web-admin.md) | Sitemap user + super, dashboard, tech stack web |
| 10 | [10-tech-stack-infra.md](./10-tech-stack-infra.md) | Stack table, project structure, deployment, env, observability |
| 11 | [11-open-questions.md](./11-open-questions.md) | Tổng hợp open questions + em recommend |

## Tiến độ

| File | Status |
|---|---|
| 01 | draft |
| 02 | draft |
| 03 | draft |
| 04 | draft |
| 05 | draft |
| 06 | draft |
| 07 | draft |
| 08 | draft |
| 09 | draft |
| 10 | draft |
| 11 | draft |

Em update status `draft → reviewed → approved` khi anh duyệt từng file.
