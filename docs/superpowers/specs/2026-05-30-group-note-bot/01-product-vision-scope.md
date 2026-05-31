[← Index](./README.md)

# §1. Tầm nhìn sản phẩm & phạm vi

## 1.1 Vấn đề

Sếp SME Việt Nam sống trong chat — Zalo là chính, Telegram phụ. Họ quản
nhiều group chat (sale, marketing, tech, đối tác). Họ:

- Sót quyết định bị chôn trong thread dài.
- Quên đã chốt gì tuần trước.
- Không biết các task đang mở rải rác ở các nhóm.
- Khó tra "ai nói gì về X" cách đây vài tuần.
- Mất buổi sáng để scroll.

Tool có sẵn (Asana, Notion, Slack AI, Otter) không phù hợp: bắt rời Zalo,
target user English-first/desktop-first, hoặc quá generic / nặng.

## 1.2 Đối tượng

**Persona chính** — sếp SME / leader team Việt Nam:

- Dùng Zalo cho >80% giao tiếp công việc
- Quản 3–15 group chat
- Có 5–50 nhân viên / đối tác
- Không phải dân tech (không tự paste API key vào setting nếu thiếu UI)
- Trả VND, thích chuyển khoản hơn thẻ

**Persona phụ** — nhân viên của sếp. Tương tác với bot **chỉ** trong group
mà sếp có mặt. Không DM bot, không có cấu hình riêng. Cách này né hoàn
toàn bài toán identity-resolution.

## 1.3 Trục sản phẩm — "group note"

Hiện vật chính của bot là **1 trang document sống cho mỗi group chat**.
Mỗi group có DUY NHẤT 1 markdown note, tự update từ cuộc trò chuyện,
sếp edit được, và là nguồn sự thật cho mọi operation khác:

- Tóm tắt → re-emit note
- Q&A → search note + lịch sử raw
- Action items → view trích từ section "Việc đang mở" của note
- Digest cross-group (hoãn) → roll-up note của tất cả group của sếp

Cách design này gom nhiều feature về 1 hiện vật bền vững, UX rõ ràng:
**1 group = 1 note luôn được cập nhật**.

## 1.4 Phạm vi MVP (Phase 0)

| Layer | Khả năng |
|---|---|
| **Capture** | Mọi message trong group nào có sếp linked. Lưu text raw + tên hiển thị người gửi + media-text (URL/YouTube/file đã extract). |
| **Group note** | 1 note markdown/group, 7 section ([§4.2](./04-group-note.md#42-schema-7-section)). Auto-update theo debounce + threshold. Sếp edit được trên web. |
| **Op in-group** | `@bot tóm tắt` / `@bot refresh note` · `@bot Q&A` trên note + history · auto-detect action item nhúng vào note · `@bot nhắc {ai} {khi nào}` set reminder ngay tại nhóm |
| **DM với sếp** | Q&A cross-group · "tóm tắt group X tuần này" · list việc đang mở · set/list/cancel reminder · KHÔNG có push tự động ngoài reminder do sếp set |
| **Reminder & task** | Bảng `scheduled_reminders` + scheduler. Nhắc đúng nhóm gốc (hoặc DM sếp). Lean base cho follow-task / due-date / recurring sau ([§13](./13-reminders-tasks.md)). |
| **Project tracking** | View cross-group action item + deadline ở `/projects` web (không entity riêng — pull từ group note + reminders). |
| **Media** | Port từ legacy: URL fetch, YouTube transcript, PDF/docx/xlsx extract, **image vision-LLM extract-once** (fast-tier vision). Voice hoãn ([§5.4](./05-capture-flow-data-model.md#54-media-ingest)). |
| **Web (user)** | Sidebar (Dashboard, Groups, Action Items, Projects, Reminders, Channels, Plugins, Usage, Settings). Xem [§9](./09-web-admin.md). |
| **Web (super)** | Bosses, Payments, Revenue, Bot Accounts, Models. Role-gated qua env var. |
| **Channel** | **Chỉ Zalo (acc cá nhân, port `zlapi-py` legacy) — single-channel MVP**. Telegram + Messenger + WhatsApp defer Phase 1+. Zalo OA + Lark Messenger không làm. |
| **Bot account** | **Dual-mode** ([§3.8](./03-identity-channel-linking.md#38-mô-hình-bot-account-dual-mode)): (a) **Platform** — anh sở hữu pool acc Zalo, gán cho sếp, sếp accept; (b) **Self-managed** — sếp tự login acc Zalo cá nhân của họ. Quản lý qua `/admin/bot-accounts` + `/channels`. |
| **AI** | Provider abstraction (OpenAI / Groq / Anthropic / Gemini / Custom). **3 model slot** (smart / fast / vision) cấu hình per-sếp ở `/settings/ai`. Multi-tier routing per-feature ([§7.3](./07-llm-abstraction.md#73-router--feature-routing)). BYO key. |
| **Plugin** | Kiến trúc sẵn sàng; **0 plugin ship**. Lark **Base** là plugin (không phải channel). |
| **DB** | PostgreSQL + Qdrant. |
| **Auth (user)** | Google OAuth + email/password (fallback). Security hooks (rate-limit, CSRF, HMAC webhook) bật từ ngày 1 ([§12](./12-security.md)). |
| **Auth (channel)** | Deep-link qua DM `/start <token>`. |
| **Subscription** | Manual: hiện VietQR + superadmin click "đã thanh toán". |

## 1.5 Hoãn (Phase 1+)

- **Telegram channel** (khách hiện tại không ai dùng — module sẵn, defer triển khai)
- Daily digest DM (toggle + lịch)
- Stalled-work alerts
- Voice transcription
- Plugin ship: Google Calendar, Lark Base
- Zalo OA channel (acc cá nhân là đủ cho MVP)
- Lark Messenger channel (không làm)
- Auto-detect thanh toán (Casso/SePay webhook)
- People insights, mood analytics
- Đa tiền tệ, subscription quốc tế
- Messenger / WhatsApp channel (module sẵn để mở rộng)

## 1.6 KHÔNG làm

- Không build billing engine. Sếp chuyển khoản; em click "đã thanh toán"
  trong admin. Không Stripe, không auto-invoice.
- Không build cross-channel identity resolution. "Anh Tân" để nguyên text
  như hiển thị — không map về `user_id`.
- Không DM nhân viên. Bot chỉ DM sếp đã linked.
- Không offer self-hosted single-tenant. Multi-tenant từ ngày 1.

## 1.7 Đã chốt (Phase 0)

- Media ingest = port từ legacy (URL, YouTube, file) + **image qua vision-LLM extract-once** (legacy có HEIC convert sẵn). Voice hoãn.
- **Channel = Zalo personal duy nhất**. Telegram + Messenger + WhatsApp defer Phase 1+ (module sẵn để mở rộng).
- **Bot account dual-mode**: platform pool (accept handshake) hoặc self-managed (sếp tự login). Default platform.
- Reminder/task lifecycle vào MVP (lean base cho follow-task sau).
- Project tracking = view, không entity riêng.
- AI cấu hình per-sếp = 3 slot model (smart / fast / vision).
- **4 architectural foundations** (template / EventBus / prompt registry / memory tier) + **3 meeting-note add-on** (pin / quote / SSE) vào MVP để tránh refactor lớn sau.
