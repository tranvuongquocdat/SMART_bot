import asyncio
from datetime import datetime

from zoneinfo import ZoneInfo

from src import db
from src.config import Settings
from src.services import openai_client, qdrant, telegram
from src.tools import TOOL_DEFINITIONS, execute_tool

_settings: Settings | None = None

SYSTEM_PROMPT = """Bạn là trợ lý AI thư ký cho giám đốc. Giao tiếp bằng tiếng Việt, thân thiện, ngắn gọn.

## Personal Note (thông tin về sếp):
{personal_note}

## Thời gian hiện tại: {current_time}

## Hướng dẫn:
- Dựa vào personal note để hiểu sếp là ai, xưng hô phù hợp.
- Nếu personal note còn trống (chưa biết) → chủ động hỏi làm quen: tên, công ty, lĩnh vực, team, cách xưng hô.
- Khi biết thêm thông tin mới về sếp/team/thói quen → gọi update_personal_note để cập nhật. Giữ note dưới 2000 tokens, tự tóm tắt nếu cần.
- Khi sếp giao việc, forward tin nhắn → gọi create_task.
- Khi sếp hỏi về task → gọi list_tasks hoặc search_tasks.
- Khi sếp cập nhật task → gọi update_task.
- Khi sếp ghi chú ý tưởng → gọi create_idea.
- Khi sếp hỏi workload → gọi get_workload.
- Khi cần thêm context từ lịch sử hội thoại → gọi search_history với query phù hợp.
- Khi sếp muốn brief/tóm tắt → gọi get_summary.
- Có thể gọi nhiều tool liên tiếp nếu cần.
- Trả lời ngắn gọn, đi thẳng vào vấn đề. Không giải thích dài dòng.
"""

MAX_TOOL_ROUNDS = 10


def init_agent(settings: Settings):
    global _settings
    _settings = settings


async def handle_message(text: str, chat_id: int):
    # 1. Save user message + embed to Qdrant
    msg_id = await db.save_message(chat_id, "user", text)
    vector = await openai_client.embed(text)
    asyncio.create_task(qdrant.upsert(msg_id, chat_id, "user", text, vector))

    # 2. Get context (parallel)
    personal_note, recent, relevant = await asyncio.gather(
        db.get_personal_note(),
        db.get_recent(chat_id, limit=5),
        qdrant.search(text, chat_id, top_n=5),
    )

    # 3. Build messages
    tz = ZoneInfo(_settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                personal_note=personal_note,
                current_time=current_time,
            ),
        }
    ]

    # Add RAG context as system message
    if relevant:
        context = "\n".join(f"[{m['role']}]: {m['content']}" for m in relevant)
        messages.append({
            "role": "system",
            "content": f"Lịch sử liên quan:\n{context}",
        })

    # Add recent messages
    for msg in recent:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current user message
    messages.append({"role": "user", "content": text})

    # 4. Agent loop: call AI → execute tools → repeat
    reply_text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        response = await openai_client.chat_with_tools(messages, TOOL_DEFINITIONS)

        # If AI wants to call tools
        if response.tool_calls:
            messages.append(response)  # append assistant message with tool_calls
            for tool_call in response.tool_calls:
                result = await execute_tool(
                    tool_call.function.name,
                    tool_call.function.arguments,
                    chat_id,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue  # let AI process tool results

        # AI returned a text reply
        reply_text = response.content or "..."
        break

    # 5. Save reply + embed + send
    reply_id = await db.save_message(chat_id, "assistant", reply_text)
    reply_vector = await openai_client.embed(reply_text)
    asyncio.create_task(qdrant.upsert(reply_id, chat_id, "assistant", reply_text, reply_vector))
    await telegram.send(chat_id, reply_text)
