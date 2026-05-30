# Hướng dẫn set-up Lark API cho AI Secretary

Tài liệu này dành cho **admin hệ thống** (người host server — tức là anh/chị đang chạy
bot trên máy chủ của mình). Khách hàng (sếp) **không cần tự làm** bước nào ở đây —
họ chỉ nhắn bot qua Telegram và nhận link Base là xong.

---

## Mô hình phân quyền

```
         1 server (do anh host)
                │
                ▼
   1 Lark Custom App duy nhất (App ID + Secret)
                │
                ▼
   Mỗi sếp → bot tự tạo 1 Bitable Base (trong tenant của app)
                │
                ▼
   Bot tự bật public share link (anyone_editable) cho Base đó
                │
                ▼
   Sếp bấm link Telegram → vào Base xem/edit ngay, không cần login Lark
```

**Ưu điểm hướng public link:**
- Sếp không cần tài khoản Lark, không cần nhận invite, không cần join tenant.
- Zero friction onboarding, link không expire.
- Bot chỉ gửi link qua Telegram DM 1-1 → link không lộ ra ngoài.

**Nhược điểm:** ai có link đều vào được. Nếu rủi ro bảo mật quan trọng (vd sếp không
muốn nhân viên cũ vẫn mở được Base) → sau này đổi sang private-share bằng email (code
đã có sẵn hàm `lark.share_base(email)`).

---

## Phần 1 — Tạo Lark Custom App (một lần duy nhất)

### 1.1 Tạo tài khoản Lark Suite

- Vào <https://www.larksuite.com> (bản quốc tế — dùng `open.larksuite.com`).
- Dự án này đang dùng **larksuite.com** (xem `LARK_API` trong [src/services/lark.py:12](../src/services/lark.py#L12)).
- Đăng ký workspace mới (free plan — Standard F3 — đủ cho dev/demo).

### 1.2 Vào Developer Console

- URL: <https://open.larksuite.com/app>
- Bấm **Create Custom App** → chọn **Self-built App**.
- Điền tên app (vd: `AI Secretary Prod`) và icon.
- Bấm Create → anh sẽ thấy **App ID** và **App Secret** ở tab "Credentials & Basic Info".
  Copy giữ an toàn (đừng commit vào git).

### 1.3 Cấp quyền (Scopes / Permissions)

Vào tab **Permissions & Scopes** → bấm **Add scope** → add:

| Scope | Dùng cho | Bắt buộc? |
|-------|----------|-----------|
| `bitable:app` | Tạo/đọc/ghi/xoá Base và records | ✅ |
| `drive:drive` | Bật public share link cho Base | ✅ |
| `contact:user.base:readonly` | Map email Lark ↔ open_id (chưa dùng nhưng nên có sẵn) | 🟡 Khuyến nghị |
| `im:message`, `im:chat` | Nhắn và quản lý Lark IM/Group (chưa dùng — giao tiếp qua Telegram) | ❌ |

> **Quan trọng:** `drive:drive` là scope chính để bot bật public share. Nếu thiếu,
> code `lark.make_base_public()` sẽ fail → bot vẫn tạo được Base nhưng sếp phải login
> cùng tenant mới vào được.

### 1.4 Publish app

Lark yêu cầu app phải được publish thì `tenant_access_token` mới chạy.

- Tab **Version Management & Release** → **Create a version**.
- Version number: `1.0.0` (tự chọn).
- Availability: chọn "All members of the tenant" hoặc "Specific members" tuỳ ý (không
  ảnh hưởng public link).
- Submit → self-built app sẽ tự approve trong vài giây.

Status phải chuyển sang **Enabled** mới hoạt động. Nếu anh update scope sau này → phải
**Create a new version** lần nữa, publish lại.

### 1.5 Điền `.env`

```env
LARK_APP_ID=cli_xxxxxxxxxxxxxxxx
LARK_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Restart server:
```bash
./scripts/restart.sh
```

---

## Phần 2 — Test

Sau khi restart, nhắn `/start` với một Telegram account test (giả làm sếp mới):

1. Bot hỏi vai trò → chọn Sếp.
2. Bot hỏi tên, công ty, xác nhận.
3. Bot tạo Base, bật public link, gửi link Telegram.
4. Mở link (kể cả ở trình duyệt ẩn danh, chưa login Lark) → phải thấy Base ngay và
   edit được các record.

### Nếu bước 4 không vào được

| Hiện tượng | Nguyên nhân | Cách xử lý |
|------------|-------------|------------|
| "You don't have permission" | Scope `drive:drive` chưa add, hoặc publish chưa cập nhật | Quay lại 1.3 → 1.4, Create version mới |
| Lark đòi login khi bấm link | Free plan giới hạn external access | Xem phần "Free plan limitation" bên dưới |
| Lỗi `code 99991672` trong log bot | Scope thiếu | Add `drive:drive`, publish lại |

### Free plan limitation

Bản Standard F3 (free) của Lark **đôi khi vẫn đòi user login** khi mở link public, kể
cả khi bot đã bật `external_access_entity=open`. Nếu gặp trường hợp này:

1. Test với tài khoản Lark bất kỳ (tạo account free nhanh) — thường vào được OK.
2. Nếu vẫn strict, upgrade tenant lên Pro plan.
3. Hoặc dùng hàm `lark.share_base(email)` thay cho `make_base_public()` — sẽ yêu cầu
   email sếp và share private thay vì public.

---

## Phần 3 — Flow end-user (sếp)

**Sếp chỉ cần:** mở Telegram, nhắn bot, trả lời 3 câu (vai trò, tên, công ty), chờ vài
giây → nhận link Base. Bấm link là xem/edit.

Không cần tài khoản Lark. Không cần install app. Không cần invite.

---

## Phần 4 — Bảo trì

### Token rotation

`tenant_access_token` Lark tự cache 2h (xem [src/services/lark.py:100](../src/services/lark.py#L100)).
App Secret nên rotate định kỳ:
1. Developer Console → Credentials → **Reset App Secret**.
2. Update `.env` → restart. Không cần publish lại.

### Thu hồi quyền public của 1 Base

Gọi `make_base_public(token, link_share_entity="closed")`. Chưa có tool UI — nếu cần
thì thêm 1 tool `revoke_base_public` cho bot.

### Giới hạn Lark free plan

- **API:** ~100 req/s/app, 50 req/s trên Bitable endpoint.
- **Storage:** 2.000 records/table, 50 tables/base.
- **Rate limit:** áp dụng cho cả app → nhiều sếp dùng cùng lúc có thể đụng trần.

Production khuyến nghị upgrade lên Pro (~$12/user/tháng cho admin account host bot —
không cần mỗi khách mua Pro).

---

## Phụ lục — Các hàm Lark trong code

- Tạo Base + 6 tables: `provision_workspace` — [src/services/lark.py:176](../src/services/lark.py#L176)
- Bật public share link: `make_base_public` — [src/services/lark.py](../src/services/lark.py)
- Share Base theo email (dự phòng): `share_base` — [src/services/lark.py](../src/services/lark.py)
- Gọi khi onboarding: `_complete_boss` — [src/onboarding.py](../src/onboarding.py)

Command test nhanh trong Python REPL:
```python
from src.services import lark
await lark.init_lark(APP_ID, APP_SECRET)
ws = await lark.provision_workspace("Test Co")
await lark.make_base_public(ws["base_token"], "anyone_editable")
print(f"https://larksuite.com/base/{ws['base_token']}")
```
