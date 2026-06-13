# Channel Inbound Ingest — Boss-membership gating (logic chung toàn platform)

**Ngày:** 2026-06-13
**Trạng thái:** Design đã chốt, chờ review trước khi viết plan.

## 1. Vấn đề

Audit luồng inbound hiện tại phát hiện một **vết nứt kiến trúc**, không phải vài bug rời:
tầng "kết nối tài khoản" và tầng "định danh sếp + lọc nhóm" chưa được nối với nhau, và
mỗi kênh tự resolve boss theo một kiểu riêng nên logic lệch nhau.

Các lỗ cụ thể (xếp theo mức độ):

- **P0-1. Nhóm không kiểm tra membership.** `zalo/normalizer.py:128` resolve boss chỉ qua
  `bot_account_assignments` + `LIMIT 1`, không hề kiểm tra acc chính của sếp có trong nhóm.
  ⇒ acc bot bị add vào nhóm nào (kể cả nhóm rác/lạ) là nuốt hết tin của nhóm đó, gán cho sếp.
- **P0-2. Không có phanh chặn nhóm lạ.** `subscription.py:258` `is_group_active` trả `True`
  mặc định cho nhóm chưa biết ⇒ nhóm lạ mặc định ACTIVE ⇒ tự build note + tự trả lời khi bị tag.
- **P0-3. QR flow quên ghi `account_links`.** `zalo_qr_login.py` chỉ tạo `bot_accounts` +
  `bot_account_assignments`, không insert `account_links` cho UID acc chính của sếp. `dm_responder`
  chỉ chạy khi `sender_is_boss==True` ⇒ DM từ sếp không bao giờ kích hoạt. (Path Web *có* ghi
  account_links — `web/promotion.py:48` — riêng Zalo sót.)
- **P1-4. Mâu thuẫn mô hình self vs worker.** `bridge.js:154` skip self. Nếu acc QR chính là acc
  của sếp thì tin của sếp bị skip; nếu là acc worker riêng thì account_links acc chính không có.
- **P1-5. Platform N-sếp/1-acc gán nhầm.** `normalizer.py:135` `LIMIT 1` chọn 1 sếp tùy ý. Web
  cũng vậy (`web/normalizer.py:66`).
- **P1-6. `classify_thread_kind` đoán theo độ dài chuỗi** (`adapter.py:126`, dùng ở
  `outbound_service.py:76`) ⇒ DM reply tới uid dài ≥19 ký tự bị gửi nhầm `ThreadType.Group`.
- **P2-7. Dedup thủng khi thiếu msgId** (`messages.py:38` + `normalizer.py:62` `or None`): NULL
  trong unique index là distinct ⇒ tin thiếu msgId có thể double-insert.

## 2. Quyết định nền tảng (đã chốt với chủ dự án)

1. **Bot là tài khoản RIÊNG; sếp là một thành viên khác trong nhóm.** Hệ thống nhận diện nhóm
   của sếp bằng cách: UID acc chính của sếp có xuất hiện trong nhóm hay không. (Loại bỏ mô hình
   "acc sếp làm bot".)
2. **Định danh acc chính của sếp bằng handshake DM một lần (`/start <token>`).** Universal cho
   mọi kênh có DM. Backend `linking_service` đã có sẵn; chỉ cần nối UI và đưa vào wrapper chung.
3. **Phát hiện "nhóm có sếp" bằng quy tắc boss-spoke:** nhóm chỉ được track cho sếp B sau khi
   UID acc chính của B được nhìn thấy là **người gửi ít nhất một tin** trong nhóm đó. Không phụ
   thuộc member-list API ⇒ universal. Sếp được hướng dẫn: "nói một câu / tag bot trong nhóm để
   kích hoạt". Spam group sếp không nói → không bao giờ track → tự lọc rác.
4. **Logic này là wrapper bắt buộc, dùng chung toàn platform.** Mọi kênh (Web, Zalo, và sau này
   Telegram, Messenger, Lark…) đều chảy qua cùng một cơ chế; không kênh nào tự resolve boss hay
   tự publish `message.captured`. Thêm kênh mới = chỉ viết phần dịch wire-format.

## 3. Kiến trúc

### 3.1 Envelope chuẩn + wrapper bắt buộc

Tái dùng dataclass `InboundMessage` đã có trong `src/channels/base.py`. Mỗi adapter chịu trách
nhiệm duy nhất: dịch payload wire-format của kênh → `InboundMessage`, rồi gọi `_emit_inbound(msg)`.

```
[Adapter kênh X]
   nhận wire-format → parse → InboundMessage
   self._emit_inbound(msg)            # publish topic chung "inbound.normalized"
        │
        ▼
[InboundIngest]  (MỘT subscriber duy nhất cho "inbound.normalized", mọi provider)
   1. handshake /start  (nếu DM + text bắt đầu "/start ")
   2. resolve boss + gate nhóm (boss-spoke)
   3. dedup insert messages
   4. publish "message.captured" (có thể nhiều lần — mỗi sếp confirmed một lần)
        │
        ▼
[Tầng agent / note / artifact]  — không đổi
```

- **Bỏ** các normalizer per-provider (`zalo/normalizer.py`, `web/normalizer.py`) ở vai trò
  resolve+publish. Phần parse wire-format chuyển vào chính adapter.
- **Bỏ** topic `inbound.raw.<provider>` + `message.captured` được publish rải rác. Chỉ còn
  `inbound.normalized` (adapter → ingest) và `message.captured` (ingest → downstream).
- Cung cấp base mixin `BaseChannelAdapter` với `async def _emit_inbound(self, msg: InboundMessage)`
  publish `inbound.normalized`. Adapter **không** có đường nào khác để đẩy tin vào hệ thống ⇒
  enforcement bằng cấu trúc, không chỉ bằng quy ước.
- **Entry chuẩn = publish `inbound.normalized` với một `InboundMessage`.** Kênh kiểu subprocess
  (Zalo) gọi `_emit_inbound` từ vòng đọc stdout. Kênh kiểu HTTP (Web — inbound đến từ POST trong
  `web/routes.py`) build `InboundMessage` ngay trong route handler rồi publish cùng topic đó. Hai
  kiểu khác nhau về nơi parse, giống nhau ở điểm ra: cùng một envelope, cùng một wrapper.

### 3.2 Sổ đăng ký nhóm — TÁI DÙNG `group_notes` (không thêm bảng mới)

`group_notes` đã là entity per-`(boss_id, provider, chat_id)` (`UNIQUE (boss_id, provider,
chat_id)`, cột `is_active` từ migration 0005), và `is_group_active` + `list_groups` + UI đều đọc
nó. Vì vậy **không tạo bảng `group_boss_link`** — dùng chính `group_notes` làm "sổ các nhóm sếp
đang track".

- **"Nhóm G được track cho sếp B"** ⇔ tồn tại row `group_notes(boss_id=B, provider, chat_id=G)`
  với `is_active=TRUE`.
- Row này được tạo bằng `GroupNotesRepo.get_or_create(provider, chat_id)` (đã có,
  `group_notes.py:89`) tại thời điểm **sếp nói câu đầu** trong nhóm (content rỗng, note tổng hợp
  điền sau qua `NoteService`).
- **Gate ≠ `is_group_active`.** `is_group_active` trả `True` cho nhóm *chưa có row* (coi như chưa
  bị tắt) — KHÔNG dùng làm điều kiện capture. Điều kiện capture là **row PHẢI tồn tại và
  `is_active=TRUE`**. Sếp tắt nhóm = `is_active=FALSE` ⇒ ngừng capture.
- Phân biệt 2 lý do `is_active=FALSE` qua cột `status` sẵn có:
  - `status='left'` — auto-deactivate do sếp rời nhóm (§3.8). Sếp quay lại nói tiếp → boss-spoke
    **reactivate** (`is_active=TRUE`, `status='active'`).
  - `status='paused'` — sếp tự tắt thủ công trên web. Boss-spoke **KHÔNG** tự bật lại; chỉ sếp
    bật lại trên web.

Cần thêm: một query cross-boss `SELECT boss_id FROM group_notes WHERE provider=$1 AND chat_id=$2
AND is_active` (kèm index `(provider, chat_id)`) cho bước gate — tương tự `account_links.lookup`.

### 3.3 Thuật toán gate cho tin nhắn NHÓM (thay `normalizer.py:128`)

Trong `InboundIngest`, với mỗi `InboundMessage` có `chat_type='group'`:

```
1. candidates = các boss đang có assignment active với msg.bot_account_id
                 (scope theo bot account đã nhận tin). Web dùng chung một 'web' bot account cho
                 nhiều sếp → candidates có thể nhiều; gate ở bước sau lọc tiếp. (Migration phải
                 sửa Web để điền bot_account_id thật của acc 'web' vào InboundMessage, thay vì
                 None như hiện tại.)
2. sender_boss = boss trong candidates mà account_links khớp msg.sender_provider_id (nếu có).
3. Nếu sender_boss tồn tại:
      GroupNotesRepo(boss=sender_boss).get_or_create(provider, chat_id)
      → tạo row nếu chưa có (đây là bước "sếp nói → track nhóm"); nếu row đang paused thì giữ.
4. tracked = các boss có row group_notes active cho (provider, chat_id), giao với candidates.
5. Nếu tracked rỗng → DROP, không lưu.
6. Với mỗi boss B trong tracked:
      insert message (scope boss=B), publish message.captured
        sender_is_boss = (msg.sender_provider_id == account_links UID của B)
```

Hệ quả: bỏ `LIMIT 1` (vá P1-5); 2 sếp cùng nhóm được xử lý độc lập (đúng spec §3.5); không cần
member API. **Phụ thuộc đổi unique của `messages` (xem 3.6)** — nếu không, bước 6 với nhiều sếp
sẽ bị `ON CONFLICT DO NOTHING` nuốt mất bản của sếp thứ hai.

### 3.4 Tin nhắn DM (giữ tinh thần, dọn lại)

Trong `InboundIngest`, với `chat_type='dm'`:

```
1. Nếu text bắt đầu "/start <token>":
      LinkingService.consume(token, sender_provider_id, bot_account_id)
      → thành công thì ack "Đã kết nối…" qua outbound_service; return (không lưu).
2. Resolve boss: account_links theo (provider, sender_provider_id) JOIN assignment active
   với bot_account_id.
3. Có boss → insert + publish (sender_is_boss=True). Không có → DROP.
```

### 3.5 Định danh — nối UI handshake (`/start <token>`)

Sau khi sếp kết nối acc bot (QR hoặc admin gán), web hiển thị bước:
"Mở [Zalo/Telegram/…] bằng **tài khoản chính của anh**, nhắn `/start <token>` cho bot."
Token mint qua `LinkingService.generate(boss_id, provider, bot_account_id)` (đã có). Đây là khâu
làm DM của sếp sống lại (vá P0-3) và là nguồn duy nhất ghi `account_links` cho acc chính.

> Lưu ý: QR flow tạo acc bot vẫn giữ, nhưng **không** còn tự ý insert account_links cho acc đó.
> account_links chỉ đến từ handshake acc chính.

### 3.6 Thay đổi schema (migration mới)

1. **`messages` unique theo boss** *(bắt buộc cho multi-boss)*: đổi
   `UNIQUE (provider, chat_id, provider_msg_id)` → `UNIQUE (boss_id, provider, chat_id,
   provider_msg_id)`. Cập nhật `ON CONFLICT` trong `MessagesRepo.insert` cho khớp. Lý do: mô
   hình tenant vốn là mỗi sếp một bản sao (`messages.boss_id NOT NULL`, `idx_messages_chat`
   boss-first, `group_notes` đã unique theo boss). Không đổi thì nhóm nhiều sếp mất tin của sếp
   thứ hai.
2. **`group_notes` index tra cứu cross-boss**: thêm `CREATE INDEX ON group_notes(provider,
   chat_id) WHERE is_active` phục vụ bước gate (4 trong §3.3).
3. **Không tạo bảng mới** (đã bỏ `group_boss_link` — xem §3.2).

### 3.7 Đăng ký wrapper (wiring)

`InboundIngest.register(bus, pool, outbound_service, admin_repo)` gọi **một lần** lúc startup
(trong `registry.discover_and_load` hoặc app lifespan, sau khi bus sẵn sàng) — subscribe đúng
một handler vào `inbound.normalized`. `setup(ctx)` của từng kênh **bỏ** dòng `normalizer.register`;
nó chỉ còn dựng adapter (+ wire route với Web). Thêm kênh mới ⇒ không phải đụng phần định danh/gate.

### 3.8 Re-verify rời nhóm (auto deactivate)

Scheduler job định kỳ (reuse `src/scheduler/jobs/`) quét các nhóm đang track (`group_notes`
active) theo từng provider hỗ trợ `list_members`:

```
với mỗi (boss B, provider, chat_id) active:
    members = adapter.list_members(bot_acc, chat_id)
    nếu account_links UID của B KHÔNG nằm trong members:
        UPDATE group_notes SET is_active=FALSE, status='left'  (boss rời/bị kick)
```

- Kênh không hỗ trợ `list_members` (Tele/Mess sau này) → bỏ qua re-verify, dựa fallback khác khi
  thêm kênh. Zalo/Web có `list_members` sẵn (`adapter.list_members`).
- Đây là chỗ DUY NHẤT dùng `list_members` — để tắt, không phải để bật. Bật vẫn là boss-spoke.
- Tần suất: cấu hình ở job (mặc định đề xuất ~hằng giờ); rẻ vì chỉ quét nhóm đã track.
- **Deactivate KHÔNG xoá dữ liệu.** Tin cũ trong `messages` + note đã tổng hợp được giữ nguyên,
  vẫn truy được qua `search_history` / `find_exact_quote` / `read_group_note`. Chỉ ngừng ghi tin
  MỚI; note đóng băng ở thời điểm rời. Sếp quay lại nói tiếp → boss-spoke reactivate (set
  `is_active=TRUE`) và ghi nhận lại từ đó.

## 4. Vá kèm (cùng vùng, không phình scope)

- **P1-6:** Bỏ `classify_thread_kind` đoán theo độ dài. `InboundMessage`/`message.captured` đã
  biết `chat_type`; mang `thread_kind` (`'user'|'group'`) thẳng xuống `outbound.send` →
  `send_text`. Reply DM không còn bị nhầm thành group.
- **P2-7:** Khi `provider_msg_id` rỗng, dedup theo khóa thay thế
  `(provider, chat_id, sender_provider_id, ts, hash(text))` thay vì để NULL.
- **P0-2:** `is_group_active` giữ default-true nhưng giờ chỉ còn ý nghĩa "tạm tắt một nhóm đã
  track"; phanh chính là **sự tồn tại của row `group_notes` active** (không có row → không lưu).

## 5. Phạm vi đợt này

- Tạo `InboundIngest` + `BaseChannelAdapter._emit_inbound` + topic `inbound.normalized`; đăng ký
  một lần lúc startup (§3.7).
- Migration: đổi unique `messages` theo boss + index tra cứu `group_notes(provider, chat_id)`
  (§3.6). **Không** tạo bảng mới.
- Dùng `group_notes` làm sổ track nhóm (§3.2); thêm query cross-boss cho gate.
- **Migrate cả Zalo lẫn Web** sang wrapper chung: chuyển phần parse vào adapter (Zalo: vòng đọc
  stdout; Web: route handler), xóa 2 normalizer cũ ở vai trò resolve/publish. Web điền
  `bot_account_id` thật.
- Nối UI handshake `/start <token>` cho định danh acc chính (Zalo trước; cùng component dùng lại
  cho kênh khác).
- Migrate path admin-inject (`api_admin.py:2175`) + các test đang dựa `inbound.raw.*` /
  publish `message.captured` per-provider (`test_zalo_adapter`, `test_linking_flow`,
  `test_web_normalizer`) sang envelope/đường mới.
- Job re-verify rời nhóm → auto deactivate (§3.8).
- Vá kèm mục 4.

## 6. Không làm (YAGNI)

- Không dùng member-list để **bắt đầu** track (đã chọn boss-spoke). `list_members` chỉ dùng cho
  re-verify rời nhóm (§3.8), không nằm trong đường gate vào.
- Không kéo lịch sử nhóm trước thời điểm sếp nói câu đầu (kênh không hỗ trợ). Bù bằng hướng dẫn.
- Không đụng Telegram/Messenger/Lark (chưa có adapter) — nhưng wrapper đảm bảo khi thêm thì
  chúng tự chạy đúng cơ chế.

## 7. Edge cases

- **Tin nhóm trước khi sếp nói câu đầu** → mất (chấp nhận; có hướng dẫn sếp).
- **Sếp rời nhóm → auto deactivate** (xem §3.8): re-verify định kỳ phát hiện UID sếp không còn
  trong nhóm → set `group_notes.is_active=FALSE` → ngừng nhận tin ngay. Không chờ thủ công.
- **Bot skip self** (`bridge.js:154`) vẫn đúng vì bot là acc riêng, không phải acc sếp.
- **Nhiều sếp cùng nhóm, cùng/khác bot acc** → mỗi sếp một row `group_notes`, xử lý độc lập.
- **Token sai bot account** → `LinkingService.consume` từ chối, không tạo link (đã đúng).

## 8. Kiểm thử

- Unit `InboundIngest`:
  - DM `/start` hợp lệ → tạo account_links, ack, không lưu message.
  - DM từ sếp đã link → captured, `sender_is_boss=True`. DM từ người lạ → drop.
  - Group: sếp chưa nói → drop toàn bộ. Sếp nói 1 câu → tạo row `group_notes` active, tin đó +
    tin sau của người khác đều captured. Nhóm sếp không có mặt → drop.
  - Re-verify: sếp rời nhóm → job set `is_active=FALSE` → tin tiếp theo bị drop.
  - 2 sếp cùng nhóm → 2 `message.captured` độc lập, `sender_is_boss` đúng từng sếp.
  - Dedup: tin trùng msgId → 1 lần; tin thiếu msgId → khóa thay thế chặn trùng.
- Adapter Zalo/Web: parse wire-format → `InboundMessage` đúng; chỉ gọi `_emit_inbound`, không tự
  publish `message.captured`.
- Outbound: reply DM tới uid dài → gửi `ThreadType.User` (không còn nhầm group).
- E2E qua web-test-channel: dựng nhóm, sếp im → bot câm; sếp nói → bot bắt đầu ghi nhận.
