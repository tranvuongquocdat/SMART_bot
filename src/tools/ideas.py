"""
Idea creation tool. Takes ChatContext as first argument.
"""
from src.context import ChatContext
from src.services import lark


async def create_idea(ctx: ChatContext, content: str, tags: str = "", project: str = "") -> str:
    fields: dict = {
        "Nội dung": content,
        "Người tạo": ctx.sender_name,
    }
    if tags:
        fields["Tags"] = tags
    if project:
        fields["Project"] = project

    await lark.create_record(ctx.lark_base_token, ctx.lark_table_ideas, fields)
    return f"Đã lưu ý tưởng: {content}"
