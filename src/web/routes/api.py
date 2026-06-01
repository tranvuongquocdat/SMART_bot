"""HTMX partials and small JSON endpoints for the user app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.web.deps import get_current_boss

router = APIRouter(prefix="/api")

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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


@router.get("/reminders/list", response_class=HTMLResponse)
async def partial_reminders_list(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, text, due_at, scope, status
            FROM scheduled_reminders
            WHERE boss_id=$1 AND status='pending'
            ORDER BY due_at ASC LIMIT 50
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "_reminders_list.html",
        {"request": request, "rows": rows, "boss_ctx": ctx, "csrf_token": ""},
    )
