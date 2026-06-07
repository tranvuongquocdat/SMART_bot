"""FastAPI router cho /test/* — UI + JSON API + SSE.

Mount ở main.py qua include_router. Lookup adapter/repos qua
``request.app.state.channel_registry.get('web')`` để tránh circular dep.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.channels.web.promotion import BossPromotionService
from src.web.security import set_session_cookie

router = APIRouter(prefix="/test")
_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir)) if _templates_dir.is_dir() else None
_STATIC_DIR = Path(__file__).parent / "static"


def _adapter(request: Request):
    reg = getattr(request.app.state, "channel_registry", None)
    if reg is None:
        raise HTTPException(503, "channel registry not ready")
    adapter = reg.get("web")
    if adapter is None:
        raise HTTPException(404, "web channel not enabled")
    return adapter


class CreateUserBody(BaseModel):
    name: str
    role: str = "employee"  # employee | boss | superadmin


def _promotion_role(role: str) -> str | None:
    """Map test-channel role label → promotion role; None means no promotion."""
    if role == "boss":
        return "boss"
    if role == "superadmin":
        return "superadmin"
    return None  # employee — stays a plain web_user, no users row needed


class CreateGroupBody(BaseModel):
    name: str
    member_ids: list[str] = []


class MembershipBody(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _templates is None:
        return HTMLResponse("<h1>Web Test Channel</h1>")
    return _templates.TemplateResponse(request, "index.html")


@router.get("/api/users")
async def list_users(request: Request):
    a = _adapter(request)
    return await a.users_repo.list_all()


@router.post("/api/users")
async def create_user(request: Request, body: CreateUserBody):
    a = _adapter(request)
    uid = await a.users_repo.create(name=body.name, is_boss=False)
    promo = _promotion_role(body.role)
    if promo is not None:
        await BossPromotionService(a.pool).promote(uid, role=promo)
    return {"id": uid}


@router.patch("/api/users/{uid}")
async def update_user(request: Request, uid: str, body: CreateUserBody):
    a = _adapter(request)
    await a.users_repo.rename(uid, body.name)
    existing = await a.users_repo.get(uid)
    if existing is None:
        raise HTTPException(404, "user not found")
    promo = _promotion_role(body.role)
    if promo is not None and not existing["is_boss"]:
        await BossPromotionService(a.pool).promote(uid, role=promo)
    elif promo is None and existing["is_boss"]:
        await BossPromotionService(a.pool).demote(uid)
    elif promo is not None and existing["is_boss"]:
        # Already promoted — re-promote so role column reflects new selection.
        await BossPromotionService(a.pool).promote(uid, role=promo)
    return {"ok": True}


@router.delete("/api/users/{uid}", status_code=204)
async def delete_user(request: Request, uid: str):
    a = _adapter(request)
    existing = await a.users_repo.get(uid)
    if existing and existing["is_boss"]:
        await BossPromotionService(a.pool).demote(uid)
    await a.users_repo.delete(uid)


@router.get("/api/groups")
async def list_groups(request: Request):
    a = _adapter(request)
    return await a.groups_repo.list_all()


@router.post("/api/groups")
async def create_group(request: Request, body: CreateGroupBody):
    a = _adapter(request)
    gid = await a.groups_repo.create(name=body.name, member_ids=body.member_ids)
    return {"id": gid}


@router.delete("/api/groups/{gid}", status_code=204)
async def delete_group(request: Request, gid: str):
    a = _adapter(request)
    await a.groups_repo.delete(gid)


@router.post("/api/groups/{gid}/members")
async def edit_members(request: Request, gid: str, body: MembershipBody):
    a = _adapter(request)
    for uid in body.add:
        await a.groups_repo.add_member(gid, uid)
    for uid in body.remove:
        await a.groups_repo.remove_member(gid, uid)
    return {"members": await a.groups_repo.list_members(gid)}


@router.get("/api/chats")
async def list_chats(request: Request, as_: str = "", as_alt: str = ""):
    """List chats that the identity 'as' participates in: 1 DM with bot + all groups.

    Query param: ?as=<web_user_id>
    """
    a = _adapter(request)
    uid = request.query_params.get("as")
    if not uid:
        return []
    user = await a.users_repo.get(uid)
    if user is None:
        return []
    groups = await a.groups_repo.list_for_user(uid)
    chats = [
        {"chat_id": f"dm:{uid}", "name": f"DM with Bot", "kind": "dm"},
    ]
    chats.extend(
        {"chat_id": g["id"], "name": g["name"], "kind": "group"}
        for g in groups
    )
    return chats


@router.post("/api/send")
async def send_inbound(request: Request):
    a = _adapter(request)
    body = await request.json()
    as_uid = body.get("as")
    chat_id = body.get("chat_id")
    text = body.get("text") or ""
    mention_bot = bool(body.get("mention_bot"))
    if not as_uid or not chat_id:
        raise HTTPException(400, "as and chat_id required")

    sender = await a.users_repo.get(as_uid)
    if sender is None:
        raise HTTPException(404, "sender not found")

    import uuid as _uuid
    await a.bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": as_uid,
            "chat_id": chat_id,
            "chat_type": "dm" if chat_id.startswith("dm:") else "group",
            "text": text,
            "mention_bot": mention_bot,
            "provider_msg_id": f"w-{_uuid.uuid4().hex[:10]}",
            "sender_name": sender["name"],
        },
    )
    return {"ok": True}


@router.get("/stream")
async def sse_stream(request: Request):
    a = _adapter(request)
    uid = request.query_params.get("as")
    if not uid:
        raise HTTPException(400, "as= required")
    user = await a.users_repo.get(uid)
    if user is None:
        raise HTTPException(404, "user not found")

    client = a.sse_hub.attach(uid)

    async def gen():
        try:
            # Initial comment to flush headers
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        client.queue.get(), timeout=15.0
                    )
                    payload = json.dumps(event)
                    yield f"data: {payload}\n\n".encode()
                except asyncio.TimeoutError:
                    yield b": heartbeat\n\n"
        finally:
            a.sse_hub.detach(client)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/chats/{chat_id:path}/messages")
async def replay_messages(request: Request, chat_id: str, limit: int = 50):
    a = _adapter(request)
    async with a.pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT * FROM (
              SELECT
                'in'::text  AS kind,
                m.id        AS id,
                m.chat_id   AS chat_id,
                m.sender_provider_id AS sender_id,
                m.sender_name        AS sender_name,
                m.text      AS text,
                m.ts        AS ts
              FROM messages m
              WHERE m.provider='web' AND m.chat_id=$1
              UNION ALL
              SELECT
                'out'::text AS kind,
                o.id        AS id,
                o.chat_id   AS chat_id,
                NULL        AS sender_id,
                'Bot'       AS sender_name,
                o.content   AS text,
                o.sent_at   AS ts
              FROM outbound_messages o
              WHERE o.provider='web' AND o.chat_id=$1
            ) merged
            ORDER BY ts DESC
            LIMIT $2
            """,
            chat_id, limit,
        )
    rows = list(reversed(rows))  # chronological
    return [
        {
            "kind": r["kind"],
            "id": r["id"],
            "chat_id": r["chat_id"],
            "sender_id": r["sender_id"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "ts": r["ts"].isoformat(),
        }
        for r in rows
    ]


def _safe_next(raw: str | None, fallback: str = "/app") -> str:
    """Same-origin only — single leading slash, no protocol-relative."""
    if not raw or not raw.startswith("/") or raw.startswith("//") or raw.startswith("/\\"):
        return fallback
    return raw


@router.get("/login-as/{web_user_id}")
async def login_as(request: Request, web_user_id: str, next: str | None = None):
    """Dev-mode backdoor: set session cookie as the boss linked to a web_user.

    Only mounted when ENABLE_WEB_TEST_CHANNEL=true. Resolves
    web_users.boss_user_id → users.id and signs a session cookie.
    """
    a = _adapter(request)
    async with a.pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT boss_user_id, is_boss, name FROM web_users WHERE id=$1",
            web_user_id,
        )
    if row is None:
        raise HTTPException(404, "web_user not found")
    if not row["is_boss"] or row["boss_user_id"] is None:
        raise HTTPException(
            400,
            f"'{row['name']}' chưa được promote — chọn Boss hoặc Superadmin khi tạo user.",
        )
    target = _safe_next(next)
    response = RedirectResponse(target, status_code=303)
    set_session_cookie(
        response,
        int(row["boss_user_id"]),
        secure=request.url.scheme == "https",
    )
    return response
