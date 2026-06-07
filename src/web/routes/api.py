"""Small JSON endpoints for the user app (HTMX partials removed after Jinja2 cleanup)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from src.web.deps import get_current_boss

router = APIRouter(prefix="/api")


@router.get("/groups/{chat_id}/note", response_class=HTMLResponse)
async def partial_group_note(
    chat_id: str, request: Request, ctx=Depends(get_current_boss)
):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        note = await c.fetchrow(
            """
            SELECT id, content, updated_at FROM group_notes
            WHERE boss_id=$1 AND chat_id=$2
            ORDER BY updated_at DESC LIMIT 1
            """,
            ctx.boss_id,
            chat_id,
        )
    if not note:
        return HTMLResponse("<div class='text-sm text-gray-400'>(chưa có note)</div>")
    return HTMLResponse(
        f"<pre class='whitespace-pre-wrap text-sm'>{(note['content'] or '')}</pre>"
        f"<div class='text-xs text-gray-400 mt-2'>cập nhật: {note['updated_at']}</div>"
    )
