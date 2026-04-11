import json

from src.tools import tasks, ideas, workload, summary, memory, note
from src.config import Settings


def init_tools(settings: Settings):
    tasks.init(settings)
    ideas.init(settings)
    workload.init(settings)
    summary.init(settings)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Tạo task mới trên Lark Base. Dùng khi CEO giao việc hoặc forward tin nhắn công việc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên task ngắn gọn"},
                    "assignee": {"type": "string", "description": "Người được giao"},
                    "deadline": {"type": "string", "description": "Deadline dạng YYYY-MM-DD"},
                    "priority": {"type": "string", "enum": ["Cao", "Trung bình", "Thấp"], "description": "Độ ưu tiên"},
                    "original_message": {"type": "string", "description": "Tin nhắn gốc CEO forward"},
                    "smart_analysis": {"type": "string", "description": "Phân tích SMART 1-2 câu"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Lọc danh sách task. Dùng khi CEO hỏi 'hôm nay có gì?', 'task của ai?', v.v.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Lọc theo người được giao"},
                    "status": {"type": "string", "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"], "description": "Lọc theo trạng thái"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Cập nhật task (trạng thái, deadline, ưu tiên, người giao). Dùng khi CEO nói 'done task X', 'dời deadline', v.v.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_keyword": {"type": "string", "description": "Từ khóa tìm task cần update"},
                    "status": {"type": "string", "enum": ["Mới", "Đang làm", "Xong", "Quá hạn"]},
                    "deadline": {"type": "string", "description": "Deadline mới dạng YYYY-MM-DD"},
                    "priority": {"type": "string", "enum": ["Cao", "Trung bình", "Thấp"]},
                    "assignee": {"type": "string", "description": "Chuyển task cho người khác"},
                },
                "required": ["search_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Tìm task theo nội dung. Dùng khi CEO hỏi 'có task nào liên quan X không?'",
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
            "name": "create_idea",
            "description": "Lưu ý tưởng nhanh. Dùng khi CEO ghi chú ý tưởng.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung ý tưởng"},
                    "tags": {"type": "string", "description": "Tag phân loại (vd: marketing, content, product)"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workload",
            "description": "Xem workload theo người. Dùng khi CEO hỏi 'ai đang bận?', 'Bách ôm bao nhiêu task?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {"type": "string", "description": "Tên người cần xem. Để trống = xem tất cả."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_history",
            "description": "Tìm trong lịch sử hội thoại. Dùng khi CEO hỏi về cuộc trò chuyện trước đó.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Từ khóa tìm trong lịch sử"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": "Tổng hợp task theo ngày hoặc tuần. Dùng khi CEO muốn brief.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_type": {"type": "string", "enum": ["today", "week"], "description": "Loại tóm tắt"},
                },
                "required": ["summary_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_personal_note",
            "description": "Cập nhật personal note về sếp. Gọi khi biết thêm thông tin mới về sếp, team, thói quen, hoặc cách làm việc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_content": {"type": "string", "description": "Nội dung personal note mới (ghi đè toàn bộ, giữ dưới 2000 tokens)"},
                },
                "required": ["note_content"],
            },
        },
    },
]


# Map tool name → async function
async def execute_tool(name: str, arguments: str, chat_id: int) -> str:
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    match name:
        case "create_task":
            return await tasks.create_task(**args)
        case "list_tasks":
            return await tasks.list_tasks(**args)
        case "update_task":
            return await tasks.update_task(**args)
        case "search_tasks":
            return await tasks.search_tasks(**args)
        case "create_idea":
            return await ideas.create_idea(**args)
        case "get_workload":
            return await workload.get_workload(**args)
        case "search_history":
            return await memory.search_history(chat_id=chat_id, **args)
        case "get_summary":
            return await summary.get_summary(**args)
        case "update_personal_note":
            return await note.update_personal_note(chat_id=chat_id, **args)
        case _:
            return f"Tool '{name}' không tồn tại."
