# Design — Zalo automation: test tự động 3 tầng + connect flow + consent notice

> Spec gọn (user chốt: skip plan, spec + triển khai thẳng). Nhánh `feat/zalo-automation`.
> Mục tiêu tổng: build/tune đường Zalo **không cần manual test** — sau đợt này phần việc
> tay của user co lại còn 1 lần smoke ~10 phút với acc thật (checklist ở cuối spec).

## 1. Bối cảnh & mục tiêu

Zalo là kênh chính v1 (acc cá nhân + bridge zca-js, KHÔNG dùng OA — user đã chốt).
Hạ tầng đã có gần đủ: `ZaloAdapter` (spawn `node bridge.js`, JSONL stdin/stdout,
protocol ở `bridge_protocol.py`), QR-login manager (`src/services/zalo_qr_login.py`),
CRUD bot account + daily stats ở superadmin, trang Channels + `zalo-qr-dialog` ở admin.

**Vấn đề:** toàn bộ đường Zalo (adapter ↔ bridge ↔ connect flow) hiện có **0 test
tự động** — mọi verify đến nay đi qua web test channel. Mọi thay đổi kênh Zalo chỉ
phát hiện lỗi khi chạy acc thật = chậm + rủi ro ban acc.

**Mục tiêu đợt này:**
1. Phủ test tự động 3 tầng cho đường Zalo (không chạm server Zalo thật).
2. Chuẩn hoá connect flow boss (acc phụ QR login → bot_account boss_owned → assignment
   → inbound chạy → acc chính handshake `/start <token>`).
3. Khoá hành vi bot bằng test: giao việc/nhắc cho người CHƯA onboard → ghi nhận + nhắc
   TẠI NHÓM (prompt in_group v8 đã có — giờ khoá bằng harness, vá nếu lộ lỗ hổng code).
4. Consent notice khi bot bắt đầu ghi nhận một nhóm mới (nghĩa vụ PDPL, nằm trên đường kênh).

## 2. Non-goals

- **Không automate traffic Zalo thật** (login QR thật, gửi/nhận thật) — rủi ro ban acc,
  và là đúng phần dành cho smoke thủ công 1 lần.
- **Không Zalo OA**, không voice/ASR (đã chốt phase sau), không Messenger.
- **Không đổi kiến trúc** adapter/bridge/InboundIngest — chỉ thêm test + vá gap.
- Retention/cascade-delete: spec riêng (compliance), không thuộc đợt này.

## 3. Kiến trúc test 3 tầng

Nguyên tắc: mọi thứ Zalo-specific nằm sau 2 đường ống hẹp — (a) module `zca-js` bên
trong bridge, (b) JSONL protocol giữa Python và bridge. Giả lập đúng 2 chỗ đó là phủ
được toàn bộ code của mình; phần KHÔNG phủ được duy nhất là hành vi server Zalo thật.

```
Tầng 1 (contract):   test Node ──stdin/stdout── bridge.js THẬT ── zca-js GIẢ (stub module)
Tầng 2 (adapter):    pytest ── ZaloAdapter THẬT ──subprocess── fake_bridge.js (nói protocol)
Tầng 3 (e2e):        harness.py zalo ── app THẬT (uvicorn) ── ZaloAdapter ── fake_bridge.js
                                └── inbound → InboundIngest → spine → responder → send → assert
```

### 3.1 Tầng 1 — contract test `bridge.js` với zca-js stub

- **Stub:** `tests/channels/zalo/fake_zca/` — package Node tên `zca-js` (class `Zalo`,
  `ThreadType`, `login()` trả api giả với `listener.onMessage/onError/start`,
  `sendMessage`, `getGroupInfo`, `getOwnId`). Inject bằng `NODE_PATH` khi spawn —
  `bridge.js` chạy **nguyên bản, không sửa**.
- **Kịch bản stub:** đọc `FAKE_ZCA_SCENARIO` (đường dẫn JSON) — danh sách message thô
  kiểu zca-js (shape thật: `{type, threadId, data:{uidFrom, dName, content, msgId, ts,
  mentions, quote}}`) emit sau khi `listener.start()`.
- **Test (pytest spawn node, không cần test-runner JS riêng):** viết command vào stdin,
  đọc stdout, assert:
  - `ready` event có `own_id`;
  - message group/DM/mention/quote/media → normalize đúng field (khớp docstring protocol);
  - `send` → stub nhận đúng `(msg, threadId, ThreadType)`, reply `{id, result:{msg_id}}`;
  - `fetch_members` → parse `memVerList` `"<uid>_<v>"` đúng;
  - method lạ → `{error: unknown_method}`; stdin rác → không crash;
  - stub báo lỗi listener → event `disconnected {fatal:false}`.

### 3.2 Tầng 2 — integration `ZaloAdapter` ↔ `fake_bridge.js`

- **`tests/channels/zalo/fake_bridge.js`:** script độc lập nói ĐÚNG JSONL protocol
  (không cần zca-js). Điều khiển động qua **control socket** (`FAKE_BRIDGE_CTRL` =
  đường dẫn unix socket): test kết nối vào để (a) inject inbound event bất kỳ lúc nào,
  (b) đọc log các command bridge đã nhận (send/fetch_members/...).
- **Hook production-safe:** `ZaloAdapter` đọc `settings.ZALO_BRIDGE_SCRIPT` (mặc định
  `bridge.js` thật) — test/harness trỏ sang `fake_bridge.js`. Một dòng config, không
  đổi hành vi prod.
- **Test (pytest, asyncio):** start_inbound với bot_account fixture (creds giả) →
  - inject message group có mention → bus nhận `inbound.raw.zalo`/`inbound.normalized`
    với `mentions_bot=True`, `chat_type=group`, ts đúng;
  - `send_text` → control socket thấy command `send` với text ĐÃ strip markdown;
  - `list_members` → trả đúng ids, timeout khi fake im lặng;
  - inject `disconnected {fatal:true}` → bus event `bot_account.status_changed → logged_out`;
  - stop_inbound → process chết trong 5s; start lại idempotent.

### 3.3 Tầng 3 — harness e2e lệnh `zalo`

- `scripts/harness.py zalo`: server thật (`ENABLE_WEB_TEST_CHANNEL` không liên quan —
  đường này đi adapter Zalo thật + fake bridge):
  1. seed bot_account provider='zalo' (creds giả) + boss + assignment active + acc chính
     đã link (`account_links`) + nhóm tracked;
  2. qua control socket bơm hội thoại nhóm (nhân viên giao việc/chốt deadline, có tin
     của sếp) → debounce/extract như thật;
  3. sếp mention bot hỏi ("ai lo việc X?", "nhắc anh Tân họp thứ 3") → assert bridge
     nhận command `send` với nội dung đúng (matcher token như gold);
  4. case khoá hành vi: giao việc cho người CHƯA onboard → bot ghi nhận + `set_reminder`
     scope=group, KHÔNG đòi onboard, KHÔNG DM người lạ — assert qua DB reminders
     (scope/chat_id) + câu trả lời;
  5. case consent: nhóm mới lần đầu capture → bridge nhận command `send` tin consent
     (một lần duy nhất, lần 2 không gửi lại).
- Đây là regression thứ 4 bên cạnh gold/multipass/workload; chạy lặp lại được, không
  cần acc thật.

## 4. Connect flow (chuẩn hoá + phủ test)

Luồng chuẩn sau đợt này (đã có phần lớn, vá chỗ hở + test):

1. Boss vào Channels → "Kết nối Zalo" → `POST /channels/zalo/qr-login` → quét QR bằng
   **acc phụ** (acc nghe ngóng — không phải acc chính của sếp).
2. QR success → tạo `bot_accounts` (ownership=boss_owned, owner_boss_id=boss, creds
   Fernet) + assignment active + `start_inbound` ngay — **verify bằng test tầng 2**
   (mock manager → adapter), vá nếu bước nào thiếu/không idempotent.
3. Boss bấm "Định danh acc chính" → `POST /channels/zalo/link-token` → DM `/start <token>`
   từ acc chính tới acc phụ → `account_links` ghi — **verify tầng 3** (inject DM handshake
   qua fake bridge, assert account_links + tin chào).
4. Trang Channels hiển thị đúng trạng thái (active / logged_out khi bridge báo
   disconnected fatal) — test API `GET /channels` sau khi inject disconnect.
5. `POST /channels/{provider}/connect` (pool nền tảng) giữ nguyên — đó là đường acc
   pool, không phải đường boss_owned; hai đường cùng tồn tại.

## 5. Consent notice khi bot vào nhóm (PDPL)

- **Khi nào:** lần ĐẦU một nhóm được capture cho bất kỳ boss nào trên bot_account đó
  (điểm `ensure_tracked` tạo row mới trong `InboundIngest._handle_group`).
- **Gửi gì:** 1 tin vào nhóm, giọng thư ký, KHÔNG icon, tiếng Việt mặc định:
  "Xin chào cả nhóm. Em là thư ký ảo của <tên sếp>, được thêm vào để ghi nhận và hỗ trợ
  công việc của nhóm (việc được giao, deadline, nhắc lịch). Tin nhắn trong nhóm sẽ được
  ghi nhận cho mục đích này. Nếu nhóm không đồng ý, vui lòng mời em ra khỏi nhóm."
- **Chống lặp:** cột mới `group_notes.consent_notified_at` (migration 0019) — NULL thì
  gửi + set; nhiều boss cùng nhóm cùng acc → vẫn chỉ 1 tin (check theo provider+chat_id,
  không theo boss).
- **Đường gửi:** `outbound_service.send(trigger='system')` — đã có sẵn ở ingest (dùng
  cho handshake ack).
- Text đặt ở `config/seeds/prompts/` hoặc constant service (quyết khi code — ưu tiên
  chỗ superadmin chỉnh được sau).

## 6. Bố cục file

```
tests/channels/zalo/
  fake_zca/            # stub module zca-js (package.json name="zca-js" + index.js)
  fake_bridge.js       # bridge giả nói JSONL protocol + control socket
  scenarios/*.json     # fixture payload shape zca-js (nguồn sự thật cho cả 3 tầng)
  test_bridge_contract.py   # tầng 1 (pytest spawn node + NODE_PATH=fake_zca)
tests/integration/
  test_zalo_adapter.py      # tầng 2
scripts/harness.py           # thêm lệnh `zalo` (tầng 3)
src/config.py                # ZALO_BRIDGE_SCRIPT (default bridge.js thật)
migrations/versions/0019_group_consent_notice.py
```

Fixture shape zca-js lấy từ: normalize() trong `bridge.js` (đã chạy live 06/2026) + docs
zca-js v2.1. Khi user smoke acc thật, bật record-mode (log raw payload) để đối chiếu lại
fixture — nếu lệch shape thì sửa fixture, không sửa test.

## 7. Definition of done

- Tầng 1 + 2 chạy trong `uv run pytest` bình thường (skip tự động nếu thiếu `node`).
- Tầng 3: `harness.py zalo` xanh ×3 liên tiếp; gold 11/11 + multipass 6/6 + workload 6/6
  không regress.
- Connect flow: QR success → assignment active + inbound chạy, verify bằng test.
- Consent notice: gửi đúng 1 lần/nhóm, có test.
- `npm run build` sạch nếu chạm FE; ruff/mypy gate qua như thường.
- Doc smoke checklist 10 phút cho user (cuối BUILD LOG).

## 8. Smoke checklist (việc tay duy nhất còn lại, làm khi nào user muốn)

1. Chuẩn bị 1 acc Zalo phụ (SIM riêng) + acc chính của user + 1 nhóm test ≥3 người.
2. Web admin → Channels → Kết nối Zalo → quét QR bằng acc phụ → thấy trạng thái active.
3. Định danh acc chính: bấm lấy token → DM `/start <token>` từ acc chính → nhận tin chào.
4. Add acc phụ vào nhóm test → thấy tin consent 1 lần.
5. Nhắn 4-5 tin giao việc trong nhóm, mention bot hỏi 2 câu (1 câu về người chưa onboard).
6. Đối chiếu record-log payload với fixture (lệnh in sẵn) — lệch thì báo, không cần sửa gì.
