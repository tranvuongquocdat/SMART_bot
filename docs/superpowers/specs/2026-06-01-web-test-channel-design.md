# Web Test Channel — Design Spec

**Ngày:** 2026-06-01
**Mục tiêu:** Plug-and-play "channel" thứ hai (sau Zalo) cho phép giả lập nhiều
user / nhiều group / DM-boss trong trình duyệt — dùng để self-test agent
cross-group memory mà không cần spam Zalo thật.

Refactor channel-registry (ngày 2026-06-01, cùng PR series) đã tạo cơ sở:
mọi channel mới chỉ cần một folder `src/channels/<name>/` với `setup(ctx)`
entrypoint. Spec này áp dụng pattern đó cho channel `web`.

---

## 1. Phạm vi & ràng buộc

### Trong scope
- Dev/test channel: chạy trong môi trường local + staging.
- UI web tại `/test` mô phỏng chat: DM boss ↔ bot + nhiều group đa-thành-viên.
- Tạo / xoá users (boss + non-boss) qua UI.
- Tạo / xoá groups, quản lý thành viên qua UI.
- Gửi message dưới identity bất kỳ; chỉ-định `@bot` để mention.
- Bot reply nhận realtime qua SSE.
- Replay 50 message gần nhất khi reload tab.
- Messages persist vào DB thật (`messages` table, `provider='web'`) để memory /
  retrieval / agent loop chạy đúng end-to-end.
- Tương thích với pattern "sim-channel" — channel thật (Telegram, WhatsApp
  sau này) **không** thêm bảng mới.

### Ngoài scope (chốt khoá lại để sau)
- Auth boss thật trên web (`/test` cho phép switch identity tự do).
- Group avatar / sticker / media — chỉ text MVP.
- Multi-bot trong cùng 1 group (1 bot account web duy nhất).
- E2E test automation chạy headless trên Playwright (có thể làm sau khi UI ổn).

### Ràng buộc
- LLM gọi **thật** (NativeGateway, OpenAI/Groq/Gemini) — không stub. Lý do:
  toàn bộ điểm test là validate agent reasoning cross-group.
- Core (agent loop, OutboundService, repositories) **không sửa**. Chỉ thêm
  folder `src/channels/web/` + 3 bảng DB + route web.
- `ENABLE_WEB_TEST_CHANNEL` flag (default `true` ở dev, `false` ở prod) để
  tránh accidentally enable trên production.

---

## 2. Kiến trúc

### 2.1 Data flow inbound

```
Browser tab (sending as web_user u-001)
  │  POST /test/api/send  {as: "u-001", chat_id: "g-001", text: "...", mention_bot: true}
  ▼
src/channels/web/routes.py
  │  publish "inbound.raw.web" { web_user_id, chat_id, text, mention_bot }
  ▼
src/channels/web/normalizer.py
  │  resolve sender → check boss via account_links(provider='web')
  │  resolve chat_type (dm: nếu chat_id bắt đầu "dm:", else group)
  │  MessagesRepo.insert (provider='web', sender_provider_id=web_user_id, ...)
  │  publish "message.captured"
  ▼
Agent dispatcher + trigger engine  (UNCHANGED)
  │
  ▼
OutboundService.send(boss_id, provider='web', chat_id, content, ...)
  │
  ▼
WebAdapter.send_text(bot_acc, chat_id, text, thread_kind)
  │  resolve recipient set:
  │   - DM (chat_id "dm:u-XXX"): chỉ u-XXX
  │   - Group (chat_id g-XXX): all members of group
  │  push JSON event to all SSE clients của các recipient online
  ▼
Browser tab subscribed /test/stream?as=u-XXX
  │  render bubble if chat_id == active view
  │  else: unread badge trên sidebar
```

### 2.2 Data flow outbound

OutboundService gọi `adapter.send_text()` trực tiếp (đã refactor). WebAdapter
giữ in-memory dict `dict[web_user_id, list[SSEClient]]`; mỗi `send_text`:
1. Resolve recipients qua `WebUsersRepo.list_members(chat_id)` (group) hoặc
   parse `chat_id` (DM).
2. Với mỗi recipient online → push event qua queue của SSEClient.
3. Best-effort, log warning nếu không có client online (message vẫn được persist
   vào `messages` + `outbound_messages` để replay).

---

## 3. Storage model

### 3.1 Bảng mới (additive, không động bảng cũ)

```sql
-- Sim users của channel web. Boss user → boss_user_id link tới users.id
CREATE TABLE web_users (
    id TEXT PRIMARY KEY,              -- e.g. 'u-001'
    name TEXT NOT NULL,
    is_boss BOOLEAN NOT NULL DEFAULT FALSE,
    boss_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE web_groups (
    id TEXT PRIMARY KEY,              -- e.g. 'g-001'
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE web_group_members (
    group_id TEXT NOT NULL REFERENCES web_groups(id) ON DELETE CASCADE,
    web_user_id TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, web_user_id)
);

CREATE INDEX idx_web_group_members_user ON web_group_members(web_user_id);
```

Migration tự áp dụng qua `_migrate_schema` (theo discipline DB migration).

### 3.2 Tái sử dụng bảng có sẵn

| Mục đích | Bảng | Ghi chú |
|---|---|---|
| Boss web user | `users` | Tạo row `role='boss'` khi `web_users.is_boss=true`. `web_users.boss_user_id` lưu liên kết. |
| Boss → web identity | `account_links` | `(boss_id, provider='web', provider_user_id=<web_user.id>)`. Auto-create khi promote `web_user` thành boss. |
| Web bot account | `bot_accounts` | Auto-seed **1** row `provider='web', ownership='platform', status='active', display_name='Web Bot'` lần đầu app boot có channel web. |
| Boss ↔ bot | `bot_account_assignments` | Auto-create khi tạo boss web (giống flow link Zalo). |
| Tin nhắn | `messages` | `provider='web'`, `chat_id` theo convention §3.3. |
| Outbound log | `outbound_messages` | OutboundService persist tự động. |

### 3.3 Convention `chat_id`

- **DM**: `"dm:<web_user_id>"` — vd `"dm:u-001"`.
- **Group**: `"<web_group_id>"` — vd `"g-001"` (giữ ngắn để dễ debug).

Normalizer parse: `chat_id.startswith("dm:")` → chat_type='dm' & recipient = phần sau `"dm:"`; ngược lại → chat_type='group'.

### 3.4 Boss-promotion flow

Khi UI POST `/test/api/users` với `is_boss=true` (hoặc PATCH user lên boss):
1. `INSERT INTO users (name, role='boss', email='<web_user_id>@web.test.local')` → boss_id.
2. `INSERT INTO account_links (boss_id, provider='web', provider_user_id=<web_user_id>)`.
3. `INSERT INTO bot_account_assignments (boss_id, provider='web', bot_account_id=<web bot acc>, status='active')`.
4. `INSERT INTO web_users (id, name, is_boss=true, boss_user_id=boss_id)`.

Demote boss → non-boss: xoá rows ngược lại + set `users.role` hoặc soft-delete (để tránh phá historical messages).

---

## 4. Module layout

```
src/channels/web/
  __init__.py         # setup(ctx) → WebAdapter + register normalizer + register routes
  adapter.py          # WebAdapter implements ChannelAdapter (send_text via SSE)
  normalizer.py       # inbound.raw.web → MessagesRepo.insert → message.captured
  routes.py           # FastAPI router /test/*  (UI + JSON API + SSE)
  sse.py              # SSEClient + SSEHub abstraction (used by adapter)
  state_repo.py       # WebUsersRepo / WebGroupsRepo (CRUD trên 3 bảng mới)
  templates/
    index.html        # SPA-ish: sidebar + chat view + admin pane
    _components.html  # message bubble, sidebar item, modal, ...
  static/
    test.js           # frontend state + EventSource subscribe + DOM render
    test.css          # styling overrides (nhẹ, dùng Tailwind CDN có sẵn)

src/migrations.py     # thêm 3 CREATE TABLE vào _migrate_schema
src/config.py         # ENABLE_WEB_TEST_CHANNEL (default true)
src/main.py           # mount router /test (chỉ khi flag bật) — qua plugin loader hoặc include trực tiếp
```

`setup(ctx)` của web channel:
1. Bảo đảm web bot_account tồn tại (auto-seed nếu chưa).
2. Tạo `WebAdapter(ctx.bus, ctx.admin_repo, sse_hub)`.
3. `normalizer.register(ctx.bus, ctx.pool, ctx.outbound_service, sse_hub)`.
4. Return adapter. (Routes mount riêng ở `main.py` — adapter expose `sse_hub` để route gọi).

---

## 5. HTTP API

| Method | Path | Body / Query | Mô tả |
|---|---|---|---|
| GET | `/test/` | — | HTML UI (templates/index.html) |
| GET | `/test/api/users` | — | List web_users |
| POST | `/test/api/users` | `{name, is_boss}` | Tạo user (auto-promote nếu is_boss) |
| PATCH | `/test/api/users/{id}` | `{name?, is_boss?}` | Update / promote / demote |
| DELETE | `/test/api/users/{id}` | — | Xoá user (cascade members) |
| GET | `/test/api/groups` | — | List groups |
| POST | `/test/api/groups` | `{name, member_ids[]}` | Tạo group + add members |
| DELETE | `/test/api/groups/{id}` | — | Xoá group |
| POST | `/test/api/groups/{id}/members` | `{add: [], remove: []}` | Edit membership |
| GET | `/test/api/chats` | `?as=<web_user_id>` | Liệt kê chats identity này tham gia (DM-bot + groups) |
| GET | `/test/api/chats/{chat_id}/messages` | `?limit=50` | Replay tin gần nhất từ `messages` |
| POST | `/test/api/send` | `{as, chat_id, text, mention_bot}` | Publish `inbound.raw.web` |
| GET | `/test/stream` | `?as=<web_user_id>` (SSE) | Server-sent events: bot replies + new inbounds từ user khác |

Tất cả `/test/api/*` trả JSON. CSRF middleware đã bật toàn project — frontend
gửi `X-CSRF-Token` header (lấy từ cookie hoặc meta tag, theo pattern có sẵn).

---

## 6. UI

### 6.1 Layout
- Sidebar trái: dropdown "Sending as" (chọn identity); list DMs (mỗi boss có 1 DM với bot) + list Groups identity đang ở.
- Panel chính: chat view của chat đang chọn — bubble layout (right = own, left = others, center = system).
- Composer dưới panel: textarea + checkbox `@bot` (nếu group) + nút Send.
- Side pane phải (collapse): admin — add/del user, add/del group, edit members.

### 6.2 State frontend
- URL `?as=<id>` xác định identity hiện tại. Nếu rỗng → modal chọn (default user đầu tiên).
- `EventSource` /test/stream?as=<id> luôn mở; trên event → append vào chat state + render nếu là chat đang xem, else unread badge sidebar.
- Send: POST /test/api/send → optimistic append (chờ event mirror sẽ skip duplicate qua `provider_msg_id` client-generated).

### 6.3 Multi-tab
- Mở nhiều tab với `?as=` khác nhau → mỗi tab là 1 user. Mỗi tab giữ SSE connection riêng. Adapter dispatch theo `web_user_id` recipient.

---

## 7. Bảo mật & cô lập

- `ENABLE_WEB_TEST_CHANNEL` flag — false ở prod, route trả 404.
- Không expose `/test` qua internet ở deployment prod (Cloudflare tunnel chỉ
  whitelist nội bộ — config infra, không thuộc spec này).
- Web bot account dùng `provider='web'` riêng → không có path nào confuse với
  Zalo (provider match strict trong OutboundService + handlers).
- CSRF middleware có sẵn áp dụng — frontend phải include token.
- Không có secret được lưu trong web channel state (web bot không cần
  credentials_blob_enc).

---

## 8. Testing strategy

### Tests cần thêm trong batch implementation
- `tests/integration/test_web_channel_send_receive.py` — gửi 1 inbound qua HTTP, assert message.captured fire, agent reply qua adapter.send_text được push lên SSE client mock.
- `tests/integration/test_web_users_repo.py` — CRUD web_users / web_groups / membership; cascade delete.
- `tests/integration/test_web_boss_promote.py` — promote → tạo users + account_links + assignment đầy đủ; demote → cleanup.
- `tests/e2e/test_web_cross_group_memory.py` (slow, dùng real LLM stub mark) — seed 2 group có messages khác nhau, boss DM hỏi cross-group → assert agent recall.

### Manual smoke
- Boot app local → mở `http://localhost:8000/test` → tạo 1 boss + 2 user + 1 group → chat thử → verify bot reply.

---

## 9. Migration & rollout

1. Implement spec này trên branch riêng (`feat/web-test-channel`).
2. `_migrate_schema` add 3 CREATE TABLE IF NOT EXISTS — additive, không drop.
3. Smoke test local + e2e test pass.
4. Merge. Default `ENABLE_WEB_TEST_CHANNEL=true` ở dev / staging,
   `false` ở prod env file.

Không có data migration. Bảng mới rỗng khi deploy.

---

## 10. Risks & open questions

| Risk | Mitigation |
|---|---|
| Tab giữ SSE lâu → memory leak ở adapter | Heartbeat timeout 30s; drop client nếu queue overflow > 100 messages. |
| Boss web "promote" tạo `users` row → orphan nếu user delete | `boss_user_id ON DELETE SET NULL` + soft-delete users (đã pattern). |
| Multi-process (gunicorn workers) → SSE hub không share state | MVP: chạy 1 worker cho `/test/*`. Future: Redis pub-sub. **Defer.** |
| Race: 2 tabs send cùng lúc cùng identity | OK — messages có timestamp & provider_msg_id riêng, không conflict. |
| LLM cost khi self-test loop | Cost cap đã có (per-boss + per-feature). Web không bypass. |

**Open question:** có cần "reset all" button (truncate web tables + messages provider='web') để dọn dẹp test session? — Để sau. Có thể thêm `/test/api/reset` debug-only.
