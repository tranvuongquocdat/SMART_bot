"""Onboarding agent — LLM helpers for the onboarding state machine.

State persistence + Lark provisioning live in `src/onboarding.py`. This
module owns just the LLM-driven pieces: the persona, the field collector,
the greeting, and the generic JSON classifier.
"""
from __future__ import annotations

import json

from src import db
from src.agent_pkg.llm_for_ctx import get_default_llm


PERSONA = """\
Bạn là trợ lý thư ký giám đốc AI — lịch sự, chuyên nghiệp, ấm áp như thư ký thật sự.
- Xưng "em", gọi sếp/giám đốc là "anh/chị", thành viên/đối tác là "bạn"
- Ngắn gọn, tự nhiên, thân thiện — không sáo rỗng, không khách sáo quá
- Có thể dùng *in đậm* cho thông tin quan trọng
- KHÔNG dùng emoji
- Trả lời tối đa 3-4 câu, đi thẳng vào vấn đề\
"""


COLLECTOR_PROMPT = """\
You are a smart onboarding assistant for an AI secretary app.
Extract structured fields from the user's message and generate a natural reply.

## Current collected state (GROUND TRUTH — do not contradict)
{state_json}

## Available workspaces (for member/partner to join)
{boss_list}

## State-aware rules (STRICT — follow before any other rule)
- If a field in state is NOT null, NEVER ask for it again. Move to the next missing field.
- Step order for boss path: type → name → company → language → confirm
- Step order for member/partner path: type → name → language → target_boss_id → confirm
- When all required fields are set and confirmed is null: SUMMARIZE collected info and ASK FOR CONFIRMATION once.

## Extraction rules
- "type": sếp/giám đốc/chủ → "boss"; nhân viên/thành viên → "member"; đối tác/partner/freelancer → "partner"
- "language": infer from the user's own writing style if not stated — Vietnamese → "vi", English → "en". Default "vi".
- "target_boss_id": if user mentions a boss name or company, match against available workspaces; return their chat_id (integer). Return null if no match or ambiguous.
- "confirmed":
    - true: explicit yes ("ok", "uh", "đúng", "đúng rồi", "tạo đi", "xác nhận", "yes", "được", "ừ", "đồng ý", "confirm")
    - false: explicit no ("không", "sai", "hủy", "làm lại", "cancel")
    - null: otherwise
- NEVER overwrite an existing non-null state field with null.

## Reply rules
- Write naturally in the user's inferred language.
- Ask ONLY for the NEXT missing field (see step order). Do not re-ask fields already set.
- If confirmed is true: acknowledge and say you are creating the workspace / sending the request.
- If user's message is off-topic (not about onboarding), briefly acknowledge and steer back to the pending step.

Return ONLY valid JSON:
{{
  "extracted": {{
    "type": "boss" | "member" | "partner" | null,
    "name": "..." | null,
    "company": "..." | null,
    "language": "vi" | "en" | "..." | null,
    "target_boss_id": 123 | null,
    "confirmed": true | false | null
  }},
  "reply": "..."
}}
"""


async def collector(state: dict, text: str, boss_list: str, chat_id: str) -> dict:
    """Extract structured fields + generate a reply for one onboarding turn."""
    state_copy = {k: v for k, v in state.items() if k != "first"}
    prompt = COLLECTOR_PROMPT.format(
        state_json=json.dumps(state_copy, ensure_ascii=False),
        boss_list=boss_list or "Chưa có workspace nào.",
    )
    # Load last 10 messages of this DM so LLM sees onboarding dialogue flow.
    recent = await db.get_recent(chat_id, limit=10)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in recent if m.get("content")
    ]
    messages = [
        {"role": "system", "content": prompt},
        *history,
        {"role": "user", "content": text},
    ]
    response, _ = await get_default_llm().chat_with_tools(messages, [])
    content = (response.content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
    return {"extracted": {}, "reply": ""}


async def greeting() -> str:
    """Initial greeting shown to a brand-new user before any state exists."""
    messages = [
        {"role": "system", "content": PERSONA},
        {"role": "user", "content": (
            "Tình huống: Người dùng mới vừa nhắn lần đầu. "
            "Chào, giới thiệu ngắn gọn em là trợ lý thư ký AI giúp quản lý công việc. "
            "Hỏi họ là: (1) Sếp/Giám đốc muốn tạo workspace mới, "
            "(2) Thành viên/Nhân viên, hoặc (3) Đối tác. Tối đa 3-4 câu."
        )},
    ]
    resp, _ = await get_default_llm().chat_with_tools(messages, [])
    return (resp.content or "").strip()


async def ai_classify(system_prompt: str, user_text: str) -> dict:
    """Generic JSON classifier — pass a prompt that asks for a JSON shape."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    response, _ = await get_default_llm().chat_with_tools(messages, [])
    content = response.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
    return {}
