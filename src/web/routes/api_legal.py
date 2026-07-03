"""Legal documents — ToS/Privacy có version + acceptance (PDPL).

Spec: docs/superpowers/specs/2026-07-02-legal-consent-design.md
  - GET  /api/v1/legal/{kind}            public — bản active (trang /terms, /privacy)
  - GET  /api/v1/legal/acceptance-status user đã login — còn bản nào chưa chấp nhận
  - POST /api/v1/legal/accept            ghi acceptance mọi bản active
  - GET  /api/v1/superadmin/legal        list mọi version
  - POST /api/v1/superadmin/legal/{kind} publish version mới (deactivate bản cũ)
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from src.repositories.base import BossContext
from src.web.deps import get_current_boss, get_db, require_superadmin
from src.web.security import verify_json_csrf

router = APIRouter(prefix="/api/v1", tags=["legal"])

KINDS = ("terms", "privacy")


async def _pending_kinds(db: asyncpg.Pool, user_id: int) -> list[dict]:
    """Các bản active user CHƯA chấp nhận. Bảng rỗng (chưa seed) = không chặn."""
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT d.kind, d.version
            FROM legal_documents d
            WHERE d.is_active
              AND NOT EXISTS (
                SELECT 1 FROM legal_acceptances a
                WHERE a.user_id = $1 AND a.kind = d.kind AND a.version = d.version)
            ORDER BY d.kind
            """,
            user_id,
        )
    return [dict(r) for r in rows]


@router.get("/legal/acceptance-status")
async def acceptance_status(
    ctx: BossContext = Depends(get_current_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    pending = await _pending_kinds(db, ctx.boss_id)
    return {"pending": pending, "needs_acceptance": bool(pending)}


@router.post("/legal/accept", dependencies=[Depends(verify_json_csrf)])
async def accept_legal(
    ctx: BossContext = Depends(get_current_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    pending = await _pending_kinds(db, ctx.boss_id)
    async with db.acquire() as c:
        for p in pending:
            await c.execute(
                """
                INSERT INTO legal_acceptances (user_id, kind, version)
                VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                """,
                ctx.boss_id, p["kind"], p["version"],
            )
    return {"accepted": [p["kind"] for p in pending]}


# Public — SPA trang /terms, /privacy đọc bản active (không cần đăng nhập).
@router.get("/legal/{kind}")
async def get_legal_document(kind: str, db: asyncpg.Pool = Depends(get_db)) -> dict:
    if kind not in KINDS:
        raise HTTPException(404, "Unknown document")
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT kind, version, content_md, published_at
            FROM legal_documents WHERE kind=$1 AND is_active
            ORDER BY version DESC LIMIT 1
            """,
            kind,
        )
    if row is None:
        raise HTTPException(404, "Document not published yet")
    return {
        "kind": row["kind"],
        "version": row["version"],
        "content_md": row["content_md"],
        "published_at": row["published_at"].isoformat(),
    }


# ---- superadmin ------------------------------------------------------------

sa_router = APIRouter(prefix="/api/v1/superadmin/legal", tags=["superadmin"])


@sa_router.get("")
async def list_legal_documents(
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT d.id, d.kind, d.version, d.content_md, d.published_at, d.is_active,
                   (SELECT count(*) FROM legal_acceptances a
                     WHERE a.kind = d.kind AND a.version = d.version) AS acceptances
            FROM legal_documents d ORDER BY d.kind, d.version DESC
            """
        )
    return [
        {**dict(r), "published_at": r["published_at"].isoformat()} for r in rows
    ]


@sa_router.post("/{kind}", dependencies=[Depends(verify_json_csrf)])
async def publish_legal_document(
    kind: str,
    payload: dict,
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> dict:
    """Publish version mới: deactivate bản cũ, users sẽ bị hỏi chấp nhận lại."""
    if kind not in KINDS:
        raise HTTPException(404, "Unknown document")
    content = (payload.get("content_md") or "").strip()
    if not content:
        raise HTTPException(422, "content_md required")
    async with db.acquire() as c:
        async with c.transaction():
            version = await c.fetchval(
                "SELECT coalesce(max(version), 0) + 1 FROM legal_documents WHERE kind=$1",
                kind,
            )
            await c.execute(
                "UPDATE legal_documents SET is_active=FALSE WHERE kind=$1", kind
            )
            await c.execute(
                "INSERT INTO legal_documents (kind, version, content_md) VALUES ($1,$2,$3)",
                kind, version, content,
            )
    return {"kind": kind, "version": version}
