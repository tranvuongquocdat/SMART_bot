[← Index](./README.md)

# §12. Security & hardening

Section này **mở đường**, không implement full ở MVP. Anh đã dính incident
trước nên ngay từ Phase 0 có hook + interface, code chạy thật ban đầu
có thể chỉ là in-memory. Khi cần lên prod thật / scale, swap impl mà
không phải refactor core.

## 12.1 Nguyên tắc

1. **Tin cậy zero ở biên** — webhook, OAuth callback, form submit luôn
   verify. Internal call giữa module trust nhau.
2. **Defense in depth** — không ai gác cổng duy nhất. Auth + authz +
   rate-limit độc lập.
3. **PII minimal log** — log message content có flag tách riêng, default off.
4. **Secret rotation-friendly** — Fernet key, OAuth client secret có
   key-version để rotate mà không re-encrypt all blob một lần.

## 12.2 Auth (web)

### Session
- Cookie: `HttpOnly`, `Secure`, `SameSite=Lax` cho user; `Strict` cho
  `/admin/*`.
- TTL 30 ngày; rolling reset khi active.
- Session token = signed random (itsdangerous hoặc Authlib token).
- `SESSION_SECRET` env, đủ 64 random bytes.

### Password (fallback)
- bcrypt cost 12.
- Min length 10, không enforce ký tự đặc biệt (NIST 800-63B style).
- Lock account 15 phút sau 5 fail trong 5 phút (rate-limit từ §12.4).

### Google OAuth
- Authlib `state` + `nonce` verify.
- Whitelist `redirect_uri` exact match.
- Email + `email_verified=true` mới allow login.

### Superadmin gate
- `SUPERADMIN_EMAILS` env (CSV).
- Page `/admin/*` decorator `require_role("superadmin")`.
- Tất cả mutation admin log vào `admin_audit_log` (Phase 1; MVP log
  structlog là đủ).

## 12.3 CSRF

- HTMX submit từ trang user → token CSRF trong header `X-CSRF-Token`.
- Token random per-session, gửi qua meta tag trong layout.
- API endpoint POST `/api/*` reject nếu thiếu token / mismatch.
- Webhook channel `/api/channels/*/webhook` exempt CSRF (verify bằng
  HMAC ở §12.5).

## 12.4 Rate-limit interface

```python
# src/security/rate_limit.py
class RateLimiter(Protocol):
    async def check(self, key: str, limit: int, window_sec: int) -> bool:
        """Return True if allowed, False if exceeded."""

class InMemoryRateLimiter:   # MVP
    """Sliding window đếm trong dict. OK single-process."""

class RedisRateLimiter:      # Phase 1
    """Lua script INCR + EXPIRE. Multi-instance."""
```

Apply tại:

| Điểm | Key | Limit |
|---|---|---|
| Login form | `login:{ip}` | 5 / 5 phút |
| Google OAuth callback | `oauth:{ip}` | 30 / phút |
| Channel webhook | `webhook:{provider}:{bot_account_id}` | 100 / phút |
| LLM call per boss | `llm:{boss_id}` | 60 / phút (Phase 1 cost guard) |
| Plugin OAuth start | `pluginauth:{boss_id}:{plugin_id}` | 10 / phút |
| Password reset | `pwreset:{email}` | 3 / giờ |
| Set reminder | `setreminder:{boss_id}` | 30 / phút |

MVP dùng `InMemoryRateLimiter`; multi-instance Phase 1+ swap Redis.

## 12.5 Webhook verification

Mỗi provider verify khác — interface chung:

```python
class WebhookVerifier(Protocol):
    def verify(self, headers: Mapping, body: bytes) -> bool: ...

# Zalo personal account = poll loop, KHÔNG có webhook → verify ở level
# session cookies + status check (`bot_account_health` job).
# Boss-owned acc: thêm verify session ownership = cookies decrypt OK + provider_user_id khớp owner_boss_id

# Plugin OAuth callback: state token verify từ DB

# Phase 1+ (khi add Telegram):
# class TelegramVerifier:
#     def verify(self, headers, body):
#         return headers.get("X-Telegram-Bot-Api-Secret-Token") == self.secret
```

MVP single-channel Zalo → không có webhook signature; security
boundary là cookie/session integrity.

## 12.6 Authz checklist

Mọi repository query trên domain entity **phải** có `boss_id` filter
hoặc explicit `cross_boss=True` (chỉ superadmin path). Code review
checklist:

- [ ] Mọi `SELECT ... FROM <domain_table>` có `WHERE boss_id = $1`?
- [ ] Mọi `UPDATE/DELETE` cùng vậy?
- [ ] Route handler load entity → check `entity.boss_id == request.user.boss_id`?
- [ ] Action item / reminder / group_note ID không expose raw bigserial
      ra URL (dùng `(boss_id, ...)` route hoặc UUID secondary key)?

Helper:

```python
class BossScopedRepo:
    """Inherit để mọi method auto-filter boss_id."""
    def __init__(self, db, boss_id: int): ...
```

## 12.7 Secrets & encryption

- `FERNET_KEY` env — encrypt `boss_integrations.auth_blob_enc`,
  `bot_accounts.credentials_blob_enc`.
- Key-versioning: env hỗ trợ `FERNET_KEY_v1`, `FERNET_KEY_v2`. Code thử
  decrypt lần lượt; encrypt luôn dùng version mới nhất. Rotation =
  thêm v2, để code re-encrypt khi save next lần.
- Không log Fernet key. Không log decrypted blob.
- `.env` không commit; `.env.example` có placeholder.

### Credential isolation — platform vs boss-owned

| Loại | Ai đọc được credentials | Ai sửa được | Ai disable được |
|---|---|---|---|
| **bot_accounts.ownership=platform** | superadmin (re-login, rotate) | superadmin | superadmin |
| **bot_accounts.ownership=boss_owned** | **không ai** (chỉ runtime decrypt cho poll loop của chính sếp đó) | sếp owner | superadmin (disable + audit log; KHÔNG đọc, KHÔNG re-login) |

Code enforcement:
- `bot_accounts_repo.get_credentials(id)` check caller context:
  platform → cho phép admin route; boss_owned → CHỈ runtime channel adapter
  serving chính `owner_boss_id` đó. Admin route raise `Forbidden`.
- Disable boss-owned không cần decrypt — chỉ set `status='paused'`. Audit
  log ghi `{actor: admin_uid, action: 'disable', target: bot_account_id, reason: text}`.

## 12.8 PII log redact

```python
# src/security/log_redact.py
REDACT_FIELDS = {"text", "media_text", "sender_name", "credentials_blob", "auth_blob"}

def redact_processor(_, __, event_dict):
    for k in list(event_dict):
        if k in REDACT_FIELDS:
            event_dict[k] = f"<redacted len={len(str(event_dict[k]))}>"
    return event_dict

structlog.configure(processors=[..., redact_processor, ...])
```

Bật debug log content qua env `LOG_RAW_CONTENT=true` (chỉ dev / staging).
Prod default: log `boss_id`, `chat_id`, `provider`, sizes — không log raw.

## 12.9 Hardening hoãn (Phase 1+)

- 2FA cho web login (TOTP).
- IP allowlist cho `/admin/*`.
- Audit log đầy đủ admin action.
- Bug bounty / responsible disclosure page.
- Quarterly secret rotation runbook.
- Pen test trước khi >100 sếp.

## 12.10 Đã chốt

- Security hooks bật từ ngày 1, impl in-memory đủ cho MVP.
- Mọi mutation admin có log (structlog) ngay; audit_log bảng riêng Phase 1.
- MVP Zalo-only: không có webhook signature; security = session cookie integrity + bot_account_health. Telegram HMAC verifier wire khi enable Phase 1.
- Boss-owned credentials: admin disable được, không đọc được — audit log ghi mọi disable.
- Authz checklist là gate code review, không có middleware magic.
