[← Index](./README.md)

# §11. Open questions (pass 2)

Sau review pass 1, các quyết định đã chốt:

## Đã chốt

| § | Câu hỏi cũ | Chốt |
|---|---|---|
| [1.7/5.4](./05-capture-flow-data-model.md#54-media-ingest) | Media ingest trong MVP | Port từ legacy: URL / YouTube / TikTok / PDF / docx / xlsx. Voice + OCR → Phase 1. |
| [2.5](./02-architecture-overview.md#25-đã-chốt) | Single-process vs split | Single-process MVP; split khi >50 sếp |
| [3.6](./03-identity-channel-linking.md#36-đã-chốt--ux-nhiều-sếp) | Nhiều sếp cùng nhóm | Tách — mỗi sếp 1 note độc lập |
| [3.9](./03-identity-channel-linking.md#39-đã-chốt) | Channel MVP | Zalo personal (zlapi-py port legacy) + Telegram bot. Zalo OA defer. Lark Messenger không làm. |
| [3.8](./03-identity-channel-linking.md#38-mô-hình-phân-bổ-bot-acc) | Bot acc pool | Platform sở hữu pool; 1 sếp × provider → 1 acc; 1 acc → N sếp; auto-assign least-loaded |
| [4.7](./04-group-note.md#47-đã-chốt) | Schema 7 section | Cố định; **không emoji** trong heading |
| [5.7](./05-capture-flow-data-model.md#57-đã-chốt--hoãn) | Voice / OCR | Phase 1 |
| [5.7](./05-capture-flow-data-model.md#57-đã-chốt--hoãn) | RTBF cá nhân được mention | Phase 1+ chờ user request |
| [6.6](./06-agent-layer.md#66-đã-chốt--defer) | Multi-agent (LangGraph) | Defer Phase 2 |
| [6.6](./06-agent-layer.md#66-đã-chốt--defer) | Tool call caching | Defer; xem xét sau khi đo hot calls |
| [7.6](./07-llm-abstraction.md#76-đã-chốt--defer) | Model registry source | DB + seed file; superadmin CRUD `/admin/models` |
| [7.6](./07-llm-abstraction.md#76-đã-chốt--defer) | Streaming LLM | Defer (channel SDK Zalo không hỗ trợ) |
| [7.6](./07-llm-abstraction.md#76-đã-chốt--defer) | Prompt caching | Phase 2 |
| [8.8](./08-plugin-architecture.md#88-đã-chốt--defer) | Plugin sandboxing | Trust 1st-party MVP; Wasm/MCP nếu mở 3rd-party (Phase 2) |
| [8.8](./08-plugin-architecture.md#88-đã-chốt--defer) | Plugin version migrate | Defer; track qua `manifest.version` |
| [8.0](./08-plugin-architecture.md#80-plugin-vs-channel) | Lark Base — channel hay plugin | Plugin |
| [9.9](./09-web-admin.md#99-đã-chốt) | i18n web UI | VN-only MVP |
| [9.9](./09-web-admin.md#99-đã-chốt) | Mobile responsive | Tailwind breakpoint, không PWA |
| [9.0](./09-web-admin.md#90-design-principles) | UI tone | Linear/Stripe Dashboard; không emoji, không AI-themed copy |
| [10.6](./10-tech-stack-infra.md#106-đã-chốt--defer) | Multi-region | Defer |
| [10.6](./10-tech-stack-infra.md#106-đã-chốt--defer) | Backup | pg_dump cron daily; chi tiết bucket defer |
| [13](./13-reminders-tasks.md) | Reminder MVP | Có, lean base; cross-group "Projects" = view |

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
+ [§3.8 bot account schema](./03-identity-channel-linking.md#38-mô-hình-phân-bổ-bot-acc)
nếu cần (vd login flow đổi → schema credentials_blob đổi format).

## Tất cả open question đã close

→ Spec sẵn sàng để em invoke `writing-plans` tạo implementation plan
với spike Zalo là task đầu.
