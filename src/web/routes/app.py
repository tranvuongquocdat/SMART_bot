"""User-facing pages (Dashboard, Groups, Reminders, Settings, etc.).

Mounted under `/app` in src/main.py. All routes require `get_current_boss`.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.web.deps import get_current_boss
from src.web.security import ensure_csrf, verify_csrf

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _ctx(request: Request, boss_ctx) -> dict:
    return {
        "request": request,
        "csrf_token": ensure_csrf(request),
        "boss_ctx": boss_ctx,
    }


# ---------- Dashboard ----------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        groups_count = await c.fetchval(
            "SELECT count(*) FROM group_notes WHERE boss_id=$1", ctx.boss_id
        )
        open_items = await c.fetchval(
            "SELECT count(*) FROM action_items WHERE boss_id=$1 AND status='open'",
            ctx.boss_id,
        )
        pending_rems = await c.fetchval(
            "SELECT count(*) FROM scheduled_reminders WHERE boss_id=$1 AND status='pending'",
            ctx.boss_id,
        )
        recent_rems = await c.fetch(
            """
            SELECT id, text, due_at, scope
            FROM scheduled_reminders
            WHERE boss_id=$1 AND status='pending'
            ORDER BY due_at ASC LIMIT 10
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _ctx(request, ctx)
        | {
            "groups_count": groups_count or 0,
            "open_items": open_items or 0,
            "pending_rems": pending_rems or 0,
            "recent_rems": recent_rems,
        },
    )


# ---------- Groups ----------

@router.get("/groups", response_class=HTMLResponse)
async def groups_list(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT gn.id, gn.provider, gn.chat_id, gn.group_name, gn.updated_at,
                   gn.msg_count_7d,
                   (SELECT count(*) FROM action_items ai
                      WHERE ai.group_note_id=gn.id AND ai.status='open') AS open_count,
                   (SELECT count(*) FROM action_items ai
                      WHERE ai.group_note_id=gn.id AND ai.status='open'
                            AND ai.due_at IS NOT NULL AND ai.due_at < NOW()) AS overdue_count
            FROM group_notes gn
            WHERE gn.boss_id=$1
            ORDER BY gn.updated_at DESC
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "groups.html", _ctx(request, ctx) | {"groups": rows}
    )


@router.get("/groups/{chat_id}", response_class=HTMLResponse)
async def group_detail(chat_id: str, request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        note = await c.fetchrow(
            """
            SELECT * FROM group_notes
            WHERE boss_id=$1 AND chat_id=$2
            ORDER BY updated_at DESC LIMIT 1
            """,
            ctx.boss_id,
            chat_id,
        )
        if not note:
            raise HTTPException(404, "group not found")
        items = await c.fetch(
            """
            SELECT id, text, status, assignee_name, due_at
            FROM action_items
            WHERE boss_id=$1 AND group_note_id=$2
            ORDER BY status, due_at NULLS LAST, id DESC
            """,
            ctx.boss_id,
            note["id"],
        )
        messages = await c.fetch(
            """
            SELECT id, sender_name, text, sent_at
            FROM messages
            WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
            ORDER BY sent_at DESC LIMIT 50
            """,
            ctx.boss_id,
            note["provider"],
            chat_id,
        )
    return templates.TemplateResponse(
        request,
        "group_detail.html",
        _ctx(request, ctx)
        | {"note": note, "items": items, "messages": messages},
    )


# ---------- Action items / Projects ----------

@router.get("/action-items", response_class=HTMLResponse)
async def action_items_list(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT ai.*, gn.group_name, gn.chat_id, gn.provider
            FROM action_items ai
            JOIN group_notes gn ON gn.id = ai.group_note_id
            WHERE ai.boss_id=$1
            ORDER BY ai.status, ai.due_at NULLS LAST, ai.id DESC
            LIMIT 200
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "action_items.html", _ctx(request, ctx) | {"items": rows}
    )


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(request: Request, ctx=Depends(get_current_boss)):
    # MVP: projects view = groups grouped by status (placeholder).
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT status, count(*) AS n
            FROM group_notes WHERE boss_id=$1
            GROUP BY status ORDER BY status
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "projects.html", _ctx(request, ctx) | {"rows": rows}
    )


# ---------- Reminders ----------

@router.get("/reminders", response_class=HTMLResponse)
async def reminders_list(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        pending = await c.fetch(
            """
            SELECT id, text, due_at, scope, provider, chat_id, recurring, status
            FROM scheduled_reminders
            WHERE boss_id=$1 AND status='pending'
            ORDER BY due_at ASC
            """,
            ctx.boss_id,
        )
        recent_fired = await c.fetch(
            """
            SELECT id, text, due_at, status, fired_at
            FROM scheduled_reminders
            WHERE boss_id=$1 AND status!='pending'
            ORDER BY COALESCE(fired_at, due_at) DESC LIMIT 20
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "reminders.html",
        _ctx(request, ctx) | {"pending": pending, "recent": recent_fired},
    )


@router.post("/reminders")
async def reminders_create(
    request: Request,
    text: str = Form(...),
    due_at: str = Form(...),
    scope: str = Form("dm"),
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO scheduled_reminders
              (boss_id, text, due_at, scope, status, created_by_op)
            VALUES ($1, $2, $3::timestamptz, $4, 'pending', 'web.user')
            """,
            ctx.boss_id,
            text,
            due_at,
            scope,
        )
    return RedirectResponse("/app/reminders", status_code=303)


@router.post("/reminders/{rid}/cancel")
async def reminders_cancel(
    rid: int,
    request: Request,
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE scheduled_reminders SET status='canceled' WHERE id=$1 AND boss_id=$2",
            rid,
            ctx.boss_id,
        )
    return RedirectResponse("/app/reminders", status_code=303)


# ---------- Channels ----------

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        assigns = await c.fetch(
            """
            SELECT baa.*, ba.provider, ba.display_name, ba.status AS bot_status,
                   ba.account_kind, ba.ownership
            FROM bot_account_assignments baa
            JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE baa.boss_id=$1
            ORDER BY baa.status, ba.provider
            """,
            ctx.boss_id,
        )
        links = await c.fetch(
            """
            SELECT provider, provider_user_id, display_name, linked_at
            FROM account_links
            WHERE boss_id=$1
            ORDER BY linked_at DESC
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "channels.html",
        _ctx(request, ctx) | {"assigns": assigns, "links": links},
    )


# ---------- Usage ----------

@router.get("/usage", response_class=HTMLResponse)
async def usage_page(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT feature, operation, provider,
                   sum(input_tokens) AS in_toks,
                   sum(output_tokens) AS out_toks,
                   sum(cost_usd) AS cost
            FROM token_usage
            WHERE boss_id=$1 AND created_at > NOW() - INTERVAL '30 days'
            GROUP BY feature, operation, provider
            ORDER BY cost DESC LIMIT 50
            """,
            ctx.boss_id,
        )
        total = await c.fetchval(
            """
            SELECT COALESCE(sum(cost_usd), 0)::float
            FROM token_usage
            WHERE boss_id=$1 AND created_at > NOW() - INTERVAL '30 days'
            """,
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "usage.html", _ctx(request, ctx) | {"rows": rows, "total_cost": float(total or 0)}
    )


# ---------- Settings: general / account ----------

@router.get("/settings/general", response_class=HTMLResponse)
async def settings_general(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        boss = await c.fetchrow(
            "SELECT id, email, name, tz, language FROM users WHERE id=$1", ctx.boss_id
        )
    return templates.TemplateResponse(
        request,
        "settings_general.html", _ctx(request, ctx) | {"boss": boss}
    )


@router.post("/settings/general")
async def settings_general_save(
    request: Request,
    name: str = Form(""),
    tz: str = Form("Asia/Ho_Chi_Minh"),
    language: str = Form("vi"),
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE users SET name=$2, tz=$3, language=$4 WHERE id=$1",
            ctx.boss_id,
            name or None,
            tz,
            language,
        )
    return RedirectResponse("/app/settings/general", status_code=303)


@router.get("/settings/account", response_class=HTMLResponse)
async def settings_account(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        boss = await c.fetchrow(
            "SELECT id, email, name, role, google_sub IS NOT NULL AS google_linked, "
            "       subscription_status, subscription_expiry, cost_cap_usd_daily "
            "FROM users WHERE id=$1",
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "settings_account.html", _ctx(request, ctx) | {"boss": boss}
    )


# ---------- Subscription ----------

@router.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        boss = await c.fetchrow(
            "SELECT subscription_status, subscription_plan, subscription_expiry, "
            "       cost_cap_usd_daily FROM users WHERE id=$1",
            ctx.boss_id,
        )
    return templates.TemplateResponse(
        request,
        "subscription.html", _ctx(request, ctx) | {"boss": boss}
    )


# ---------- Settings AI (G4) ----------

@router.get("/settings/ai", response_class=HTMLResponse)
async def settings_ai(request: Request, ctx=Depends(get_current_boss)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        boss = await c.fetchrow(
            """
            SELECT id, email, name, smart_model_id, fast_model_id, vision_model_id,
                   cost_cap_usd_daily, api_keys_enc
            FROM users WHERE id=$1
            """,
            ctx.boss_id,
        )
        models = await c.fetch(
            "SELECT id, name, provider, tier, capabilities, cost_per_1m_input_usd, "
            "       cost_per_1m_output_usd, is_platform_default "
            "FROM models WHERE is_active=TRUE ORDER BY tier, provider, name"
        )
    # Determine which providers have a stored key (without decrypting values).
    saved_providers: list[str] = []
    if boss and boss["api_keys_enc"]:
        try:
            f = Fernet(settings.FERNET_KEY.encode())
            data = json.loads(f.decrypt(bytes(boss["api_keys_enc"])).decode())
            saved_providers = sorted(data.keys())
        except Exception:
            saved_providers = []

    # Smart model capabilities for "vision included?" hint.
    smart_caps: list = []
    smart_name: str | None = None
    if boss and boss["smart_model_id"]:
        for m in models:
            if m["id"] == boss["smart_model_id"]:
                smart_caps = list(m["capabilities"]) if m["capabilities"] else []
                smart_name = m["name"]
                break

    return templates.TemplateResponse(
        request,
        "settings_ai.html",
        _ctx(request, ctx)
        | {
            "boss": boss,
            "models": models,
            "saved_providers": saved_providers,
            "smart_has_vision": "vision" in smart_caps,
            "smart_name": smart_name,
        },
    )


@router.post("/settings/ai")
async def settings_ai_save(
    request: Request,
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()

    def _maybe_int(v) -> int | None:
        try:
            iv = int(v) if v else 0
        except (TypeError, ValueError):
            return None
        return iv or None

    smart = _maybe_int(form.get("smart_model_id"))
    fast = _maybe_int(form.get("fast_model_id"))
    vision = _maybe_int(form.get("vision_model_id"))
    cap_raw = form.get("cost_cap_usd_daily")
    try:
        cap = float(cap_raw) if cap_raw not in (None, "") else None
    except (TypeError, ValueError):
        cap = None

    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        if cap is not None:
            await c.execute(
                """
                UPDATE users
                SET smart_model_id=$2, fast_model_id=$3, vision_model_id=$4,
                    cost_cap_usd_daily=$5
                WHERE id=$1
                """,
                ctx.boss_id,
                smart,
                fast,
                vision,
                cap,
            )
        else:
            await c.execute(
                """
                UPDATE users
                SET smart_model_id=$2, fast_model_id=$3, vision_model_id=$4
                WHERE id=$1
                """,
                ctx.boss_id,
                smart,
                fast,
                vision,
            )

    # Invalidate any cached resolution downstream.
    try:
        await request.app.state.bus.publish(
            "registry.invalidated",
            {
                "registry_name": "users.model_slots",
                "key": str(ctx.boss_id),
                "by_user_id": ctx.boss_id,
            },
        )
    except Exception:
        pass

    return RedirectResponse("/app/settings/ai", status_code=303)


@router.post("/settings/ai/keys")
async def settings_ai_save_keys(
    request: Request,
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(get_current_boss),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()

    pool = request.app.state.db_pool
    # Load existing keys (so empty inputs don't clobber stored values).
    async with pool.acquire() as c:
        blob = await c.fetchval(
            "SELECT api_keys_enc FROM users WHERE id=$1", ctx.boss_id
        )
    f = Fernet(settings.FERNET_KEY.encode())
    existing: dict[str, str] = {}
    if blob:
        try:
            existing = json.loads(f.decrypt(bytes(blob)).decode())
        except Exception:
            existing = {}

    for prov in ("openai", "groq", "gemini"):
        v = (form.get(f"key_{prov}") or "").strip()
        clear = form.get(f"clear_{prov}")
        if clear:
            existing.pop(prov, None)
        elif v:
            existing[prov] = v

    new_blob = f.encrypt(json.dumps(existing).encode())
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE users SET api_keys_enc=$2 WHERE id=$1", ctx.boss_id, new_blob
        )

    try:
        await request.app.state.bus.publish(
            "registry.invalidated",
            {
                "registry_name": "users.api_keys",
                "key": str(ctx.boss_id),
                "by_user_id": ctx.boss_id,
            },
        )
    except Exception:
        pass

    return RedirectResponse("/app/settings/ai", status_code=303)
