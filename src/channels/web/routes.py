"""FastAPI router cho /test/* — UI + JSON API + SSE.

Mount ở main.py qua include_router. Lookup adapter/repos qua
``request.app.state.channel_registry.get('web')`` để tránh circular dep.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.channels.web.promotion import BossPromotionService

router = APIRouter(prefix="/test")
_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir)) if _templates_dir.is_dir() else None


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
    is_boss: bool = False


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
    return _templates.TemplateResponse(
        "index.html", {"request": request}
    )


@router.get("/api/users")
async def list_users(request: Request):
    a = _adapter(request)
    return await a.users_repo.list_all()


@router.post("/api/users")
async def create_user(request: Request, body: CreateUserBody):
    a = _adapter(request)
    uid = await a.users_repo.create(name=body.name, is_boss=False)
    if body.is_boss:
        await BossPromotionService(a.pool).promote(uid)
    return {"id": uid}


@router.patch("/api/users/{uid}")
async def update_user(request: Request, uid: str, body: CreateUserBody):
    a = _adapter(request)
    await a.users_repo.rename(uid, body.name)
    existing = await a.users_repo.get(uid)
    if existing is None:
        raise HTTPException(404, "user not found")
    if body.is_boss and not existing["is_boss"]:
        await BossPromotionService(a.pool).promote(uid)
    elif not body.is_boss and existing["is_boss"]:
        await BossPromotionService(a.pool).demote(uid)
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
