# AI Secretary - Thư ký giám đốc ảo

Bot Telegram hỗ trợ giám đốc quản lý công việc, nhân sự, dự án thông qua hội thoại tự nhiên. Hỗ trợ nhiều công ty/sếp trên cùng một bot.

---

## Tính năng chính

| Nhóm | Khả năng |
|------|----------|
| **Quản lý task** | Tạo, xem, cập nhật, xóa, tìm kiếm task bằng ngôn ngữ tự nhiên |
| **Quản lý nhân sự** | Thêm/sửa/xóa thành viên, đối tác. Kiểm tra workload, xung đột lịch |
| **Quản lý dự án** | Tạo dự án, theo dõi tiến độ, xem task liên quan |
| **Ghi chú thông minh** | Bot tự lưu ghi chú về người, dự án, nhóm để nhớ ngữ cảnh |
| **Tìm kiếm ngữ nghĩa** | Tìm task và lịch sử chat theo nghĩa, không cần từ khóa chính xác |
| **Nhắc nhở** | Đặt reminder, bot nhắn đúng giờ |
| **Gửi tin nhắn** | Sếp bảo bot nhắn cho ai đó trong team |
| **Lưu ý tưởng** | Ghi nhanh ý tưởng vào hệ thống |
| **Tìm kiếm web** | Tra cứu thông tin bên ngoài |
| **Phân tích chiến lược** | Cố vấn AI phân tích tình hình, đề xuất giải pháp |
| **Báo cáo tự động** | Briefing sáng 8h, tổng kết chiều 5h, cảnh báo deadline |

---

## Vai trò người dùng

### Sếp (Boss)
Toàn quyền sử dụng mọi tính năng. Khi nhắn bot lần đầu, bot sẽ hướng dẫn tạo workspace riêng (tự động tạo Lark Base + cấu hình).

### Thành viên (Member)
Chỉ xem và cập nhật task **của mình**. Không xem được task người khác, không giao task, không xem tổng quan.

### Đối tác (Partner)
Tương tự thành viên — xem và cập nhật task được giao cho mình.

### Trong nhóm (Group chat)
Bot lưu tất cả tin nhắn trong nhóm, nhưng **chỉ phản hồi khi được tag** (`@tên_bot`). Quyền tùy theo người tag.

---

## Bắt đầu sử dụng

### Đăng ký làm Sếp

1. Mở Telegram, tìm bot và nhắn bất kỳ
2. Bot hỏi: *"Bạn là Sếp, Thành viên, hay Đối tác?"* → Trả lời **1**
3. Nhập tên của bạn
4. Nhập tên công ty
5. Xác nhận **OK** → Bot tự tạo workspace (vài giây)

Sau khi xong, bạn có thể bắt đầu nhắn tin ngay.

### Đăng ký làm Thành viên / Đối tác

1. Nhắn bot, chọn **2** (thành viên) hoặc **3** (đối tác)
2. Nhập tên sếp hoặc tên công ty để tìm team
3. Nhập tên của bạn → Xong

### Thêm bot vào nhóm

1. Thêm bot vào group Telegram
2. Sếp cần đăng ký group với bot (bot sẽ hướng dẫn)
3. Từ đó, tag `@tên_bot` trong nhóm để tương tác

---

## Hướng dẫn sử dụng

Nhắn tin tự nhiên bằng tiếng Việt. Bot hiểu ngữ cảnh, không cần lệnh cố định.

### Quản lý task

```
"Giao cho Bách thiết kế logo, deadline thứ 6"
"Hôm nay có task gì?"
"Task của Linh tuần này"
"Done task thiết kế logo"
"Dời deadline task logo sang thứ 2 tuần sau"
"Xóa task gửi báo giá đi"
"Có task nào liên quan marketing không?"
```

### Quản lý nhân sự

```
"Thêm Minh vào team, làm lập trình viên, nhóm Tech"
"Bách đang ôm bao nhiêu task?"
"Danh sách nhân sự nhóm Media"
"Cập nhật SĐT của Linh: 0901234567"
"Nếu giao thêm task deadline thứ 5 cho Bách thì sao?"
```

### Quản lý dự án

```
"Tạo dự án Rebranding, Linh phụ trách, deadline cuối tháng"
"Tình hình dự án Rebranding"
"Danh sách dự án đang active"
"Cập nhật dự án Rebranding: trạng thái Active"
```

### Ghi chú & trí nhớ

Bot tự động ghi nhớ thông tin quan trọng qua hội thoại. Bạn cũng có thể chủ động:

```
"Nhớ là Bách sẽ nghỉ phép tuần sau"
"Hôm trước mình nói gì về chiến lược Q3?"
```

### Nhắc nhở

```
"Nhắc tôi 3h chiều họp với khách hàng"
"Nhắc tôi ngày 15/5 lúc 9h gửi báo cáo"
```

### Gửi tin nhắn

```
"Nhắn Bách là mai 9h họp online nhé"
"Gửi Linh: gửi lại file thiết kế banner"
```

### Ý tưởng

```
"Lưu ý tưởng: làm video ngắn giới thiệu sản phẩm, tag marketing"
```

### Phân tích chiến lược

Khi bạn hỏi những câu phức tạp, bot tự chuyển sang chế độ Cố vấn:

```
"Sắp xếp lại nhân sự cho Q3 xem nên thế nào"
"Phân tích workload team, ai đang quá tải?"
"Tuần sau có 3 deadline trùng nhau, xử lý sao?"
```

### Tra cứu web

```
"Tìm xem GDP Việt Nam 2025 bao nhiêu"
"Xu hướng marketing 2026 là gì"
```

---

## Báo cáo tự động

Bot gửi tin nhắn tự động cho sếp:

| Thời gian | Nội dung |
|-----------|----------|
| **8:00 sáng** | Briefing: task hôm nay, deadline sắp tới, cảnh báo quá tải |
| **9:30 sáng** | Nhắc deadline ngày mai + cảnh báo task quá hạn cho assignee |
| **5:00 chiều** | Tổng kết cuối ngày |
| **Mỗi phút** | Gửi reminder đến giờ |

---

## Cài đặt (dành cho admin)

### Yêu cầu

- Docker & Docker Compose
- Telegram Bot Token (tạo qua [@BotFather](https://t.me/BotFather))
- Lark Suite App (App ID + Secret)
- OpenAI API Key
- Cohere API Key (dùng cho rerank)

### Cài đặt

```bash
# 1. Clone repo
git clone <repo-url>
cd <repo>

# 2. Setup
./scripts/setup.sh

# 3. Điền API keys vào .env
nano .env

# 4. Khởi chạy
./scripts/start.sh
```

### Quản lý

```bash
./scripts/status.sh    # Xem trạng thái
./scripts/logs.sh      # Xem log realtime
./scripts/restart.sh   # Khởi động lại
./scripts/stop.sh      # Dừng
```

### Backup

```bash
python scripts/backup.py
```

Chạy thủ công hoặc đặt cron chạy hàng ngày. Giữ tối đa 7 bản backup.

---

## Kiến trúc tổng quan

```
Telegram ←→ Bot (FastAPI + Polling)
                ├── Secretary Agent (26 tools, xử lý CRUD)
                ├── Advisor Agent (11 read-only tools, phân tích chiến lược)
                ├── Lark Base (data: People, Tasks, Projects, Ideas)
                ├── SQLite (routing: bosses, people_map, group_map, messages, notes, reminders)
                └── Qdrant (semantic search: messages + tasks per boss)
```

Mỗi sếp/công ty có workspace riêng biệt — data hoàn toàn tách biệt.
