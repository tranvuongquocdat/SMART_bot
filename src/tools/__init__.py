import json

from src.context import ChatContext
from src.tools import (
    tasks,
    people,
    projects,
    ideas,
    note,
    memory,
    summary,
    messaging,
    reminder,
    review_config,
    web_search,
    join,
    reset,
)
from src.tools import workspace as workspace_tools
from src.tools import group as group_tools
from src.tools import communication
from src.tools import search as search_tools


# ---------------------------------------------------------------------------
# Tool definitions — 29 tools
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    # ------------------------------------------------------------------
    # Task tools (5)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Tạo task mới. Dùng khi sếp giao việc, ví dụ: 'giao Bách thiết kế logo deadline thứ 6'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên task ngắn gọn, tóm tắt nội dung việc cần làm"},
                    "assignee": {"type": "string", "description": "Tên người được giao (dùng đúng tên trong danh sách nhân sự)"},
                    "deadline": {"type": "string", "description": "Deadline dạng YYYY-MM-DD. Nếu sếp nói 'thứ 6', 'tuần sau', tự quy đổi ra ngày cụ thể"},
                    "priority": {
                        "type": "string",
                        "enum": ["Cao", "Trung bình", "Thấp"],
                        "description": "Độ ưu tiên. Mặc định Trung bình nếu không nói rõ",
                    },
                    "project": {"type": "string", "description": "Tên dự án liên quan (dùng đúng tên dự án đã tạo)"},
                    "start_time": {"type": "string", "description": "Ngày bắt đầu dạng YYYY-MM-DD (nếu có)"},
                    "location": {"type": "string", "description": "Địa điểm thực hiện (nếu có)"},
                    "original_message": {"type": "string", "description": "Tin nhắn gốc mà sếp forward/trích dẫn (nếu có)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Liệt kê task có lọc. Dùng khi: 'hôm nay có gì?', 'task của Bách', 'task dự án X'. Gọi không tham số = tất cả task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Lọc theo tên người được giao (tìm gần đúng)"},
                    "status": {
                        "type": "string",
                        "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"],
                        "description": "Lọc theo trạng thái task",
                    },
                    "project": {"type": "string", "description": "Lọc theo tên dự án (tìm gần đúng)"},
                    "workspace_ids": {
                        "type": "string",
                        "description": "Which workspaces to query. 'current' (default) = active workspace only. 'all' = all workspaces this user belongs to. Pass 'all' for personal queries like 'what are my tasks' that span workspaces.",
                        "default": "current",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Cập nhật task. Dùng khi: 'done task X', 'dời deadline', 'chuyển task cho Y'. Tìm task theo tên rồi cập nhật.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm trong TÊN task (ví dụ: 'thiết kế logo')"},
                    "status": {
                        "type": "string",
                        "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"],
                        "description": "Trạng thái mới",
                    },
                    "deadline": {"type": "string", "description": "Deadline mới dạng YYYY-MM-DD"},
                    "priority": {
                        "type": "string",
                        "enum": ["Cao", "Trung bình", "Thấp"],
                        "description": "Độ ưu tiên mới",
                    },
                    "assignee": {"type": "string", "description": "Chuyển task cho người khác"},
                    "name": {"type": "string", "description": "Đổi tên task"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Xóa task. LUÔN hỏi sếp xác nhận trước khi gọi. Tìm task theo tên rồi xóa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm trong TÊN task cần xóa"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Tìm task bằng semantic search (tìm theo nghĩa, không cần từ chính xác). Dùng khi: 'có task nào liên quan marketing?', 'task về khách hàng ABC'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa hoặc mô tả tìm kiếm"},
                },
                "required": ["query"],
            },
        },
    },
    # ------------------------------------------------------------------
    # People tools (6)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "add_people",
            "description": "Thêm người mới vào hệ thống nhân sự. Dùng khi sếp nói 'thêm Minh vào team', 'có nhân viên mới tên Lan'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên đầy đủ của người cần thêm"},
                    "chat_id": {"type": "integer", "description": "Chat ID Telegram (nếu biết). Thường chưa có, bỏ trống"},
                    "username": {"type": "string", "description": "Username Telegram (không có @ phía trước)"},
                    "group": {"type": "string", "description": "Nhóm / phòng ban, ví dụ: Tech, Media, Sale, Marketing"},
                    "person_type": {
                        "type": "string",
                        "enum": ["member", "partner", "customer"],
                        "description": "member = nhân viên, partner = đối tác, customer = khách hàng",
                    },
                    "role_desc": {"type": "string", "description": "Vai trò / chức vụ, ví dụ: Lập trình viên, Thiết kế, Quản lý"},
                    "skills": {"type": "string", "description": "Kỹ năng chuyên môn, ví dụ: React, Figma, SEO"},
                    "note": {"type": "string", "description": "Ghi chú thêm về người này"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_people",
            "description": "Xem thông tin chi tiết của một người. Dùng khi: 'Bách là ai?', 'thông tin của Linh'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên hoặc tên gọi (tìm gần đúng trong cả Tên và Tên gọi)"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_people",
            "description": "Liệt kê danh sách nhân sự, có thể lọc theo nhóm hoặc loại.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {"type": "string", "description": "Lọc theo nhóm / phòng ban"},
                    "person_type": {
                        "type": "string",
                        "enum": ["member", "partner", "customer"],
                        "description": "Lọc theo loại người dùng",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_people",
            "description": "Cập nhật thông tin của một người trong hệ thống.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên để tìm người cần cập nhật"},
                    "name": {"type": "string", "description": "Tên mới"},
                    "nickname": {"type": "string", "description": "Tên gọi mới"},
                    "group": {"type": "string", "description": "Nhóm mới"},
                    "role_desc": {"type": "string", "description": "Vai trò mới"},
                    "skills": {"type": "string", "description": "Kỹ năng mới"},
                    "note": {"type": "string", "description": "Ghi chú mới"},
                    "phone": {"type": "string", "description": "Số điện thoại"},
                    "username": {"type": "string", "description": "Username mới"},
                    "person_type": {"type": "string", "description": "Loại người dùng mới"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_people",
            "description": "Xóa người khỏi hệ thống. LUÔN hỏi sếp xác nhận trước khi gọi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên người cần xóa"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_effort",
            "description": "Kiểm tra workload của một người: liệt kê task đang làm, phát hiện xung đột/trùng deadline. GỌI TRƯỚC khi giao task mới cho ai đó.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Tên người cần kiểm tra (đúng tên trong danh sách nhân sự)"},
                    "deadline": {
                        "type": "string",
                        "description": "Deadline task mới dạng YYYY-MM-DD — nếu có, sẽ so sánh với các task hiện tại để phát hiện xung đột",
                    },
                    "workspace_ids": {
                        "type": "string",
                        "description": "Which workspaces to query. 'current' (default) = active workspace only. 'all' = all workspaces this user belongs to. Pass 'all' for personal queries like 'what are my tasks' that span workspaces.",
                        "default": "current",
                    },
                },
                "required": ["assignee"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Project tools (5)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "Tạo dự án mới trong hệ thống.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên dự án"},
                    "description": {"type": "string", "description": "Mô tả dự án"},
                    "lead": {"type": "string", "description": "Người phụ trách"},
                    "members": {"type": "string", "description": "Danh sách thành viên"},
                    "deadline": {"type": "string", "description": "Deadline dạng YYYY-MM-DD"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "Xem thông tin chi tiết dự án kèm danh sách task liên quan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên dự án cần xem"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Liệt kê tất cả dự án, có thể lọc theo trạng thái.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Lọc theo trạng thái (Planning, Active, Done, v.v.)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_project",
            "description": "Cập nhật thông tin dự án.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên dự án cần cập nhật"},
                    "name": {"type": "string", "description": "Tên mới"},
                    "description": {"type": "string", "description": "Mô tả mới"},
                    "lead": {"type": "string", "description": "Người phụ trách mới"},
                    "members": {"type": "string", "description": "Thành viên mới"},
                    "deadline": {"type": "string", "description": "Deadline mới dạng YYYY-MM-DD"},
                    "status": {"type": "string", "description": "Trạng thái mới"},
                },
                "required": ["search_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_project",
            "description": "Xóa dự án khỏi hệ thống. LUÔN hỏi sếp xác nhận trước khi gọi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên dự án cần xóa"},
                },
                "required": ["search_name"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Note tools (2)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Lưu ghi chú nội bộ (chỉ bot dùng, user không thấy). Gọi khi biết thêm thông tin quan trọng cần nhớ lâu dài, ví dụ: 'Bách nghỉ phép tuần sau', 'dự án X bị delay vì khách chưa duyệt'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {
                        "type": "string",
                        "enum": ["personal", "project", "group"],
                        "description": "personal = ghi chú về 1 người/sếp, project = về dự án, group = về nhóm chat",
                    },
                    "ref_id": {"type": "string", "description": "Khóa tham chiếu: tên người (vd 'Bách'), tên dự án (vd 'Rebranding'), hoặc ID nhóm"},
                    "content": {"type": "string", "description": "Nội dung ghi chú (ghi đè toàn bộ note cũ nếu có, nên gộp thông tin cũ + mới)"},
                },
                "required": ["note_type", "ref_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": "Đọc ghi chú nội bộ đã lưu. Dùng khi cần nhớ lại thông tin về người/dự án/nhóm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {
                        "type": "string",
                        "enum": ["personal", "project", "group"],
                        "description": "personal = về người/sếp, project = về dự án, group = về nhóm chat",
                    },
                    "ref_id": {"type": "string", "description": "Khóa tham chiếu (cùng giá trị đã dùng khi update_note)"},
                },
                "required": ["note_type", "ref_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Search tools (2)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": (
                "Tìm trong lịch sử chat bằng semantic search. Dùng khi: 'hôm trước nói gì về X?', 'ai nhắc đến khách hàng Y?'. "
                "scope: \"current_chat\" (mặc định) | \"all\" (tìm toàn bộ chat thuộc workspace)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa hoặc nội dung cần tìm"},
                    "scope": {"type": "string", "description": "\"current_chat\" (mặc định) hoặc \"all\""},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "Tìm kiếm ngữ nghĩa trong ghi chú và ý tưởng đã lưu. "
                "Dùng khi cần tìm lại thông tin đã lưu trong notes hoặc ideas. "
                "note_type: \"personal\" | \"group\" | \"project\" | \"idea\" | \"all\""
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "note_type": {"type": "string", "description": "\"all\" mặc định"},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Summary tools (2)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Tổng hợp báo cáo task theo ngày hoặc tuần. Dùng khi sếp muốn brief tình hình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_type": {
                        "type": "string",
                        "enum": ["today", "week"],
                        "description": "Loại tóm tắt",
                    },
                    "assignee": {"type": "string", "description": "Lọc theo người (để trống = tất cả)"},
                },
                "required": ["summary_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workload",
            "description": "Xem workload (khối lượng task đang làm) theo người. Dùng khi sếp hỏi 'ai đang bận?', 'X ôm bao nhiêu task?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Tên người cần xem. Để trống = xem tất cả."},
                },
                "required": [],
            },
        },
    },
    # ------------------------------------------------------------------
    # Idea tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_idea",
            "description": "Lưu ý tưởng nhanh vào hệ thống. Dùng khi sếp nói 'lưu ý tưởng', 'idea', hoặc đề cập ý tưởng mới.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung ý tưởng (ghi lại nguyên văn hoặc tóm tắt ý chính)"},
                    "tags": {"type": "string", "description": "Tag phân loại, phân cách bằng dấu phẩy. Ví dụ: marketing, content, product"},
                    "project": {"type": "string", "description": "Tên dự án liên quan (nếu có, dùng đúng tên dự án đã tạo)"},
                },
                "required": ["content"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Messaging tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Gửi tin nhắn Telegram thay sếp. Tra tên người nhận trong danh sách nhân sự để lấy Chat ID. Dùng khi: 'nhắn Bách mai 9h họp', 'gửi Linh file thiết kế'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Tên người nhận (tìm gần đúng trong danh sách nhân sự)"},
                    "content": {"type": "string", "description": "Nội dung tin nhắn gửi đi (viết hoàn chỉnh, lịch sự)"},
                },
                "required": ["to", "content"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Reminder tools (4)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Tạo nhắc nhở vào một thời điểm cụ thể. Có thể nhắc sếp hoặc nhắc người khác trong team.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung nhắc nhở"},
                    "remind_at": {
                        "type": "string",
                        "description": "Thời gian nhắc dạng YYYY-MM-DD HH:MM theo giờ địa phương (timezone app, mặc định Asia/Ho_Chi_Minh)",
                    },
                    "target": {
                        "type": "string",
                        "description": "Tên người cần nhắc. Để trống = nhắc sếp.",
                    },
                },
                "required": ["content", "remind_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": (
                "Liệt kê nhắc nhở của workspace sếp (pending = chưa tới giờ gửi; done = đã gửi). "
                "Gọi trước khi nói 'không có reminder' hoặc khi sếp hỏi lịch nhắc / muốn sửa xóa theo ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "done", "all"],
                        "description": "pending (mặc định), done, hoặc all",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số dòng tối đa (mặc định 30, tối đa 200)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_reminder",
            "description": "Sửa nhắc nhở theo ID (lấy từ list_reminders). Chỉ truyền các field cần đổi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer", "description": "ID nhắc nhở"},
                    "content": {"type": "string", "description": "Nội dung mới (bỏ qua nếu không đổi)"},
                    "remind_at": {
                        "type": "string",
                        "description": "Thời gian mới YYYY-MM-DD HH:MM giờ địa phương (bỏ qua nếu không đổi)",
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Người nhận: tên trên Lark. Chuỗi rỗng = chỉ nhắc sếp. "
                            "Bỏ qua field này = giữ nguyên người nhận."
                        ),
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "Xóa nhắc nhở theo ID (lấy từ list_reminders).",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer"},
                },
                "required": ["reminder_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Review schedule config tools (4)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "add_review_schedule",
            "description": "Thêm lịch review tự động (briefing sáng, tổng kết chiều, hoặc tuỳ chỉnh). Sếp dùng khi muốn nhận báo cáo định kỳ vào giờ cố định.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron_time": {"type": "string", "description": "Giờ dạng HH:MM, ví dụ: 08:00, 17:30"},
                    "content_type": {
                        "type": "string",
                        "enum": ["morning_brief", "evening_summary", "custom", "group_brief"],
                        "description": "Loại nội dung: morning_brief = briefing sáng, evening_summary = tổng kết chiều, custom = tuỳ chỉnh theo prompt, group_brief = briefing gửi vào nhóm",
                    },
                    "group_chat_id": {
                        "type": "integer",
                        "description": "ID nhóm Telegram để gửi group_brief (chỉ dùng khi content_type = group_brief). Để trống = gửi DM sếp.",
                    },
                    "custom_prompt": {
                        "type": "string",
                        "description": "Prompt tuỳ chỉnh (chỉ dùng khi content_type = custom). Ví dụ: 'Liệt kê task quá hạn và workload team'",
                    },
                },
                "required": ["cron_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_review_schedules",
            "description": "Xem danh sách lịch review tự động đang được cấu hình.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_review",
            "description": "Bật hoặc tắt một lịch review theo ID (lấy từ list_review_schedules).",
            "parameters": {
                "type": "object",
                "properties": {
                    "review_id": {"type": "integer", "description": "ID lịch review"},
                    "enabled": {"type": "boolean", "description": "true = bật, false = tắt"},
                },
                "required": ["review_id", "enabled"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_review_schedule",
            "description": "Xoá một lịch review theo ID. LUÔN hỏi xác nhận trước khi gọi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "review_id": {"type": "integer", "description": "ID lịch review cần xoá"},
                },
                "required": ["review_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Web Search tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Tìm kiếm thông tin trên web. Dùng khi sếp hỏi thông tin thời sự, tra cứu dữ liệu bên ngoài.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa tìm kiếm"},
                },
                "required": ["query"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Advisor tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "escalate_to_advisor",
            "description": (
                "Chuyển sang Cố vấn chiến lược khi sếp hỏi phân tích tổng thể, sắp xếp nhân sự, so sánh phương án. "
                "Ví dụ: 'sắp xếp nhân sự Q3', 'phân tích workload team xem ai quá tải'. "
                "KHÔNG gọi cho CRUD đơn giản (tạo/xem/sửa/xóa task, người, dự án)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Lý do cần leo thang sang Advisor"},
                },
                "required": ["reason"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Note tools — append_note (new)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "append_note",
            "description": "Add new information to an existing note without overwriting. Use this when you learn something new about a person, project, or group — it preserves existing knowledge. Use update_note only when reorganizing stale content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {"type": "string", "enum": ["personal", "project", "group"]},
                    "ref_id": {"type": "string", "description": "Reference key (person name, project name, or group id)"},
                    "content": {"type": "string", "description": "New information to append"},
                },
                "required": ["note_type", "ref_id", "content"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Approval tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_pending_approvals",
            "description": "Lists all pending approvals: task change requests from members and join requests to this workspace. Call this when someone asks about pending items or when you need to know what approval_id to use.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_task_change",
            "description": "Approve a pending task change request from a member. Use list_pending_approvals to get the approval_id first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "integer", "description": "ID from list_pending_approvals"},
                },
                "required": ["approval_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_task_change",
            "description": "Reject a pending task change request from a member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_id": {"type": "integer"},
                },
                "required": ["approval_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Join flow tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_available_workspaces",
            "description": "Returns workspaces this user can request to join (not already a member). Useful when someone wants to collaborate with another company.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_join",
            "description": "Send a join request to another workspace. The target boss will be notified and can approve or reject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_boss_id": {"type": "integer", "description": "Boss ID from list_available_workspaces"},
                    "role": {"type": "string", "enum": ["member", "partner"], "description": "Role being requested"},
                    "intro": {"type": "string", "description": "Brief introduction / reason for joining"},
                },
                "required": ["target_boss_id", "role", "intro"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_join",
            "description": "Approve a join request to this workspace. The person will be added to the team and written to the People table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "membership_chat_id": {"type": "string", "description": "chat_id of the person to approve (from list_pending_approvals)"},
                    "role": {"type": "string", "enum": ["member", "partner"], "description": "Role to assign (overrides requested role if specified)"},
                },
                "required": ["membership_chat_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_join",
            "description": "Reject a join request. The person will be notified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "membership_chat_id": {"type": "string"},
                },
                "required": ["membership_chat_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Reset tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "initiate_reset",
            "description": "Start the workspace reset flow. Only call when the boss clearly wants to delete all workspace data and start fresh. This begins a 3-step confirmation.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_reset_step1",
            "description": "Second step of reset: validate the company name the boss typed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_input": {"type": "string", "description": "Exact text the user typed"},
                },
                "required": ["user_input"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_reset",
            "description": "Final step of reset: execute nuclear deletion after boss types confirmation phrase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {"type": "string", "description": "The confirmation phrase typed by boss"},
                },
                "required": ["confirmation"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Group tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "summarize_group_conversation",
            "description": "Summarize recent group messages: main topic, decisions made, action items. Call when asked to recap a meeting or conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n_messages": {"type": "integer", "description": "Number of recent messages to summarize (default 20)", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_group_note",
            "description": "Write or append to the group's persistent note. Use to record decisions, group rules, or context that should be remembered across sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "description": "True (default) = append; False = overwrite", "default": True},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast_to_group",
            "description": "Send a message to the group chat. Use for team announcements, deadline alerts, or approval results that the whole team should see.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_group",
            "description": "Manage the Telegram group: invite member, rename, pin/unpin messages, kick member, set description, or generate invite link. Requires bot to be admin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["invite", "rename", "pin", "unpin", "kick", "set_description", "invite_link"],
                    },
                    "name": {"type": "string", "description": "Person name (for invite/kick)"},
                    "title": {"type": "string", "description": "New group name (for rename)"},
                    "message_id": {"type": "integer", "description": "Message ID to pin"},
                    "text": {"type": "string", "description": "Description text (for set_description)"},
                },
                "required": ["action"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Workspace & language tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": "Persist the language preference for this user. Call when the user requests a specific language or switches mid-conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language_code": {"type": "string", "description": "BCP-47 language code, e.g. 'en', 'vi', 'ja'"},
                },
                "required": ["language_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_workspace",
            "description": (
                "Chuyển workspace đang hoạt động. Dùng khi user có nhiều workspace và muốn làm việc ở workspace cụ thể. "
                "Truyền tên workspace (fuzzy match) hoặc boss_id. Lưu vào DB lâu dài."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Tên workspace (tìm gần đúng)"},
                    "boss_id": {"type": "integer", "description": "boss_id cụ thể (nếu biết)"},
                },
                "required": [],
            },
        },
    },
    # ------------------------------------------------------------------
    # Communication tools (3)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "send_dm",
            "description": (
                "Gửi tin nhắn riêng (DM) cho một người trong team theo tên. "
                "Dùng khi sếp muốn nhắn riêng ai đó — kể cả khi đang ở group. "
                "Tự động log vào lịch sử liên lạc. "
                "Nếu đang ở group, ưu tiên tìm người thuộc workspace của group đó trước."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Tên người nhận"},
                    "content": {"type": "string", "description": "Nội dung tin nhắn"},
                    "context": {"type": "string", "description": "Ngữ cảnh tùy chọn (vd: tên task liên quan)"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) hoặc \"all\""},
                },
                "required": ["to", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast",
            "description": (
                "Gửi thông báo hàng loạt cho nhiều người qua DM cá nhân. "
                "targets: \"all_members\" | \"all_partners\" | \"all\" | tên cụ thể cách nhau dấu phẩy. "
                "Hoạt động từ cả DM lẫn group. Dùng check_team_engagement trước để biết ai có Chat ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "targets": {"type": "string", "description": "\"all_members\" | \"all_partners\" | \"all\" | \"Tên A, Tên B\""},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_communication_log",
            "description": (
                "Tra lịch sử tất cả tin nhắn bot đã chủ động gửi cho ai đó. "
                "GỌI TRƯỚC khi trả lời 'đã nhắn X chưa' hoặc 'đã push deadline chưa'. "
                "Trả về timeline đầy đủ: DM thủ công, thông báo giao task, nhắc deadline, reminder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person": {"type": "string", "description": "Tên người cần tra (bỏ trống = xem tất cả)"},
                    "since": {"type": "string", "description": "Từ ngày YYYY-MM-DD (tùy chọn)"},
                    "log_type": {"type": "string", "description": "\"all\" | \"manual\" | \"task_assigned\" | \"deadline_push\" | \"reminder\""},
                    "workspace_ids": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool router
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: str | dict, ctx: ChatContext) -> str:
    try:
        args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        return await _dispatch_tool(name, args_dict, ctx)
    except Exception as e:
        err_type = type(e).__name__
        msg = str(e)
        if any(kw in msg.lower() for kw in ("lark", "base_token", "table", "record")):
            return (
                f"[TOOL_ERROR:lark] {name} — Lark không phản hồi hoặc cấu hình sai: {msg}. "
                f"Thử lại hoặc báo người dùng."
            )
        if any(kw in msg.lower() for kw in ("not found", "không tìm thấy", "no such")):
            return (
                f"[TOOL_ERROR:not_found] {name} — {msg}. "
                f"Hãy hỏi lại người dùng tên chính xác."
            )
        return f"[TOOL_ERROR:unknown] {name} thất bại ({err_type}): {msg}"


async def _dispatch_tool(name: str, args: dict, ctx: ChatContext) -> str:
    match name:
        # Task tools
        case "create_task":
            return await tasks.create_task(ctx, **args)
        case "list_tasks":
            return await tasks.list_tasks(ctx, **args)
        case "update_task":
            return await tasks.update_task(ctx, **args)
        case "delete_task":
            return await tasks.delete_task(ctx, **args)
        case "search_tasks":
            return await tasks.search_tasks(ctx, **args)

        # People tools
        case "add_people":
            return await people.add_people(ctx, **args)
        case "get_people" | "get_person":
            return await people.get_person(ctx, **args)
        case "list_people":
            return await people.list_people(ctx, **args)
        case "update_people":
            return await people.update_people(ctx, **args)
        case "delete_people":
            return await people.delete_people(ctx, **args)
        case "check_effort":
            return await people.check_effort(ctx, **args)
        case "check_team_engagement":
            return await people.check_team_engagement(ctx, **args)

        # Project tools
        case "create_project":
            return await projects.create_project(ctx, **args)
        case "get_project":
            return await projects.get_project(ctx, **args)
        case "list_projects":
            return await projects.list_projects(ctx, **args)
        case "update_project":
            return await projects.update_project(ctx, **args)
        case "delete_project":
            return await projects.delete_project(ctx, **args)

        # Note tools
        case "update_note":
            return await note.update_note(ctx, **args)
        case "get_note":
            return await note.get_note(ctx, **args)

        # Search tools
        case "search_history":
            return await search_tools.search_history(ctx, **args)
        case "search_notes":
            return await search_tools.search_notes(ctx, **args)

        # Summary tools
        case "get_summary":
            return await summary.get_summary(ctx, **args)
        case "get_workload":
            return await summary.get_workload(ctx, **args)

        # Idea tools
        case "create_idea":
            return await ideas.create_idea(ctx, **args)

        # Messaging tools
        case "send_message":
            return await messaging.send_message(ctx, **args)

        # Reminder tools
        case "create_reminder":
            return await reminder.create_reminder(ctx, **args)
        case "list_reminders":
            return await reminder.list_reminders(ctx, **args)
        case "update_reminder":
            return await reminder.update_reminder(ctx, **args)
        case "delete_reminder":
            return await reminder.delete_reminder(ctx, **args)

        # Review schedule config tools
        case "add_review_schedule":
            return await review_config.add_review_schedule(ctx, **args)
        case "list_review_schedules":
            return await review_config.list_review_schedules(ctx)
        case "toggle_review":
            return await review_config.toggle_review(ctx, **args)
        case "delete_review_schedule":
            return await review_config.delete_review_schedule(ctx, **args)

        # Web search tools
        case "web_search":
            return await web_search.web_search(**args)

        # Advisor escalation
        case "escalate_to_advisor":
            return "__ESCALATE__"

        # Note — append
        case "append_note":
            return await note.append_note(ctx, **args)

        # Approval tools
        case "list_pending_approvals":
            return await memory.list_pending_approvals(ctx)
        case "approve_task_change":
            return await tasks.approve_task_change(ctx, **args)
        case "reject_task_change":
            return await tasks.reject_task_change(ctx, **args)

        # Join flow tools
        case "list_available_workspaces":
            return await join.list_available_workspaces(ctx)
        case "request_join":
            return await join.request_join(ctx, **args)
        case "approve_join":
            return await join.approve_join(ctx, **args)
        case "reject_join":
            return await join.reject_join(ctx, **args)

        # Reset tools
        case "initiate_reset":
            return await reset.initiate_reset(ctx)
        case "confirm_reset_step1":
            return await reset.confirm_reset_step1(ctx, **args)
        case "execute_reset":
            return await reset.execute_reset(ctx, **args)

        # Group tools
        case "summarize_group_conversation":
            return await group_tools.summarize_group_conversation(ctx, **args)
        case "update_group_note":
            return await group_tools.update_group_note(ctx, **args)
        case "broadcast_to_group":
            return await group_tools.broadcast_to_group(ctx, **args)
        case "manage_group":
            return await group_tools.manage_group(ctx, **args)

        # Communication tools
        case "send_dm":
            return await communication.send_dm(ctx, **args)
        case "broadcast":
            return await communication.broadcast(ctx, **args)
        case "get_communication_log":
            return await communication.get_communication_log(ctx, **args)

        # Workspace & language tools
        case "set_language":
            return await workspace_tools.set_language(ctx, **args)
        case "switch_workspace":
            return await workspace_tools.switch_workspace(ctx, **args)

        case _:
            return f"Tool '{name}' không tồn tại."
