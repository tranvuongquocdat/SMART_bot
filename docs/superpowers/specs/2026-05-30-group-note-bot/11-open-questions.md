[← Index](./README.md)

# §11. Tổng hợp open questions

| § | Open question | Em recommend |
|---|---|---|
| [1.7](./01-product-vision-scope.md#17-mở) / [5.4](./05-capture-flow-data-model.md#54-xử-lý-media--decision-mở) | Media ingest trong MVP | **B**: URL fetch + voice transcribe |
| [2.5](./02-architecture-overview.md#25-mở) | Single-process vs split web/worker | Single cho MVP, split khi >50 sếp |
| [3.6](./03-identity-channel-linking.md#36-mở) | Nhiều sếp cùng nhóm: tách vs gộp | **Tách** (mỗi sếp 1 note độc lập) |
| [4.7](./04-group-note.md#47-mở) | Schema 7 section cố định vs cấu hình per-boss | **Cố định** cho MVP |
| [5.7](./05-capture-flow-data-model.md#57-mở) | Voice STT: API vs tự host | API (Whisper) cho MVP |
| [5.7](./05-capture-flow-data-model.md#57-mở) | Image OCR | Hoãn Phase 1 |
| [5.7](./05-capture-flow-data-model.md#57-mở) | Right-to-be-forgotten cá nhân được mention | Hoãn |
| [6.5](./06-agent-layer.md#65-mở) | Multi-agent (LangGraph) cho Phase 2 | Defer, theo dõi failure rate |
| [6.5](./06-agent-layer.md#65-mở) | Tool call caching | Defer |
| [7.6](./07-llm-abstraction.md#76-mở) | Streaming LLM response | Defer (channel SDK support tricky) |
| [7.6](./07-llm-abstraction.md#76-mở) | Prompt caching Anthropic/OpenAI | Phase 2 |
| [8.8](./08-plugin-architecture.md#88-mở) | Plugin sandboxing | Trust 1st-party MVP, Wasm/MCP nếu mở 3rd-party |
| [8.8](./08-plugin-architecture.md#88-mở) | Plugin version & migrate | Defer |
| [9.8](./09-web-admin.md#98-mở) | i18n web UI | VN-only MVP |
| [9.8](./09-web-admin.md#98-mở) | Mobile responsive | Tailwind breakpoint đủ, không PWA |
| [10.6](./10-tech-stack-infra.md#106-mở) | Multi-region | Defer |
| [10.6](./10-tech-stack-infra.md#106-mở) | Backup pg_dump cron | Defer chi tiết |

## Cách close

- Reply ngắn: `media ingest: B` · `nhiều sếp: tách` · `section schema: cố định` · ...
- Hoặc reply 1 message gom tất cả thay đổi anh muốn.
- Hoặc `Spec OK` để duyệt theo em recommend → em commit final + invoke
  `writing-plans` tạo implementation plan.
