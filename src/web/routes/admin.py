"""Admin pages (superadmin-only).

Routes mounted under `/admin/*`. Every mutating endpoint must:
  1) `Depends(require_superadmin)` for authz
  2) `verify_csrf(request)`
  3) `INSERT INTO admin_audit_log` for accountability
  4) Publish `registry.invalidated` for live consumers when applicable
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.services.bot_account_service import BotAccountService
from src.web.deps import require_superadmin
from src.web.security import ensure_csrf, verify_csrf

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _ctx(request: Request, ctx) -> dict:
    return {
        "request": request,
        "csrf_token": ensure_csrf(request),
        "boss_ctx": ctx,
    }


async def _audit(pool, actor_uid: int, action: str, target_kind: str | None,
                 target_id: str | None, payload: dict | None = None):
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO admin_audit_log (actor_user_id, action, target_kind, target_id, payload_json)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            actor_uid,
            action,
            target_kind,
            target_id,
            json.dumps(payload or {}),
        )


async def _invalidate(bus, registry_name: str, key: str, by_user_id: int):
    try:
        await bus.publish(
            "registry.invalidated",
            {"registry_name": registry_name, "key": key, "by_user_id": by_user_id},
        )
    except Exception:
        pass


# =====================================================================
# Bosses
# =====================================================================

@router.get("/admin/bosses", response_class=HTMLResponse)
async def admin_bosses(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        bosses = await c.fetch(
            """
            SELECT u.id, u.email, u.name, u.role, u.subscription_status, u.created_at,
                   ba.provider, ba.id AS bot_acc_id, ba.display_name AS bot_display
            FROM users u
            LEFT JOIN bot_account_assignments baa
              ON baa.boss_id = u.id AND baa.status = 'active'
            LEFT JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE u.role IN ('boss', 'superadmin')
            ORDER BY u.created_at DESC
            """
        )
    return templates.TemplateResponse(
        request,
        "admin/bosses.html", _ctx(request, ctx) | {"bosses": bosses}
    )


@router.post("/admin/bosses/{boss_id}/assign-zalo")
async def admin_assign_zalo(
    boss_id: int,
    request: Request,
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    state = request.app.state
    svc = BotAccountService(state.db_pool, state.bus, {"zalo": state.zalo})
    try:
        await svc.auto_assign(boss_id, "zalo")
        await _audit(state.db_pool, ctx.boss_id, "assign_bot_account",
                     "users", str(boss_id), {"provider": "zalo"})
    except Exception as e:
        await _audit(state.db_pool, ctx.boss_id, "assign_bot_account_failed",
                     "users", str(boss_id), {"provider": "zalo", "error": str(e)})
    return RedirectResponse("/admin/bosses", status_code=303)


# =====================================================================
# Bot accounts (Platform / Boss-owned tabs)
# =====================================================================

@router.get("/admin/bot-accounts", response_class=HTMLResponse)
async def admin_bot_accounts(
    request: Request, tab: str = "platform", ctx=Depends(require_superadmin)
):
    ownership = "platform" if tab == "platform" else "boss_owned"
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT ba.*,
                   (SELECT count(*) FROM bot_account_assignments
                      WHERE bot_account_id = ba.id AND status='active')
                     AS active_assignments,
                   (SELECT count(*) FROM messages
                      WHERE provider = ba.provider
                            AND ingested_at > NOW() - INTERVAL '7 days')
                     AS msgs_7d
            FROM bot_accounts ba
            WHERE ba.ownership = $1
            ORDER BY ba.created_at DESC
            """,
            ownership,
        )
    return templates.TemplateResponse(
        request,
        "admin/bot_accounts.html",
        _ctx(request, ctx) | {"rows": rows, "tab": tab},
    )


@router.post("/admin/bot-accounts/{bot_id}/disable")
async def admin_bot_disable(
    bot_id: int,
    request: Request,
    reason: str = Form("manual"),
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            "UPDATE bot_accounts SET status='disabled', status_reason=$2, updated_at=NOW() WHERE id=$1",
            bot_id,
            reason,
        )
    await _audit(state.db_pool, ctx.boss_id, "disable_bot_account",
                 "bot_accounts", str(bot_id), {"reason": reason})
    await _invalidate(state.bus, "bot_accounts", str(bot_id), ctx.boss_id)
    return RedirectResponse("/admin/bot-accounts", status_code=303)


# =====================================================================
# Models CRUD
# =====================================================================

@router.get("/admin/models", response_class=HTMLResponse)
async def admin_models(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM models ORDER BY tier, provider, name"
        )
    return templates.TemplateResponse(
        request,
        "admin/models.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.post("/admin/models")
async def admin_models_create(
    request: Request,
    csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    caps = form.get("capabilities", "")
    cap_json = json.dumps(
        [c.strip() for c in (caps.split(",") if caps else []) if c.strip()]
    )
    async with state.db_pool.acquire() as c:
        new_id = await c.fetchval(
            """
            INSERT INTO models
              (name, provider, endpoint_kind, base_url, tier, ctx_max,
               capabilities, cost_per_1m_input_usd, cost_per_1m_output_usd,
               is_platform_default, is_active, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            form["name"],
            form["provider"],
            form.get("endpoint_kind") or "openai_chat",
            form.get("base_url") or None,
            form["tier"],
            int(form.get("ctx_max") or 8000),
            cap_json,
            float(form["cost_per_1m_input_usd"]) if form.get("cost_per_1m_input_usd") else None,
            float(form["cost_per_1m_output_usd"]) if form.get("cost_per_1m_output_usd") else None,
            form.get("is_platform_default") == "on",
            form.get("is_active", "on") == "on",
            form.get("notes") or None,
        )
    await _audit(state.db_pool, ctx.boss_id, "create_model", "models", str(new_id))
    await _invalidate(state.bus, "models", str(new_id), ctx.boss_id)
    return RedirectResponse("/admin/models", status_code=303)


@router.post("/admin/models/{mid}")
async def admin_models_update(
    mid: int, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE models
            SET tier = COALESCE($2, tier),
                ctx_max = COALESCE($3, ctx_max),
                cost_per_1m_input_usd = $4,
                cost_per_1m_output_usd = $5,
                is_active = $6,
                notes = $7,
                updated_at = NOW()
            WHERE id = $1
            """,
            mid,
            form.get("tier"),
            int(form["ctx_max"]) if form.get("ctx_max") else None,
            float(form["cost_per_1m_input_usd"]) if form.get("cost_per_1m_input_usd") else None,
            float(form["cost_per_1m_output_usd"]) if form.get("cost_per_1m_output_usd") else None,
            form.get("is_active") == "on",
            form.get("notes") or None,
        )
    await _audit(state.db_pool, ctx.boss_id, "update_model", "models", str(mid))
    await _invalidate(state.bus, "models", str(mid), ctx.boss_id)
    return RedirectResponse("/admin/models", status_code=303)


# =====================================================================
# Prompts CRUD (key+version)
# =====================================================================

@router.get("/admin/prompts", response_class=HTMLResponse)
async def admin_prompts(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT id, key, version, is_active, created_at, notes FROM prompts "
            "ORDER BY key, version DESC"
        )
    return templates.TemplateResponse(
        request,
        "admin/prompts.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.get("/admin/prompts/{pid}", response_class=HTMLResponse)
async def admin_prompt_detail(
    pid: int, request: Request, ctx=Depends(require_superadmin)
):
    async with request.app.state.db_pool.acquire() as c:
        row = await c.fetchrow("SELECT * FROM prompts WHERE id=$1", pid)
    return templates.TemplateResponse(
        request,
        "admin/prompt_detail.html", _ctx(request, ctx) | {"row": row}
    )


@router.post("/admin/prompts")
async def admin_prompts_create(
    request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        max_ver = await c.fetchval(
            "SELECT COALESCE(MAX(version),0) FROM prompts WHERE key=$1", form["key"]
        )
        new_id = await c.fetchval(
            """
            INSERT INTO prompts (key, version, body, is_active, notes, created_by)
            VALUES ($1, $2, $3, FALSE, $4, $5) RETURNING id
            """,
            form["key"],
            int(max_ver or 0) + 1,
            form.get("body", ""),
            form.get("notes") or None,
            ctx.boss_id,
        )
    await _audit(state.db_pool, ctx.boss_id, "create_prompt", "prompts", str(new_id))
    return RedirectResponse("/admin/prompts", status_code=303)


@router.post("/admin/prompts/{pid}/activate")
async def admin_prompt_activate(
    pid: int, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    state = request.app.state
    async with state.db_pool.acquire() as c:
        row = await c.fetchrow("SELECT key FROM prompts WHERE id=$1", pid)
        if row:
            await c.execute(
                "UPDATE prompts SET is_active=FALSE WHERE key=$1", row["key"]
            )
            await c.execute("UPDATE prompts SET is_active=TRUE WHERE id=$1", pid)
    await _audit(state.db_pool, ctx.boss_id, "activate_prompt", "prompts", str(pid))
    await _invalidate(state.bus, "prompts", str(pid), ctx.boss_id)
    return RedirectResponse("/admin/prompts", status_code=303)


# =====================================================================
# Note templates CRUD
# =====================================================================

@router.get("/admin/note-templates", response_class=HTMLResponse)
async def admin_note_templates(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch("SELECT * FROM note_templates ORDER BY name")
    return templates.TemplateResponse(
        request,
        "admin/note_templates.html", _ctx(request, ctx) | {"rows": rows}
    )


# =====================================================================
# LLM routes CRUD
# =====================================================================

@router.get("/admin/llm-routes", response_class=HTMLResponse)
async def admin_llm_routes(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM llm_routes ORDER BY feature, weight DESC"
        )
    return templates.TemplateResponse(
        request,
        "admin/llm_routes.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.post("/admin/llm-routes/{rid}")
async def admin_llm_route_update(
    rid: int, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE llm_routes
            SET target_tier=$2,
                fallback_chain=$3::jsonb,
                weight=$4,
                is_active=$5,
                updated_at=NOW()
            WHERE id=$1
            """,
            rid,
            form["target_tier"],
            form.get("fallback_chain") or "[]",
            int(form.get("weight") or 100),
            form.get("is_active") == "on",
        )
    await _audit(state.db_pool, ctx.boss_id, "update_llm_route", "llm_routes", str(rid))
    await _invalidate(state.bus, "llm_routes", str(rid), ctx.boss_id)
    return RedirectResponse("/admin/llm-routes", status_code=303)


# =====================================================================
# Feature budgets CRUD
# =====================================================================

@router.get("/admin/feature-budgets", response_class=HTMLResponse)
async def admin_feature_budgets(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM feature_budgets ORDER BY feature"
        )
    return templates.TemplateResponse(
        request,
        "admin/feature_budgets.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.post("/admin/feature-budgets/{feature}")
async def admin_feature_budget_update(
    feature: str, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE feature_budgets
            SET max_input_tokens=$2,
                max_output_tokens=$3,
                trim_policy_json=$4::jsonb,
                compression_strategy=$5,
                cache_prefix_hint=$6,
                updated_at=NOW()
            WHERE feature=$1
            """,
            feature,
            int(form["max_input_tokens"]),
            int(form["max_output_tokens"]),
            form.get("trim_policy_json") or "{}",
            form.get("compression_strategy") or "none",
            form.get("cache_prefix_hint") or None,
        )
    await _audit(state.db_pool, ctx.boss_id, "update_feature_budget",
                 "feature_budgets", feature)
    await _invalidate(state.bus, "feature_budgets", feature, ctx.boss_id)
    return RedirectResponse("/admin/feature-budgets", status_code=303)


# =====================================================================
# Agent triggers
# =====================================================================

@router.get("/admin/agent-triggers", response_class=HTMLResponse)
async def admin_agent_triggers(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM agent_triggers ORDER BY op_name"
        )
    return templates.TemplateResponse(
        request,
        "admin/agent_triggers.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.post("/admin/agent-triggers/{tid}")
async def admin_agent_trigger_update(
    tid: int, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE agent_triggers
            SET enabled=$2,
                debounce_json = CASE WHEN $3 = '' THEN NULL ELSE $3::jsonb END,
                threshold_json = CASE WHEN $4 = '' THEN NULL ELSE $4::jsonb END,
                updated_at=NOW()
            WHERE id=$1
            """,
            tid,
            form.get("enabled") == "on",
            form.get("debounce_json") or "",
            form.get("threshold_json") or "",
        )
    await _audit(state.db_pool, ctx.boss_id, "update_agent_trigger",
                 "agent_triggers", str(tid))
    await _invalidate(state.bus, "agent_triggers", str(tid), ctx.boss_id)
    return RedirectResponse("/admin/agent-triggers", status_code=303)


# =====================================================================
# Retrieval pipelines
# =====================================================================

@router.get("/admin/retrieval-pipelines", response_class=HTMLResponse)
async def admin_retrieval_pipelines(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            "SELECT * FROM retrieval_pipelines ORDER BY feature"
        )
    return templates.TemplateResponse(
        request,
        "admin/retrieval_pipelines.html", _ctx(request, ctx) | {"rows": rows}
    )


@router.post("/admin/retrieval-pipelines/{feature}")
async def admin_pipeline_update(
    feature: str, request: Request, csrf_field: str = Form("", alias="_csrf"),
    ctx=Depends(require_superadmin),
):
    request.state.form_csrf_token = csrf_field
    verify_csrf(request)
    form = await request.form()
    state = request.app.state
    async with state.db_pool.acquire() as c:
        await c.execute(
            """
            UPDATE retrieval_pipelines
            SET stages_json=$2::jsonb, description=$3, updated_at=NOW()
            WHERE feature=$1
            """,
            feature,
            form.get("stages_json") or "[]",
            form.get("description") or None,
        )
    await _audit(state.db_pool, ctx.boss_id, "update_retrieval_pipeline",
                 "retrieval_pipelines", feature)
    await _invalidate(state.bus, "retrieval_pipelines", feature, ctx.boss_id)
    return RedirectResponse("/admin/retrieval-pipelines", status_code=303)


# =====================================================================
# Audit log
# =====================================================================

@router.get("/admin/audit-log", response_class=HTMLResponse)
async def admin_audit_log(request: Request, ctx=Depends(require_superadmin)):
    async with request.app.state.db_pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT al.*, u.email AS actor_email
            FROM admin_audit_log al
            LEFT JOIN users u ON u.id = al.actor_user_id
            ORDER BY al.created_at DESC LIMIT 200
            """
        )
    return templates.TemplateResponse(
        request,
        "admin/audit_log.html", _ctx(request, ctx) | {"rows": rows}
    )
