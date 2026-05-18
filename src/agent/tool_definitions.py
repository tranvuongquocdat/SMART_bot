"""OpenAI tool schemas — pure data, no logic, no imports of tool functions.

Phase 4b-2 will add new entries (or move them) as tools are migrated to
handler classes. Phase 4b-3 will rename this module to `agent/tool_definitions.py`.
"""
from __future__ import annotations



TOOL_DEFINITIONS = [
    # ------------------------------------------------------------------
    # Task tools (5)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Tạo task mới. Dùng khi sếp giao việc, ví dụ: 'giao Bách thiết kế logo deadline thứ 6'. Gọi get_person trước để check effort_score. Nếu effort_score > 0.8 (gần overload), hỏi sếp xác nhận trước khi giao thêm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên task ngắn gọn, tóm tắt nội dung việc cần làm"},
                    "assignee": {"type": "string", "description": "Tên người được giao. Nếu chưa có trong Lark, gọi add_people thêm trước (Chat ID không bắt buộc)."},
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
            "description": "Liệt kê task có lọc. Dùng khi: 'hôm nay có gì?', 'task của Bách', 'task dự án X'. Gọi không tham số = tất cả task. Khi gọi từ group, mặc định lọc theo project gắn với group đó.",
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
            "description": "Cập nhật task. Dùng khi: 'done task X', 'dời deadline', 'chuyển task cho Y'. Tìm task theo tên rồi cập nhật. Status phải là một trong: Mới, Đang làm, Hoàn thành, Huỷ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Substring của TÊN task (không phải cả câu user nói). Match bằng lowercase substring, không phải fuzzy/semantic — tự trích phần lõi từ câu user (vd user nói 'Task check bot đã xong' thì truyền 'check bot'). Nếu không match: thử keyword ngắn hơn hoặc gọi list_tasks/search_tasks để lấy tên chính xác."},
                    "status": {
                        "type": "string",
                        "enum": ["Mới", "Đang làm", "Hoàn thành", "Huỷ"],
                        "description": "Trạng thái mới. Phải là chính xác một trong các giá trị enum.",
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
                    "search_keyword": {"type": "string", "description": "Substring của TÊN task. Match lowercase substring, không fuzzy — trích phần lõi từ câu user, không truyền cả câu."},
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
                    "chat_id": {"type": "integer", "description": "Chat ID kênh đã DM bot (Telegram/Zalo/...). Khi sếp thêm thủ công thường chưa có, bỏ trống."},
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
            "description": (
                "Xem thông tin chi tiết của một người — trả fat return gồm: "
                "profile, tasks đang làm (tối đa 5), effort_score (0-1, > 0.8 = gần overload), "
                "lịch sử DM bot gần nhất, has_dmd_bot flag. "
                "Dùng khi: 'Bách là ai?', 'Bách đang bận không?', trước khi giao task cho ai. "
                "Nếu nhiều người cùng tên, trả tất cả kèm workspace tag."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên hoặc tên gọi (tìm gần đúng trong cả Tên và Tên gọi)"},
                    "workspace_ids": {
                        "type": "string",
                        "description": "\"current\" (mặc định) hoặc \"all\" để tìm across workspaces.",
                        "default": "current",
                    },
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
            "description": "Tạo dự án mới trong hệ thống. Status mặc định là 'Chưa bắt đầu'. Các giá trị hợp lệ: Chưa bắt đầu, Đang thực hiện, Hoàn thành, Tạm dừng, Huỷ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên dự án"},
                    "description": {"type": "string", "description": "Mô tả dự án"},
                    "lead": {"type": "string", "description": "Người phụ trách"},
                    "members": {"type": "string", "description": "Danh sách thành viên"},
                    "deadline": {"type": "string", "description": "Deadline dạng YYYY-MM-DD"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định)", "default": "current"},
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
                    "workspace_ids": {
                        "type": "string",
                        "description": "\"current\" (default) | \"all\" = aggregate across all workspaces this user belongs to.",
                        "default": "current",
                    },
                },
                "required": ["summary_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workload",
            "description": "Xem workload (khối lượng task đang làm) theo người. Dùng khi sếp hỏi 'ai đang bận?', 'X ôm bao nhiêu task?'. Mặc định workspace_ids='all' để thấy tổng workload thật sự.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Tên người cần xem. Để trống = xem tất cả."},
                    "workspace_ids": {
                        "type": "string",
                        "description": "\"all\" (mặc định) = toàn bộ workspaces. \"current\" = workspace hiện tại.",
                        "default": "all",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_team_engagement",
            "description": (
                "Kiểm tra trạng thái kết nối + workload của từng thành viên trong Lark People: "
                "ai đã kết nối với bot (có Chat ID trong Lark = bot ↔ người đã liên lạc được), "
                "ai chưa kết nối, ai đang overload. "
                "Gọi khi hỏi 'ai đã/chưa nhắn với bot', 'ai đang bận', hoặc trước broadcast."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) hoặc \"all\"", "default": "current"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_report",
            "description": (
                "Tạo báo cáo tổng quan dự án bằng LLM: % tiến độ, tasks theo status, "
                "ai đang chặn, deadline sắp tới. Dùng khi sếp hỏi 'báo cáo dự án X', 'tiến độ X thế nào?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Tên dự án cần báo cáo"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) hoặc \"all\"", "default": "current"},
                },
                "required": ["project"],
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
    # Reminder tools (4)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Tạo nhắc nhở vào một thời điểm cụ thể. Khi giờ tới, bot gửi cho người nhận (DM riêng nếu có Chat ID; fallback group nguồn hoặc báo sếp nếu chưa). Mỗi call tạo 1 reminder cho 1 đích (1 người hoặc sếp nếu target trống). Cần nhắc NHIỀU NGƯỜI: gọi tool này NHIỀU LẦN trong 1 turn — mỗi người một call, cùng `remind_at`. Nếu target chưa có Person row, gọi add_people trước (Chat ID không bắt buộc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung nhắc nhở"},
                    "remind_at": {
                        "type": "string",
                        "description": "Thời gian nhắc, định dạng YYYY-MM-DD HH:MM (giờ địa phương, mặc định Asia/Ho_Chi_Minh). Tự convert từ natural language như '9h30 sáng nay' dùng current_time trong context.",
                    },
                    "target": {
                        "type": "string",
                        "description": "Ai nhận nhắc. Để TRỐNG nếu nhắc chính sếp (bot sẽ DM riêng sếp). Chỉ truyền tên NGƯỜI KHÁC (member/partner trong team) khi muốn nhắc người đó — KHÔNG truyền 'tôi'/'chị'/'anh'/'sếp'/tên boss vào đây.",
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
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Mở 1 URL cụ thể để lấy nội dung. Dùng khi sếp paste link YouTube, "
                "TikTok, bài báo, blog → tool trả metadata (oEmbed) hoặc title + "
                "description + body rút gọn. KHÔNG dùng cho search keyword (đó là web_search). "
                "Sau khi gọi, đọc kết quả và tóm tắt cho sếp; không bịa nội dung khi tool báo lỗi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL đầy đủ (http/https)"},
                },
                "required": ["url"],
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
            "description": (
                "Approve a pending task-change request. Only call when the boss is replying "
                "to an approval prompt AND the supplied approval_id matches an existing pending "
                "task-change row in this workspace. The function refuses (no write) if no "
                "matching pending row exists."
            ),
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
            "description": (
                "Reject a pending task-change request. Only call when the boss is replying to "
                "an approval prompt AND the supplied approval_id matches an existing pending "
                "task-change row in this workspace. The function refuses (no write) if no "
                "matching pending row exists."
            ),
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
            "description": "Send a join request to another workspace. Always call list_available_workspaces first to get the target_boss_id. The target boss will be notified and can approve or reject.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_boss_id": {"type": "string", "description": "Boss ID from list_available_workspaces (the value AFTER 'boss_id:', not the list number)"},
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
            "description": (
                "Activate a pending join request as the boss of THIS workspace. Only call when "
                "the boss is replying to an approval prompt AND the supplied membership_chat_id "
                "matches an existing pending row in this workspace. The function refuses (no "
                "write) if no matching pending row exists."
            ),
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
            "description": (
                "Reject a pending join request as the boss of THIS workspace. Only call when "
                "the boss is replying to an approval prompt AND the supplied membership_chat_id "
                "matches an existing pending row. The function refuses (no write) if no "
                "matching pending row exists."
            ),
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
            "description": "Step 2 of workspace reset: validate the company name the boss typed. Call after initiate_reset once the boss has typed the company name.",
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
    {
        "type": "function",
        "function": {
            "name": "resolve_person",
            "description": (
                "Tra tất cả ứng viên người khớp query (tên/nickname/chat_id). "
                "Trả về nhiều nguồn: lark_people, bosses, memberships, seen_contacts — kèm source tag. "
                "GỌI TRƯỚC khi trả 'không tìm thấy X' hoặc 'X chưa có Chat ID' — "
                "có thể hệ thống đã biết chat_id của X qua nguồn khác."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Tên, nickname, hoặc chat_id số"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) | \"all\""},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_contact_to_person",
            "description": (
                "Gắn chat_id vào trường Chat ID của 1 Lark People record đang thiếu. "
                "Dùng khi xác định được seen_contacts/bosses chính là record Lark nào. "
                "Fails loud nếu record đã có Chat ID khác — phải hỏi sếp xác nhận trước khi overwrite."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "integer", "description": "Chat ID Telegram (số) cần gắn"},
                    "lark_record_id": {"type": "string", "description": "record_id của Lark People record đích"},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["chat_id", "lark_record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unlinked_contacts",
            "description": (
                "Liệt kê chat_id bot đã thấy trong group/DM (Telegram) nhưng CHƯA gắn "
                "vào Lark People record nào của workspace hiện tại. Dùng khi sếp hỏi "
                "'ai trong group mà chưa add', hoặc khi cần proactively propose linking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Xem trong N ngày qua (mặc định 30)"},
                    "limit": {"type": "integer", "description": "Tối đa N mục (mặc định 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_admins",
            "description": (
                "Trả danh sách admin của group hiện tại kèm chat_id. "
                "Chỉ chạy trong context group. Không list được non-admin members "
                "(Telegram API không cho phép)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ------------------------------------------------------------------
    # Group-context tools (3) — only usable when ctx.is_group = True
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "summarize_group_conversation",
            "description": (
                "Tóm tắt N tin nhắn gần nhất trong group hiện tại — theo 3 mục: "
                "chủ đề chính, quyết định đã ra, action items chưa được giao. "
                "Chỉ chạy trong context group."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n_messages": {"type": "integer", "description": "Số tin nhắn lấy từ lịch sử group (mặc định 20)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_group_note",
            "description": (
                "Ghi/append vào group note — lưu quyết định, rule, context lặp lại của group. "
                "Chỉ chạy trong context group. Dùng khi cần nhớ lâu điều đã thống nhất trong nhóm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung cần ghi vào note"},
                    "append": {"type": "boolean", "description": "True = append vào note hiện có (mặc định); False = ghi đè"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast_to_group",
            "description": (
                "Gửi 1 tin nhắn công khai vào group hiện tại. Dùng cho thông báo team, "
                "broadcast deadline, kết quả duyệt. Chỉ chạy trong context group."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Nội dung thông báo"},
                },
                "required": ["message"],
            },
        },
    },
]
