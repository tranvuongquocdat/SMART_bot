# AI Secretary — Thư ký giám đốc ảo

Bot Telegram hỗ trợ giám đốc quản lý công việc, nhân sự, dự án thông qua hội thoại tự nhiên.  
Một người dùng có thể **vừa là sếp của công ty A**, **vừa là đối tác/nhân viên của công ty B** — bot tự nhận biết ngữ cảnh tương ứng.

---

## Tính năng

### Quản lý công việc (Tasks)

| Tính năng | Mô tả |
|-----------|-------|
| Tạo / xem / sửa / xóa task | Nhắn tự nhiên, bot phân tích và ghi vào Lark Base |
| Tìm kiếm ngữ nghĩa | Tìm task theo nghĩa, không cần từ khóa chính xác (Qdrant) |
| Tự động thông báo assignee | Khi tạo task, bot nhắn Telegram cho người được giao |
| Approval flow | Member/partner muốn sửa task → cần sếp duyệt qua chat |
| Deadline push | Nhắc assignee tự động khi còn **24h** và **2h** tới deadline |
| Cảnh báo quá hạn | Nhắc assignee + báo sếp khi task quá hạn |

### Quản lý nhân sự (People)

| Tính năng | Mô tả |
|-----------|-------|
| Thêm / sửa / xóa nhân sự | Lưu vào Lark Base People table |
| Kiểm tra workload | Xem ai đang ôm bao nhiêu task, có xung đột deadline không |
| Phân loại | member (nhân viên), partner (đối tác), customer (khách hàng) |

### Multi-workspace & Membership

| Tính năng | Mô tả |
|-----------|-------|
| Đa workspace | Một người có thể là sếp bên này, nhân viên/đối tác bên kia |
| Join request | Người ngoài xem danh sách công ty → gửi request vào → sếp duyệt |
| Boss approve/reject | Sếp chấp nhận, từ chối, hoặc điều chỉnh quyền khi duyệt request |
| Workspace isolation | Dữ liệu mỗi công ty hoàn toàn tách biệt |

### Nhắc nhở (Reminders)

| Tính năng | Mô tả |
|-----------|-------|
| Tạo / sửa / xóa reminder | Đặt giờ, bot nhắn đúng giờ qua LLM (giọng tự nhiên) |
| Nhắc người khác | Sếp đặt reminder cho nhân viên trong team |
| Sync 2 chiều Lark ↔ SQLite | Reminder hiển thị ở bảng Reminders trên Lark Base; sửa trên Lark cũng tự sync về bot |

### Lịch review tự động

| Tính năng | Mô tả |
|-----------|-------|
| Nhiều lịch | Mỗi sếp có thể đặt bao nhiêu lịch review tùy thích |
| Loại nội dung | `morning_brief` (briefing sáng), `evening_summary` (tổng kết chiều), `custom` (prompt tuỳ chỉnh) |
| Bật/tắt/xóa | Quản lý qua chat, không cần động vào server |
| Giờ tuỳ ý | Đặt bất kỳ giờ nào theo định dạng HH:MM |

### Chat nhóm (Group)

| Tính năng | Mô tả |
|-----------|-------|
| Lưu tất cả tin nhắn | Mọi tin nhắn trong nhóm đều được lưu vào DB + Qdrant |
| Chỉ phản hồi khi được tag | Bot im lặng cho đến khi được `@mention` |
| Context thông minh | Mỗi lần trả lời: 15 tin gần nhất + 8 tin RAG liên quan |

### Reset workspace

Bot hỗ trợ xóa toàn bộ dữ liệu Lark Base khi cần thiết (không xóa SQLite). Cơ chế 2 bước:
1. Gửi `/reset` → bot yêu cầu gõ tên công ty bằng **CHỮ HOA**
2. Gõ `tôi chắc chắn` → bot xóa tất cả records trên Lark

### Cố vấn chiến lược (Advisor)

Khi sếp hỏi phân tích phức tạp, bot tự chuyển sang chế độ cố vấn:

```
"Sắp xếp lại nhân sự Q3 xem thế nào"
"Phân tích workload team, ai đang quá tải?"
"Tuần sau có 3 deadline trùng nhau, xử lý sao?"
```

### Các tính năng khác

- Ghi chú nội bộ (bot tự nhớ thông tin về người/dự án/nhóm)
- Lưu ý tưởng nhanh
- Gửi tin nhắn Telegram thay sếp
- Tìm kiếm lịch sử chat bằng ngữ nghĩa
- Báo cáo workload / tổng kết ngày / tuần
- Tra cứu web

---

## Vai trò người dùng

### Sếp (Boss)
Toàn quyền: tạo task, giao việc, xem toàn bộ, duyệt request, cấu hình lịch review.  
Khi nhắn bot lần đầu, bot tự động tạo Lark Base workspace và gửi link.

### Thành viên (Member)
Chỉ xem và cập nhật task **của mình**. Mọi thay đổi cần sếp duyệt.

### Đối tác (Partner)
Tương tự member — xem và cập nhật task được giao.

### Trong nhóm
Bot lưu tất cả tin nhắn, chỉ phản hồi khi được `@tag`. Quyền tùy theo người tag.

---

## Bắt đầu sử dụng

### Đăng ký làm Sếp

1. Tìm bot trên Telegram và nhắn bất kỳ
2. Bot hỏi vai trò → chọn **Sếp**
3. Nhập tên, tên công ty
4. Xác nhận → bot tự tạo Lark Base (vài giây), gửi link cho bạn

### Đăng ký làm Thành viên / Đối tác (join company)

1. Nhắn bot: *"xem danh sách công ty"* hoặc *"muốn join"*
2. Bot liệt kê các công ty đang hỗ trợ → chọn công ty
3. Chọn vai trò (nhân viên / đối tác) → nhập tên và thông tin
4. Bot gửi request đến sếp của công ty đó
5. Sếp duyệt → bạn nhận được thông báo và có thể dùng bot ngay

### Thêm bot vào nhóm

1. Thêm bot vào group Telegram
2. Sếp đăng ký group với bot (bot hướng dẫn)
3. Tag `@bot_name` trong nhóm để tương tác

---

## Hướng dẫn sử dụng nhanh

### Task

```
"Giao cho Bách thiết kế logo, deadline thứ 6"
"Hôm nay có task gì?"
"Task của Linh tuần này"
"Done task thiết kế logo"
"Dời deadline task logo sang thứ 2 tuần sau"
"Có task nào liên quan marketing không?"
```

### Nhân sự

```
"Thêm Minh vào team, lập trình viên, nhóm Tech"
"Bách đang ôm bao nhiêu task?"
"Danh sách nhân sự nhóm Media"
"Giao thêm task deadline thứ 5 cho Bách có ổn không?"
```

### Nhắc nhở

```
"Nhắc tôi 3h chiều họp với khách hàng"
"Nhắc Bách ngày mai 9h gửi báo cáo"
"Xem danh sách reminder"
"Xóa reminder số 3"
```

### Lịch review

```
"Thêm lịch briefing sáng lúc 7:30"
"Thêm lịch custom lúc 12:00: liệt kê task quá hạn và cảnh báo workload"
"Xem lịch review của tôi"
"Tắt lịch review số 2"
"Xóa lịch review số 1"
```

### Reset workspace

```
/reset
→ Bot: Gõ tên công ty bằng CHỮ HOA để xác nhận...
→ Bạn: ACME CORP
→ Bot: Gõ "tôi chắc chắn" để tiến hành xóa...
→ Bạn: tôi chắc chắn
→ Bot: Reset hoàn tất. Đã xóa X records...
```

---

## Lark Base

Mỗi công ty có 1 Lark Base riêng với **6 bảng**:

| Bảng | Nội dung |
|------|----------|
| **People** | Nhân sự: tên, Chat ID, vai trò, kỹ năng |
| **Tasks** | Công việc: assignee, deadline, priority, status |
| **Projects** | Dự án: người phụ trách, deadline, trạng thái |
| **Ideas** | Ý tưởng: nội dung, tags, project |
| **Reminders** | Nhắc nhở (sync 2 chiều với bot) |
| **Notes** | Ghi chú nội bộ của bot |

Dữ liệu thay đổi qua bot tự cập nhật lên Lark ngay lập tức. Reminders sửa trên Lark sẽ sync về bot mỗi 30 giây.

---

## Báo cáo tự động (mặc định)

| Thời gian | Nội dung |
|-----------|----------|
| **8:00 sáng** | Briefing: task hôm nay, deadline sắp tới, cảnh báo quá tải |
| **9:30 sáng** | Nhắc deadline ngày mai + cảnh báo task quá hạn cho assignee |
| **5:00 chiều** | Tổng kết cuối ngày |
| **Mỗi phút** | Gửi reminder đến giờ |
| **Mỗi 30 phút** | Push nhắc assignee khi task còn 24h / 2h |

> Lịch mặc định (8h, 17h) có thể tắt bật hoặc thêm lịch mới qua chat bất cứ lúc nào.

---

## Cài đặt

### Yêu cầu

- Docker & Docker Compose
- Telegram Bot Token ([BotFather](https://t.me/BotFather))
- Lark Suite App (App ID + App Secret) — [Lark Developer Console](https://open.larksuite.com/)
- OpenAI API Key
- Cohere API Key (reranking)

### Chạy

```bash
# 1. Clone
git clone <repo-url> && cd <repo>

# 2. Setup môi trường
./scripts/setup.sh

# 3. Điền API keys
nano .env

# 4. Khởi chạy
./scripts/start.sh
```

### Quản lý

```bash
./scripts/status.sh    # Trạng thái
./scripts/logs.sh      # Log realtime
./scripts/restart.sh   # Khởi động lại
./scripts/stop.sh      # Dừng
python scripts/backup.py  # Backup SQLite
```

### Biến môi trường (`.env`)

```env
TELEGRAM_BOT_TOKEN=...
LARK_APP_ID=...
LARK_APP_SECRET=...
OPENAI_API_KEY=...
OPENAI_CHAT_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
COHERE_API_KEY=...
QDRANT_URL=http://qdrant:6333
DB_PATH=data/history.db
TIMEZONE=Asia/Ho_Chi_Minh
```

---

## Kiến trúc

```
Telegram ←→ FastAPI (Polling)
              │
              ├── agent.py          ← Secretary Agent (33 tools)
              ├── advisor.py        ← Advisor Agent (11 read-only tools)
              ├── onboarding.py     ← Luồng đăng ký + join company
              ├── scheduler.py      ← APScheduler: review, reminder, deadline push
              │
              ├── src/db.py         ← SQLite (aiosqlite)
              │     bosses, memberships, people_map, group_map
              │     messages, notes, reminders, token_usage
              │     pending_approvals, task_notifications, scheduled_reviews
              │
              ├── src/services/
              │     lark.py         ← Lark Base API (6 tables per workspace)
              │     qdrant.py       ← Vector search (tasks + messages)
              │     openai_client.py← Chat + embeddings
              │     telegram.py     ← Send / edit messages
              │
              └── src/tools/        ← 33 tool functions
                    tasks.py        ← CRUD + approval flow + auto-notify
                    people.py       ← CRUD + workload check
                    projects.py     ← CRUD
                    reminder.py     ← CRUD + Lark sync
                    review_config.py← Scheduled review CRUD
                    reset.py        ← 2-step workspace reset
                    note.py         ← Internal notes
                    summary.py      ← Reports
                    ...
```

### Data flow

```
User message
  → agent.py: resolve workspace context (multi-membership)
  → save message to SQLite + Qdrant (async)
  → build context: 15 recent + 8 RAG + people summary
  → Claude tool loop (max 10 rounds)
  → execute tools → read/write Lark Base
  → reply to user
  → save reply to SQLite + Qdrant (async)
```

---

## Tests

```bash
python -m pytest tests/ -v
# 47 tests: unit (schema, context, lark, onboarding) + integration (approvals, reviews, reset)
```

---

## Bảo mật

- Mỗi workspace hoàn toàn tách biệt — sếp A không thấy dữ liệu sếp B
- Member/partner chỉ thao tác được task của mình, mọi thay đổi cần boss duyệt
- Reset workspace yêu cầu 2 bước xác nhận để tránh xóa nhầm
- SQL injection được phòng ngừa bằng whitelist cột trong các hàm dynamic UPDATE
