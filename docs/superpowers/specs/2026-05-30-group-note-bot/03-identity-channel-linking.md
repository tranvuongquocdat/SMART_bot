[← Index](./README.md)

# §3. Định danh & Kết nối kênh

## 3.1 Tài khoản web (boss → users)

- Sếp đăng ký qua Google OAuth (chính) hoặc email/password (fallback).
- 1 row `users` per sếp. Cột: `id, email, name, google_sub,
  password_hash` (nullable), `role, subscription_status,
  subscription_plan, subscription_expiry`.
- `role ∈ {boss, superadmin}`. Auto-set superadmin khi email khớp env
  `SUPERADMIN_EMAILS` lúc login.

## 3.2 Linking kênh qua deep-link

Bot do platform sở hữu (1 Zalo OA, 1 Telegram bot, 1 Lark app). Mỗi sếp
link identity kênh qua DM-deep-link:

```
Web (sếp đã login):
  Click [Kết nối Zalo] ở page /channels
     │
     ▼  server generate token (16 url-safe bytes), TTL 10 phút
     │  lưu vào linking_tokens
     │
     ▼  redirect tới deep-link:
        https://zalo.me/<OA_ID>?param=<token>            (Zalo)
        https://t.me/<BOT_USERNAME>?start=<token>        (Telegram)

Điện thoại sếp:
  Zalo/Telegram mở chat với bot.
  Pre-populate "/start <token>" — sếp tap Gửi.
     │
     ▼  bot nhận DM
     │  parse token từ payload
     │  lookup linking_tokens → boss_id
     │  INSERT account_links (boss_id, provider, provider_user_id, linked_at)
     │  DELETE token row
     │  reply "✓ Đã kết nối Zalo. Em là bot của anh ở đây."

Web (auto-refresh):
  Page channels hiện: Zalo ✓ Connected
```

## 3.3 Schema

```sql
account_links (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT    NOT NULL,                  -- 'zalo' | 'telegram' | 'lark_msg'
  provider_user_id TEXT    NOT NULL,
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX idx_account_links_boss ON account_links(boss_id);

linking_tokens (
  token       TEXT PRIMARY KEY,
  boss_id     INTEGER NOT NULL REFERENCES users(id),
  provider    TEXT NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at);
```

## 3.4 Phát hiện thành viên nhóm

Khi message đến từ 1 group chat:

```python
# Pseudo
async def resolve_group_owner(chat_id, provider):
    member_ids = await channel.list_members(chat_id)
    if not member_ids:
        # Fallback nếu channel API hạn chế đọc membership:
        member_ids = await message_repo.distinct_senders(chat_id, days=30)
    rows = await db.fetch(
        "SELECT boss_id FROM account_links "
        "WHERE provider = $1 AND provider_user_id = ANY($2)",
        provider, member_ids,
    )
    return [r["boss_id"] for r in rows]
```

Không có sếp linked nào trong chat → bot drop event im lặng (không reply,
không capture).

## 3.5 Nhiều sếp cùng nhóm (edge case)

Nếu 2 sếp đã linked cùng nằm trong 1 group, cả 2 đều nên thấy group
trong dashboard của mình.

- `group_notes` key theo `(boss_id, provider, chat_id)` — cùng 1 group
  render thành 2 note (1/sếp), edit độc lập.
- Bot reply trong group 1 lần. Attribution: sếp nào tag `@bot` là sếp
  đó; nếu tag trống, lấy sếp link sớm nhất.

## 3.6 Mở

- **(mở) UX nhiều sếp: tách vs gộp.** Em recommend **tách** (mỗi sếp 1
  note độc lập, experience không nhiễu nhau).
