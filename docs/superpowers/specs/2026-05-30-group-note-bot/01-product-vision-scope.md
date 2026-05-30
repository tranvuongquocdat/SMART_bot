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
| **Capture** | Mọi message trong group nào có sếp linked. Lưu text raw + tên hiển thị người gửi. |
| **Group note** | 1 note markdown/group, 7 section ([§4.2](./04-group-note.md#42-schema-7-section)). Auto-update theo debounce + threshold. Sếp edit được trên web. |
| **Op in-group** | `@bot tóm tắt` / `@bot refresh note` · `@bot Q&A` trên note + history · auto-detect action item nhúng vào note |
| **DM với sếp** | Q&A cross-group · "tóm tắt group X tuần này" · list việc đang mở · KHÔNG có push tự động |
| **Web (user)** | Sidebar 8 section (Dashboard, Groups, Action Items, Digests-disabled, Channels, Plugins, Usage, Settings). Xem [§9](./09-web-admin.md). |
| **Web (super)** | 3 page — Bosses, Payments, Revenue. Role-gated qua env var. |
| **Channel** | Zalo (ưu tiên) + Telegram. Lark Messenger hoãn. |
| **AI** | Provider abstraction (OpenAI / Groq / Anthropic / Gemini / Custom). 2-tier fast/smart. BYO key. |
| **Plugin** | Kiến trúc sẵn sàng; **0 plugin ship**. |
| **DB** | PostgreSQL + Qdrant. |
| **Auth (user)** | Google OAuth + email/password (fallback). |
| **Auth (channel)** | Deep-link qua DM `/start <token>`. |
| **Subscription** | Manual: hiện VietQR + superadmin click "đã thanh toán". |

## 1.5 Hoãn (Phase 1+)

- Daily digest DM (toggle + lịch)
- Stalled-work alerts
- **Media ingest ngoài text** — decision ở [§5.4](./05-capture-flow-data-model.md#54-xử-lý-media--decision-mở) (recommend B)
- Plugin ship: Google Calendar, Lark Base
- Lark Messenger channel
- Auto-detect thanh toán (Casso/SePay webhook)
- People insights, mood analytics
- Đa tiền tệ, subscription quốc tế

## 1.6 KHÔNG làm

- Không build billing engine. Sếp chuyển khoản; em click "đã thanh toán"
  trong admin. Không Stripe, không auto-invoice.
- Không build cross-channel identity resolution. "Anh Tân" để nguyên text
  như hiển thị — không map về `user_id`.
- Không DM nhân viên. Bot chỉ DM sếp đã linked.
- Không offer self-hosted single-tenant. Multi-tenant từ ngày 1.

## 1.7 Mở

- **(mở) Media ingest trong MVP** — xem [§5.4](./05-capture-flow-data-model.md#54-xử-lý-media--decision-mở),
  so sánh A / B / C. Em recommend **B** (URL fetch + voice transcribe).
