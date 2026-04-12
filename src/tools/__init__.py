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
    web_search,
)


# ---------------------------------------------------------------------------
# Tool definitions — 26 tools
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    # ------------------------------------------------------------------
    # Task tools (5)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Tạo task mới trên Lark Base. Dùng khi sếp giao việc hoặc forward tin nhắn công việc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên task ngắn gọn"},
                    "assignee": {"type": "string", "description": "Người được giao việc"},
                    "deadline": {"type": "string", "description": "Deadline dạng YYYY-MM-DD"},
                    "priority": {
                        "type": "string",
                        "enum": ["Cao", "Trung bình", "Thấp"],
                        "description": "Độ ưu tiên",
                    },
                    "project": {"type": "string", "description": "Tên dự án liên quan"},
                    "start_time": {"type": "string", "description": "Thời gian bắt đầu dạng YYYY-MM-DD"},
                    "location": {"type": "string", "description": "Địa điểm thực hiện"},
                    "original_message": {"type": "string", "description": "Tin nhắn gốc sếp forward"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Lọc danh sách task. Dùng khi sếp hỏi 'hôm nay có gì?', 'task của ai?', v.v.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Lọc theo người được giao"},
                    "status": {
                        "type": "string",
                        "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"],
                        "description": "Lọc theo trạng thái",
                    },
                    "project": {"type": "string", "description": "Lọc theo dự án"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Cập nhật task (trạng thái, deadline, ưu tiên, assignee, tên). Dùng khi sếp nói 'done task X', 'dời deadline', v.v.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm task cần cập nhật"},
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
            "description": "Xóa task khỏi hệ thống. Dùng khi sếp muốn hủy/xóa task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm task cần xóa"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Tìm task theo nội dung bằng semantic search. Dùng khi sếp hỏi 'có task nào liên quan X không?'",
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
            "description": "Thêm người mới (nhân viên, đối tác, khách hàng) vào hệ thống.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên đầy đủ"},
                    "chat_id": {"type": "integer", "description": "Chat ID Telegram"},
                    "username": {"type": "string", "description": "Username Telegram"},
                    "group": {"type": "string", "description": "Nhóm / phòng ban"},
                    "person_type": {
                        "type": "string",
                        "enum": ["member", "partner", "customer"],
                        "description": "Loại người dùng",
                    },
                    "role_desc": {"type": "string", "description": "Vai trò / chức vụ"},
                    "skills": {"type": "string", "description": "Kỹ năng"},
                    "note": {"type": "string", "description": "Ghi chú"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_people",
            "description": "Xem thông tin chi tiết của một người.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "Tên hoặc tên gọi để tìm"},
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
            "description": "Xóa một người khỏi hệ thống.",
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
            "description": "Kiểm tra workload/effort của một người, phát hiện xung đột deadline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Tên người cần kiểm tra"},
                    "deadline": {
                        "type": "string",
                        "description": "Deadline cần so sánh dạng YYYY-MM-DD (tùy chọn)",
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
            "description": "Xóa dự án khỏi hệ thống.",
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
            "description": "Cập nhật ghi chú về người, dự án, hoặc bất kỳ đối tượng nào. Gọi khi biết thêm thông tin mới cần lưu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {
                        "type": "string",
                        "description": "Loại note (person / project / general)",
                    },
                    "ref_id": {"type": "string", "description": "ID tham chiếu (tên người, tên dự án, v.v.)"},
                    "content": {"type": "string", "description": "Nội dung ghi chú mới"},
                },
                "required": ["note_type", "ref_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": "Lấy ghi chú đã lưu về một người hoặc dự án.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type": {
                        "type": "string",
                        "description": "Loại note (person / project / general)",
                    },
                    "ref_id": {"type": "string", "description": "ID tham chiếu"},
                },
                "required": ["note_type", "ref_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Memory tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "Tìm trong lịch sử hội thoại bằng semantic search. Dùng khi sếp hỏi về cuộc trò chuyện trước đó.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa hoặc nội dung cần tìm"},
                    "target_chat_id": {
                        "type": "integer",
                        "description": "Chat ID cụ thể cần tìm (để trống = dùng chat hiện tại)",
                    },
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
            "description": "Lưu ý tưởng nhanh của sếp vào Lark Base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung ý tưởng"},
                    "tags": {"type": "string", "description": "Tag phân loại (vd: marketing, content, product)"},
                    "project": {"type": "string", "description": "Dự án liên quan (nếu có)"},
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
            "description": "Gửi tin nhắn Telegram đến một người trong danh sách nhân sự.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Tên người nhận"},
                    "content": {"type": "string", "description": "Nội dung tin nhắn"},
                },
                "required": ["to", "content"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Reminder tools (1)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Tạo nhắc nhở vào một thời điểm cụ thể.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung nhắc nhở"},
                    "remind_at": {
                        "type": "string",
                        "description": "Thời gian nhắc dạng YYYY-MM-DD HH:MM",
                    },
                },
                "required": ["content", "remind_at"],
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
                "Chuyển sang Advisor khi sếp cần phân tích chiến lược, sắp xếp tổng thể. "
                "KHÔNG gọi cho CRUD đơn giản."
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
]


# ---------------------------------------------------------------------------
# Tool router
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: str, ctx: ChatContext) -> str:
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

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
        case "get_people":
            return await people.get_people(ctx, **args)
        case "list_people":
            return await people.list_people(ctx, **args)
        case "update_people":
            return await people.update_people(ctx, **args)
        case "delete_people":
            return await people.delete_people(ctx, **args)
        case "check_effort":
            return await people.check_effort(ctx, **args)

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

        # Memory tools
        case "search_history":
            return await memory.search_history(ctx, **args)

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

        # Web search tools
        case "web_search":
            return await web_search.web_search(**args)

        # Advisor escalation
        case "escalate_to_advisor":
            return "__ESCALATE__"

        case _:
            return f"Tool '{name}' không tồn tại."
