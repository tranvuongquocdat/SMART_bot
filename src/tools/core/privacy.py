"""Privacy tools — PDPL opt-out cá nhân trong nhóm.

Thành viên nhắn với bot "đừng ghi tin của tôi" → responder (LLM quyết định,
không keyword) gọi ``opt_out_capture`` → từ đó InboundIngest bỏ qua mọi tin
của người này (mọi nhóm, mọi boss trên provider đó). Gỡ opt-out: qua
boss/superadmin (thao tác hiếm, chưa cần tool).
"""

from __future__ import annotations

from src.tools.base import ToolResult
from src.tools.registry import tool


@tool(
    name="opt_out_capture",
    description=(
        "Ghi nhận yêu cầu NGỪNG GHI tin nhắn của CHÍNH NGƯỜI ĐANG NHẮN "
        "(quyền phản đối xử lý dữ liệu). Chỉ dùng khi người gửi yêu cầu rõ "
        "ràng cho bản thân họ; không dùng thay cho người khác."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
    available_to={"in_group_responder", "dm_responder"},
    parallel_safe=False,
)
async def opt_out_capture(ctx) -> ToolResult:
    uid = getattr(ctx, "sender_provider_id", None)
    provider = getattr(ctx, "provider", None)
    if not uid or not provider:
        return ToolResult(
            content=None, error="cannot identify requester on this channel"
        )
    async with ctx.pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO capture_optouts (provider, provider_user_id, display_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (provider, provider_user_id) DO NOTHING
            """,
            provider, uid, getattr(ctx, "sender_name", None),
        )
    return ToolResult(content={
        "opted_out": True,
        "note": "Từ giờ tin nhắn của người này sẽ không được ghi nhận nữa; "
                "dữ liệu đã ghi trước đó muốn xoá thì liên hệ quản trị viên.",
    })
