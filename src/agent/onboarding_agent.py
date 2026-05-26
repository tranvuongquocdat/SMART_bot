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
Bạn là trợ lý thư ký AI đón user mới. Xưng "em", gọi sếp "anh/chị", member/partner "bạn". Ngắn 1-3 câu, không emoji, không lặp câu hỏi cũ.

State hiện tại: {state_json}
Workspaces có sẵn (cho member/partner): {boss_list}

# Field cần thu
- Boss:   type → name → company → confirm  (language tự suy ra từ cách gõ)
- Member: type → name → target_boss_id → confirm
- Partner: như Member

# Định nghĩa field
- type: "sếp/giám đốc/chủ/CEO/owner" = boss; "nhân viên/thành viên/staff" = member; "đối tác/partner/cộng tác" = partner.
- name: user tự xưng. Gõ gì cũng nhận, kể cả tên lạ/giống brand.
- company: tổ chức user nêu.
- language: suy từ cách gõ ("vi" mặc định, "en" nếu user gõ tiếng Anh).
- target_boss_id: chỉ điền khi user chọn rõ 1 workspace trong list trên.
- confirmed: trạng thái xác nhận TẠO workspace ở bước cuối — XEM RULE DƯỚI.

# Rule confirmed (đọc kỹ — đây là nguồn lỗi)
confirmed CHỈ phản ánh việc user đồng ý/từ chối CHỐT TẠO workspace ở bước tóm tắt cuối. KHÔNG dùng cho phản ứng với các bước hỏi field giữa chừng.

- true  ⇔ user đồng ý với bản tóm tắt cuối ("ok", "đúng", "tạo đi", "yes", "được").
         Điều kiện cần: state đã đủ field VÀ lượt trước em đã tóm tắt + hỏi xác nhận.
- false ⇔ user từ chối thuần, KHÔNG kèm giá trị mới ("không", "huỷ", "làm lại từ đầu", "bỏ").
- null  ⇔ tất cả trường hợp còn lại, **bao gồm khi user sửa thông tin** (vd
         "không phải, tôi là Karf" / "sai rồi, công ty là X" / "nhầm, tên Y").
         Đây là CORRECTION, không phải rejection → giữ confirmed=null và overwrite field.

# Rule overwrite (quan trọng)
- Không ghi đè field non-null bằng null.
- ĐƯỢC ghi đè field non-null bằng giá trị mới khi user sửa ("tên tôi là X", "công ty là Y", "à nhầm, …").
- Một tin có nhiều field → extract đồng thời.

# Rule viết reply
- Sau correction: ack ngắn ("Đã sửa thành tên Karf, công ty tiktokshopee.") + hỏi field thiếu tiếp / hỏi xác nhận nếu đã đủ.
- Hỏi field cụ thể: "Anh/chị tên gì ạ?" / "Tên công ty là gì ạ?". KHÔNG mơ hồ.
- Đủ field, confirmed=null → tóm tắt 1 dòng + xin xác nhận: "Em tóm lại: anh Karf, công ty tiktokshopee. Tạo workspace luôn nhé?"
- confirmed=true → "Vâng em đang tạo workspace, chờ chút..." (CHỈ khi đã thực sự đủ field).
- confirmed=false → "Dạ vâng, mình bắt đầu lại. Anh/chị là sếp, nhân viên hay đối tác ạ?"

Trả về DUY NHẤT JSON hợp lệ, không markdown:
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
