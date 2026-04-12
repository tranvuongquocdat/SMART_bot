"""
Advisor agent: strategy analysis on-demand + smart daily review (cron 8am).
Read-only — never mutates data.
"""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src import db
from src.config import Settings
from src.context import ChatContext
from src.services import openai_client
from src.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("advisor")

# ---------------------------------------------------------------------------
# Read-only tool subset
# ---------------------------------------------------------------------------

_ADVISOR_TOOL_NAMES = {
    "list_tasks",
    "search_tasks",
    "list_people",
    "get_people",
    "check_effort",
    "list_projects",
    "get_project",
    "get_note",
    "search_history",
    "get_summary",
    "get_workload",
}

ADVISOR_TOOLS = [
    t for t in TOOL_DEFINITIONS
    if t["function"]["name"] in _ADVISOR_TOOL_NAMES
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ADVISOR_PROMPT = """\
Bạn là cố vấn chiến lược cho {boss_name}{company_info}.
Vai trò: phân tích tình hình, đề xuất giải pháp, giúp sếp ra quyết định.

## Thời gian: {current_time}

## Câu hỏi: {question}

## Context: {context_str}

## Hướng dẫn:
- Phân tích dựa trên DATA thực tế. Gọi tools để lấy data.
- Đề xuất cụ thể, có lý do, kèm phương án thay thế.
- Xem xét: workload, deadline, kỹ năng, xung đột lịch.
- Thiếu thông tin → nói rõ, đề xuất dựa trên cái đang có.
- Format: Tình hình → Phân tích → Đề xuất → Lý do.
- Tiếng Việt, chuyên nghiệp, ngắn gọn.\
"""

DAILY_REVIEW_PROMPT = """\
Bạn là cố vấn AI của {boss_name}. Hôm nay {current_time}.
Soạn briefing sáng cho sếp.

Hãy:
1. Xem tasks hôm nay + quá hạn + deadline trong 3 ngày
2. Xem workload từng người
3. Xem dự án đang active
4. Phân tích: cảnh báo, quá tải, deadline nguy hiểm?
5. Đề xuất hành động cụ thể

Format:
- Chào sếp, tóm 1 câu tình hình
- Tasks hôm nay
- Cảnh báo (nếu có)
- Đề xuất (nếu có)
- Hỏi sếp muốn xử lý gì

Dưới 300 từ, chỉ nêu điều quan trọng.\
"""

MAX_TOOL_ROUNDS = 8


# ---------------------------------------------------------------------------
# Internal agent loop
# ---------------------------------------------------------------------------

async def _run_agent_loop(ctx: ChatContext, system_prompt: str, source: str = "advisor") -> str:
    """Shared agentic loop for both advisor functions."""
    messages = [{"role": "system", "content": system_prompt}]

    reply_text = ""
    total_prompt = 0
    total_completion = 0
    total_tokens = 0

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        response, usage = await openai_client.chat_with_tools(messages, ADVISOR_TOOLS)
        total_prompt += usage.get("prompt_tokens", 0)
        total_completion += usage.get("completion_tokens", 0)
        total_tokens += usage.get("total_tokens", 0)

        logger.info(
            f"[advisor:{ctx.boss_chat_id}] Round {round_num} | "
            f"tokens: {usage.get('prompt_tokens', 0)}in/{usage.get('completion_tokens', 0)}out"
        )

        if response.tool_calls:
            messages.append(response)

            for tc in response.tool_calls:
                logger.info(f"[advisor:{ctx.boss_chat_id}] TOOL: {tc.function.name}({tc.function.arguments})")

            results = await asyncio.gather(
                *(execute_tool(tc.function.name, tc.function.arguments, ctx)
                  for tc in response.tool_calls)
            )

            for tool_call, result in zip(response.tool_calls, results):
                logger.info(f"[advisor:{ctx.boss_chat_id}] TOOL RESULT: {result[:200]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
            continue

        reply_text = response.content or "..."
        break

    await db.log_token_usage(ctx.boss_chat_id, source, total_prompt, total_completion, total_tokens)

    return reply_text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_advisor(
    ctx: ChatContext,
    context_str: str,
    question: str,
    settings: Settings,
) -> str:
    """Strategy analysis triggered when CEO asks a strategic question."""
    boss = await db.get_boss(ctx.boss_chat_id)
    company = boss.get("company", "") if boss else ""
    company_info = f" — {company}" if company else ""

    tz = ZoneInfo(settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    system_prompt = ADVISOR_PROMPT.format(
        boss_name=ctx.boss_name,
        company_info=company_info,
        current_time=current_time,
        question=question,
        context_str=context_str,
    )

    logger.info(
        f"[advisor:{ctx.boss_chat_id}] run_advisor | question: {question[:100]}"
    )
    return await _run_agent_loop(ctx, system_prompt, source="advisor")


async def run_daily_review(ctx: ChatContext, settings: Settings) -> str:
    """Smart morning briefing triggered by cron at 8am."""
    boss = await db.get_boss(ctx.boss_chat_id)
    company = boss.get("company", "") if boss else ""
    company_info = f" ({company})" if company else ""

    tz = ZoneInfo(settings.timezone)
    current_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M (%A)")

    system_prompt = DAILY_REVIEW_PROMPT.format(
        boss_name=ctx.boss_name + company_info,
        current_time=current_time,
    )

    logger.info(f"[advisor:{ctx.boss_chat_id}] run_daily_review | {current_time}")
    return await _run_agent_loop(ctx, system_prompt, source="daily_review")
