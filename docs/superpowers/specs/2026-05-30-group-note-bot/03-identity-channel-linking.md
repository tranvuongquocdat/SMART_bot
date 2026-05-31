[← Index](./README.md)

# §3. Định danh & Kết nối kênh

## 3.1 Tài khoản web (boss → users)

- Sếp đăng ký qua Google OAuth (chính) hoặc email/password (fallback).
- 1 row `users` per sếp. Cột: `id, email, name, google_sub,
  password_hash` (nullable), `role, subscription_status,
  subscription_plan, subscription_expiry, tz, language,
  smart_model_id, fast_model_id, vision_model_id, api_keys_enc,
  cost_cap_usd_daily` (default 5, [§12](./12-security.md)).
- Memory semantic (tên gọi, alias, tone, habits) **không** nhúng JSONB
  vào `users` — lưu riêng ở `memory_entries` ([§6.4](./06-agent-layer.md#64-memory-provider))
  để swap mem0/Letta sau qua MemoryProvider abstraction ([§15.5](./15-agent-dispatch-extension.md#155-memory-provider-abstraction)).
- `tz` default `Asia/Ho_Chi_Minh` khi register. Sếp đổi qua
  `/settings/general` ([§9.2](./09-web-admin.md#92-sitemap-user-pages)).
  Mọi parse thời gian ("3h chiều mai") + format output dùng `users.tz`,
  không phải TZ server.
- `language` default `vi`. Toggle EN khi sếp request.
- `role ∈ {boss, superadmin}`. Auto-set superadmin khi email khớp env
  `SUPERADMIN_EMAILS` lúc login.
- Security hooks bật từ ngày 1 — xem [§12](./12-security.md) (rate-limit
  login, CSRF, password policy, session hardening).

## 3.2 Linking kênh — 2 flow theo mode

Sếp chọn 1 trong 2 mode bot acc (xem [§3.8](#38-mô-hình-bot-account-dual-mode)).
Flow link khác nhau:

### Flow A — Platform mode (bot acc do anh cấp)

```
Web (sếp đã login):
  Page /channels → "Anh muốn dùng acc bot do platform cấp?" → [Có]
     │
     ▼  Status: "Đang chờ admin gán acc..."
     │
     ▼  Superadmin /admin/bosses → click "Auto-assign Zalo"
     │  (least-loaded acc còn slot, status='pending_accept')
     │
     ▼  Sếp nhận notify (web banner + email): "Admin gán 0903xxx789. Accept?"
     │  [Accept] → assignment.status='active'
     │  [Decline] → status='rejected', slot trả pool
     │
     ▼  Sau accept:
     │  server generate token (16 url-safe bytes), TTL 10 phút
     │  INSERT linking_tokens (boss_id, provider='zalo', bot_account_id, token)
     │
     ▼  Hiện: "Anh nhắn /start <token> tới 0903xxx789 trên Zalo"
     │  (copy số + token, deep-link nếu app desktop hỗ trợ)

Điện thoại sếp:
  Mở Zalo, gửi "/start <token>" cho 0903xxx789
     │
     ▼  bot acc nhận DM (channel adapter)
     │  parse token → lookup linking_tokens
     │  verify bot_account_id của tin nhắn khớp với token.bot_account_id
     │  INSERT account_links (boss_id, 'zalo', provider_user_id, linked_at)
     │  DELETE token row
     │  reply "Đã kết nối. Em là bot của anh ở đây."

Web auto-refresh: /channels hiện "Zalo — Connected (0903xxx789)"
```

### Flow B — Self-managed mode (sếp tự login acc Zalo của mình)

```
Web (sếp đã login):
  Page /channels → "Anh muốn tự kết nối acc Zalo của mình?" → [Có]
     │
     ▼  Wizard login Zalo:
     │  - QR scan (mở Zalo trên điện thoại, scan QR ở web), HOẶC
     │  - Paste cookies xuất từ extension (advanced)
     │
     ▼  Login success:
     │  INSERT bot_accounts (
     │     provider='zalo', ownership='boss_owned',
     │     owner_boss_id=<sếp>, credentials_blob_enc=...,
     │     status='active'
     │  )
     │  INSERT bot_account_assignments (
     │     boss_id=<sếp>, provider='zalo',
     │     bot_account_id=<vừa tạo>,
     │     assignment_kind='self', status='active', accepted_at=NOW()
     │  )
     │
     ▼  Boss-owned acc CHÍNH LÀ acc của sếp → không cần deep-link riêng
     │  INSERT account_links (boss_id, 'zalo', sếp's provider_user_id)
     │  (lấy provider_user_id từ login session)
     │
     ▼  Bắt đầu poll loop cho acc này

Web auto-refresh: /channels hiện "Zalo — Connected (acc của tôi)"
```

Sếp đổi mode bất kỳ lúc nào — xem [§3.10](#310-switch-mode).

## 3.3 Schema

```sql
account_links (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT    NOT NULL,                  -- MVP: 'zalo' only
  provider_user_id TEXT    NOT NULL,                  -- id của SẾP trên platform
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX idx_account_links_boss ON account_links(boss_id);

linking_tokens (
  token            TEXT PRIMARY KEY,
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT NOT NULL,
  bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at);
```

`provider` enum MVP **chỉ `'zalo'`**. Phase 1+ thêm `'telegram'` →
chỉ thêm string mới, không sửa schema.

## 3.4 Phát hiện thành viên nhóm

Khi message đến từ 1 group chat:

```python
async def resolve_group_owner(chat_id: str, provider: str, bot_account_id: int):
    # 1. Lấy member của group qua channel adapter (capability dependent)
    member_ids = await channel.list_members(chat_id, bot_account_id)
    if not member_ids:
        # Fallback nếu channel API hạn chế đọc membership:
        member_ids = await message_repo.distinct_senders(chat_id, days=30)
    # 2. Match member với account_links → boss_id
    rows = await db.fetch(
        "SELECT boss_id FROM account_links "
        "WHERE provider = $1 AND provider_user_id = ANY($2)",
        provider, member_ids,
    )
    boss_ids = [r["boss_id"] for r in rows]
    # 3. Filter chỉ các boss được assign cho chính bot_account_id này
    return await assignments_repo.filter_by_bot_account(boss_ids, provider, bot_account_id)
```

Không có sếp linked + được assign acc này nào trong chat → bot drop event
im lặng (không reply, không capture).

## 3.5 Nhiều sếp cùng nhóm (edge case)

Nếu 2 sếp đã linked cùng nằm trong 1 group:

- `group_notes` key theo `(boss_id, provider, chat_id)` — cùng group
  render thành 2 note (1/sếp), edit độc lập.
- Nếu cả 2 sếp dùng **cùng** bot acc → bot reply 1 lần, attribution: sếp
  nào tag `@bot` là sếp đó; tag trống → sếp link sớm nhất.
- Nếu 2 sếp dùng **khác** bot acc cùng có mặt trong nhóm → cả 2 acc đều
  thấy event, reply theo acc của sếp tương ứng. Tránh đụng bằng cách
  superadmin assign 2 sếp cùng nhóm vào cùng 1 acc (xem [§3.8](#38-mô-hình-bot-account--dual-mode)).

## 3.6 Đã chốt — UX nhiều sếp

**Tách** — mỗi sếp 1 note độc lập, experience không nhiễu nhau.

## 3.7 Sếp dùng nhiều platform đồng thời (Phase 1+)

MVP chỉ Zalo nên hiện tại sếp = 1 provider. Khi add Telegram/Messenger
Phase 1+, schema đã sẵn sàng (`account_links` PK = `(provider,
provider_user_id)`, N row/sếp).

Forward shape:

```
boss_id=42
  ├── account_links(zalo,     0903xxx111)
  └── account_links(telegram, @datcoder)              ← Phase 1+

  ├── bot_account_assignments(zalo,     bot_acc_id=3)
  └── bot_account_assignments(telegram, bot_acc_id=1) ← Phase 1+

group_notes:
  - (42, zalo,     <group_zalo_a>)   ← note A
  - (42, zalo,     <group_zalo_b>)   ← note B
  - (42, telegram, <group_tg_c>)     ← note C (Phase 1+)
```

UI web Phase 1+ hiển thị badge provider trong group list. Q&A DM search
cross-provider trừ khi sếp filter.

## 3.8 Mô hình bot account — dual-mode

Sếp chọn 1 trong 2 mode (default: platform). Có thể switch sau —
xem [§3.10](#310-switch-mode).

### Mode A — Platform-managed

- Anh (chủ server) sở hữu pool N bot acc Zalo cá nhân (real phone, anh login).
- Sếp register → superadmin gán → sếp **accept** → bắt đầu serve.
- **Mỗi (boss × provider) → 1 bot acc.** Sếp chỉ chat với 1 acc Zalo.
- **1 bot acc → N sếp** (cap per acc, default 5).
- Sếp KHÔNG biết credentials, không control. Anh control mọi thứ.

### Mode B — Self-managed (boss-owned)

- Sếp tự login acc Zalo của mình qua web wizard (QR / cookies paste).
- Bot acc thuộc về CHÍNH sếp đó (`owner_boss_id`).
- **1 acc serve duy nhất 1 sếp** (chính chủ).
- Anh KHÔNG đọc được credentials. Chỉ có thể disable nếu phát hiện abuse (có audit log).
- Sếp tự manage: re-login khi logout, swap khi acc bị ban.

### Schema

```sql
bot_accounts (
  id                       BIGSERIAL PRIMARY KEY,
  provider                 TEXT NOT NULL,                       -- 'zalo' (MVP)
  provider_user_id         TEXT NOT NULL,                       -- phone
  display_name             TEXT,
  account_kind             TEXT NOT NULL,                       -- 'personal' | 'bot_api' (Phase 1+)
  ownership                TEXT NOT NULL,                       -- 'platform' | 'boss_owned'
  owner_boss_id            INTEGER REFERENCES users(id),        -- NULL nếu platform; SET nếu boss_owned
  credentials_blob_enc     BYTEA,                               -- Fernet-encrypted
  status                   TEXT NOT NULL DEFAULT 'active',      -- 'active' | 'logged_out' | 'banned' | 'rate_limited' | 'paused'
  status_reason            TEXT,
  max_assigned_bosses      INTEGER NOT NULL DEFAULT 5,          -- chỉ áp dụng cho ownership='platform'
  last_seen_at             TIMESTAMPTZ,
  msgs_received_total      BIGINT NOT NULL DEFAULT 0,
  msgs_sent_total          BIGINT NOT NULL DEFAULT 0,
  notes                    TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, provider_user_id),
  CHECK (
    (ownership = 'platform'   AND owner_boss_id IS NULL) OR
    (ownership = 'boss_owned' AND owner_boss_id IS NOT NULL)
  )
);

bot_account_assignments (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT NOT NULL,
  bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
  assignment_kind  TEXT NOT NULL,                              -- 'platform_assigned' | 'self'
  status           TEXT NOT NULL DEFAULT 'pending_accept',     -- 'pending_accept' | 'active' | 'rejected' | 'revoked'
  assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assigned_by      INTEGER REFERENCES users(id),               -- platform → superadmin uid; self → boss tự
  accepted_at      TIMESTAMPTZ,                                -- NULL khi pending; auto-NOW khi assignment_kind='self'
  PRIMARY KEY (boss_id, provider)
);
CREATE INDEX idx_assignments_account ON bot_account_assignments(bot_account_id);
```

### Invariants (enforce ở code + DB CHECK)

1. `ownership='boss_owned'` → có duy nhất 1 assignment row, `boss_id = owner_boss_id`, `assignment_kind='self'`, `status='active'` ngay khi tạo.
2. `ownership='platform'` → max `max_assigned_bosses` assignment row có `status='active'`.
3. `assignment_kind='self'` ↔ acc đó `ownership='boss_owned'`.
4. Router chỉ deliver event cho boss nếu `assignment.status='active'`. Pending/rejected → drop.

### Auto-assign (chỉ áp dụng platform mode)

```python
def auto_assign(boss_id: int, provider: str) -> int:
    candidates = bot_accounts_repo.list_active(provider, ownership='platform')
    # filter còn slot trống theo cap riêng từng acc
    candidates = [a for a in candidates if a.active_assignment_count < a.max_assigned_bosses]
    if not candidates:
        raise NoCapacity(provider)
    return min(
        candidates,
        key=lambda a: (a.active_assignment_count, a.msgs_received_7d),
    ).id
```

Vượt cap = `NoCapacity` → admin tăng cap hoặc add acc mới. Sếp có thể
được khuyến nghị switch sang self-managed.

### Accept handshake (chỉ platform mode)

Admin gán → `assignment.status='pending_accept'`. Sếp nhận notify:
- Web banner ở `/channels`: "Admin gán acc 0903xxx789 cho anh. Accept?"
- Email backup (Phase 1).

Sếp click `[Accept]` → status='active' → bắt đầu link identity flow §3.2.
Sếp click `[Decline]` → status='rejected', slot trả pool, admin có thể
re-assign acc khác.

TTL pending_accept: 7 ngày. Quá → auto-revoke, slot trả pool.

### Re-assign / lifecycle

| Trigger | Side effect platform mode | Side effect boss_owned mode |
|---|---|---|
| Acc bị banned/logged_out | Admin assign acc khác; sếp accept lại; re-link identity | Sếp tự re-login hoặc admin disable; group notes giữ |
| Sếp huỷ subscription | Assignment.status='revoked'; slot trả pool | Acc giữ trong DB, status='paused'; sếp re-active khi sub trở lại |
| Admin disable boss-owned (abuse) | N/A | Acc status='paused' + audit_log; sếp được notify lý do |
| Sếp xoá acc của mình (self mode) | N/A | DELETE bot_accounts row + cascade assignment |

Group notes luôn giữ (key theo provider+chat_id, không phụ thuộc bot
acc). UI quản lý xem [§9.3](./09-web-admin.md#93-sitemap-superadmin-pages).

## 3.9 Đã chốt

- **Provider MVP: chỉ `zalo`** (acc cá nhân, port `zlapi-py` legacy). Telegram + Messenger + WhatsApp → Phase 1+ (khách hiện tại không dùng Telegram).
- **Dual-mode bot acc**: platform (default, gán + accept) hoặc self-managed (sếp tự login). Cùng tier giá.
- Platform mode: 1 sếp ↔ 1 acc/provider; 1 acc ↔ N sếp (cap per acc).
- Boss-owned mode: 1 acc serve duy nhất chính sếp đó. Anh disable được (audit log), không đọc được credentials.
- Re-link required sau khi swap bot acc (platform mode).

## 3.10 Switch mode

Sếp đổi platform ↔ self bất kỳ lúc nào ở `/channels`:

```
[Cấu hình hiện tại: Platform — acc 0903xxx789]

[Đổi sang Tự kết nối acc của tôi]

  → Confirm dialog: "Acc bot platform sẽ revoke. Group note giữ
                     nguyên. Anh phải login acc Zalo của mình."
  → [Đồng ý]
     ↓
  1. UPDATE assignment SET status='revoked', revoked_at=NOW()
  2. Slot platform trả pool (assignment_count giảm)
  3. Mở wizard self-managed §3.2 Flow B
  4. Hoàn thành login → assignment mới (self, active)
  5. account_links update (sếp's provider_user_id có thể thay
     đổi nếu acc cá nhân khác acc platform — thường khác)
  6. Group note giữ nguyên (key theo provider+chat_id)
  7. Group membership re-detect tự động khi event mới về
```

Ngược lại (self → platform) tương tự: revoke acc self (xoá khỏi DB
hoặc giữ paused tuỳ sếp), chờ admin gán + accept.

**Lưu ý:** nếu acc Zalo cá nhân khác acc platform, các nhóm cũ
**phải re-add bot acc mới** vào nhóm. Bot không thể tự join lại.
Wizard switch cảnh báo rõ điều này.
