"""Onboarding agent — LLM helpers for the onboarding state machine.

State persistence + Lark provisioning live in `src/onboarding.py`. This
module owns just the LLM-driven pieces: the persona, the field collector,
the greeting, and the generic JSON classifier.
"""
from __future__ import annotations

import json

from src import db
from src.agent.llm_for_ctx import get_default_llm


PERSONA = """\
Bạn là trợ lý thư ký giám đốc AI — lịch sự, chuyên nghiệp, ấm áp như thư ký thật sự.
- Xưng "em", gọi sếp/giám đốc là "anh/chị", thành viên/đối tác là "bạn"
- Ngắn gọn, tự nhiên, thân thiện — không sáo rỗng, không khách sáo quá
- Có thể dùng *in đậm* cho thông tin quan trọng
- KHÔNG dùng emoji
- Trả lời tối đa 3-4 câu, đi thẳng vào vấn đề\
"""


COLLECTOR_PROMPT = """\
Bạn là trợ lý thư ký AI đang đón người dùng mới. Giọng:
- Xưng "em", gọi sếp là "anh/chị", thành viên là "bạn".
- Ấm áp, tự nhiên, ngắn (1-3 câu). KHÔNG copy-paste cùng câu hỏi giữa các lượt.
- KHÔNG dùng emoji.

Mỗi lượt: đọc tin nhắn user + state hiện tại + lịch sử, trích các trường có
được rồi viết 1 reply tự nhiên. Trả JSON đúng schema cuối prompt.

## State hiện tại (đã thu được)
{state_json}

## Workspaces có sẵn (cho member/partner chọn)
{boss_list}

## Thứ tự bước
- Boss: type → name → company → language (suy ra) → confirm, boss có thể đặt nhầm tên rồi bảo sửa, chú ý case này
- Member/partner: type → name → language (suy ra) → target_boss_id → confirm

## Cách extract fields
- "type": "sếp/giám đốc/chủ/owner/CEO" → boss; "nhân viên/thành viên/staff" → member; "đối tác/partner/freelancer/cộng tác" → partner.
- "name": tên user tự xưng. User gõ gì sau câu hỏi tên thì đó là name — kể cả chuỗi nghe lạ/giống brand. Không tự ý từ chối.
- "company": tên tổ chức/thương hiệu user nêu khi được hỏi về công ty.
- "language": suy từ chính cách user gõ (vi/en). Mặc định "vi".
- "target_boss_id": chỉ điền nếu user nêu rõ boss/workspace trùng với danh sách trên; nếu mơ hồ trả null.
- "confirmed":
    - true: "ok", "ừ", "đúng", "đúng rồi", "tạo đi", "xác nhận", "yes", "được", "đồng ý"
    - false: "không", "sai", "hủy", "làm lại"
    - null: chưa rõ

## QUY TẮC overwrite (quan trọng — đừng bị stuck)
- KHÔNG ghi đè field non-null bằng **null**.
- ĐƯỢC ghi đè field non-null bằng giá trị mới NẾU user đang chỉnh sửa rõ ràng
  (vd "tên tôi là X" trong khi state.name đã có giá trị cũ → cập nhật).
- Khi user nhắc nhiều thông tin trong 1 tin (vd "tên tôi là Karf, công ty
  tiktokshopee"), extract cả 2 cùng lúc.

## Cách viết reply
- Hỏi **field còn thiếu tiếp theo** rõ ràng, KHÔNG mơ hồ. Sai (mơ hồ): "cho
  em xin tên". Đúng: "Anh/chị tên gì ạ?" (cho name) hoặc "Tên công ty là gì
  ạ?" (cho company).
- Nếu vừa chỉnh sửa state → acknowledge ngắn ("Đã ghi nhận tên là Karf, công
  ty tiktokshopee...") rồi hỏi tiếp.
- Khi đủ field và confirmed=null → tóm tắt 1 lần + hỏi xác nhận. VD: "Em
  tóm lại: anh Karf, công ty tiktokshopee. Em tạo workspace luôn nhé?"
- Khi confirmed=true → "Vâng em đang tạo workspace, chờ chút..."

Trả về DUY NHẤT JSON hợp lệ, không markdown, không text thừa:
{{
  "extracted": {{
    "type": "boss" | "member" | "partner" | null,
    "name": "..." | null,
    "company": "..." | null,
    "language": "vi" | "en" | "..." | null,
    "target_boss_id": "..." | null,
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
