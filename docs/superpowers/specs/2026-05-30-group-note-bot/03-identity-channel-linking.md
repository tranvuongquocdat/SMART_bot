[← Index](./README.md)

# §3. Định danh & Kết nối kênh

## 3.1 Tài khoản web (boss → users)

- Sếp đăng ký qua Google OAuth (chính) hoặc email/password (fallback).
- 1 row `users` per sếp. Cột: `id, email, name, google_sub,
  password_hash` (nullable), `role, subscription_status,
  subscription_plan, subscription_expiry, tz, language`.
- `tz` default `Asia/Ho_Chi_Minh` khi register. Sếp đổi qua
  `/settings/general` ([§9.2](./09-web-admin.md#92-sitemap-user-pages)).
  Mọi parse thời gian ("3h chiều mai") + format output dùng `users.tz`,
  không phải TZ server.
- `language` default `vi`. Toggle EN khi sếp request.
- `role ∈ {boss, superadmin}`. Auto-set superadmin khi email khớp env
  `SUPERADMIN_EMAILS` lúc login.
- Security hooks bật từ ngày 1 — xem [§12](./12-security.md) (rate-limit
  login, CSRF, password policy, session hardening).

## 3.2 Linking kênh qua deep-link

Platform sở hữu N bot account Zalo cá nhân + 1 Telegram bot. Sau khi sếp
register & active subscription, superadmin assign 1 bot acc (per provider)
cho sếp. Sếp link identity của mình vào bot acc đó qua deep-link:

```
Web (sếp đã login):
  Page /channels → "Zalo: ✓ acc bot đã gán: 0903xxx789"
                   [Kết nối Zalo]
     │
     ▼  server generate token (16 url-safe bytes), TTL 10 phút
     │  INSERT linking_tokens (boss_id, provider, bot_account_id, token)
     │
     ▼  redirect tới deep-link:
        - Zalo personal: copy số điện thoại bot acc + auto-fill DM "/start <token>"
        - Telegram:      https://t.me/<BOT_USERNAME>?start=<token>

Điện thoại sếp:
  Mở app, tap Gửi pre-fill "/start <token>".
     │
     ▼  bot acc nhận DM (channel adapter)
     │  parse token → lookup linking_tokens
     │  verify bot_account_id của tin nhắn khớp với token.bot_account_id
     │  INSERT account_links (boss_id, provider, provider_user_id, linked_at)
     │  DELETE token row
     │  reply "Đã kết nối. Em là bot của anh ở đây."

Web (auto-refresh):
  Page channels hiện: Zalo — Connected
```

## 3.3 Schema

```sql
account_links (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT    NOT NULL,                  -- 'zalo' | 'telegram'
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

`provider` enum chỉ `{zalo, telegram}` cho MVP. Khi thêm Messenger/WhatsApp
sau → thêm string mới, không sửa schema.

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
  superadmin assign 2 sếp cùng nhóm vào cùng 1 acc (xem [§3.8](#38-mô-hình-phân-bổ-bot-acc)).

## 3.6 Đã chốt — UX nhiều sếp

**Tách** — mỗi sếp 1 note độc lập, experience không nhiễu nhau.

## 3.7 Sếp dùng nhiều platform đồng thời

1 sếp có thể link cả Zalo lẫn Telegram. Schema đã hỗ trợ
(`account_links` PK = `(provider, provider_user_id)`, N row/sếp).

```
boss_id=42
  ├── account_links(zalo,     0903xxx111)
  └── account_links(telegram, @datcoder)

  ├── bot_account_assignments(zalo,     bot_acc_id=3)
  └── bot_account_assignments(telegram, bot_acc_id=1)

group_notes:
  - (42, zalo,     <group_zalo_a>)   ← note A
  - (42, zalo,     <group_zalo_b>)   ← note B
  - (42, telegram, <group_tg_c>)     ← note C
```

UI web hiển thị unified dashboard cross-platform; group list có badge
`Zalo` / `Telegram` để phân biệt. Q&A DM được search cả 2 provider trừ
khi sếp filter.

## 3.8 Mô hình phân bổ bot acc

**Nguyên tắc:**
- Platform sở hữu pool N bot acc Zalo (acc cá nhân, real phone). Telegram
  chỉ cần 1 bot.
- **Mỗi (boss × provider) → 1 bot acc duy nhất.** Sếp chỉ "nói chuyện"
  với 1 acc Zalo, 1 acc Telegram.
- **1 bot acc → N sếp.** Acc Zalo có thể serve 2–5 sếp cùng lúc (tuỳ
  load).
- Khi sếp register → superadmin click "Auto-assign" (chọn acc
  least-loaded của provider) hoặc tay chọn cụ thể.

### Schema

```sql
bot_accounts (
  id                       BIGSERIAL PRIMARY KEY,
  provider                 TEXT NOT NULL,                  -- 'zalo' | 'telegram'
  provider_user_id         TEXT NOT NULL,                  -- phone / @handle
  display_name             TEXT,
  account_kind             TEXT NOT NULL,                  -- 'personal' | 'bot_api'
  credentials_blob_enc     BYTEA,                          -- Fernet-encrypted (cookies / token)
  status                   TEXT NOT NULL DEFAULT 'active', -- 'active' | 'logged_out' | 'banned' | 'rate_limited' | 'paused'
  status_reason            TEXT,
  max_assigned_bosses      INTEGER NOT NULL DEFAULT 5,     -- cap riêng từng acc; superadmin edit trên web
  last_seen_at             TIMESTAMPTZ,
  msgs_received_total      BIGINT NOT NULL DEFAULT 0,
  msgs_sent_total          BIGINT NOT NULL DEFAULT 0,
  notes                    TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, provider_user_id)
);

bot_account_assignments (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT NOT NULL,
  bot_account_id   BIGINT NOT NULL REFERENCES bot_accounts(id),
  assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assigned_by      INTEGER REFERENCES users(id),        -- superadmin uid
  PRIMARY KEY (boss_id, provider)
);
CREATE INDEX idx_assignments_account ON bot_account_assignments(bot_account_id);
```

### Auto-assign policy

```python
def auto_assign(boss_id: int, provider: str) -> int:
    candidates = bot_accounts_repo.list_active(provider)
    # filter còn slot trống theo cap riêng từng acc
    candidates = [a for a in candidates if a.assignment_count < a.max_assigned_bosses]
    if not candidates:
        raise NoCapacity(provider)   # admin cần tăng cap hoặc add acc mới
    return min(
        candidates,
        key=lambda a: (a.assignment_count, a.msgs_received_7d),
    ).id
```

Cap **per acc** (`bot_accounts.max_assigned_bosses`, default 5).
Superadmin chỉnh trên `/admin/bot-accounts/:id` — vd acc khoẻ set 10,
acc rate-limit hay bị set 2. Vượt cap = `NoCapacity` → admin assign tay
hoặc tăng cap.

### Re-assign

Khi acc bị ban / logged_out / paused → superadmin reassign sếp đó qua
acc khác. Side effect:
- Group note cũ giữ nguyên (key theo provider+chat_id, không phụ thuộc bot acc).
- Sếp phải re-link identity vào acc mới (deep-link lại).
- Membership lookup tự update theo bot acc mới.

UI quản lý xem [§9.3](./09-web-admin.md#93-sitemap-superadmin-pages) —
`/admin/bot-accounts`.

## 3.9 Đã chốt

- Provider MVP: `zalo` (acc cá nhân, port `zlapi-py` từ legacy) + `telegram` (bot API).
- Bot acc pool: 1 sếp ↔ 1 acc/provider; 1 acc ↔ N sếp.
- Re-link required sau khi swap bot acc.
