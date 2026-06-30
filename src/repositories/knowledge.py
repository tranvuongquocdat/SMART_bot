"""KnowledgeRepo — Lớp 1 store với invariant CỨNG: soft-delete + revision-logging.

- KHÔNG có method hard-delete knowledge_items (no silent rewrite — watchlist #1 +
  must-fix bảo mật). "Xoá" = status='deleted', giữ row + lịch sử.
- Mọi mutation (add/update/delete/restore) ghi knowledge_revisions trong CÙNG transaction.
- Mọi query scope theo self.ctx.boss_id (tenant isolation — bắt buộc).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from src.domain.knowledge import (
    KnowledgeItem,
    KnowledgeStatus,
    RevisionActor,
    RevisionOp,
)
from src.repositories.base import BossScopedRepo


def _v(x: Any) -> Any:
    return x.value if hasattr(x, "value") else x


def _row_to_item(r: asyncpg.Record) -> KnowledgeItem:
    meta = r["meta_json"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return KnowledgeItem(
        id=r["id"], boss_id=r["boss_id"], kind=r["kind"], content=r["content"],
        status=r["status"], title=r["title"], provider=r["provider"],
        chat_id=r["chat_id"], project_id=r["project_id"],
        importance=r["importance"], confidence=r["confidence"],
        valid_from=r["valid_from"], valid_to=r["valid_to"],
        assignee_name=r["assignee_name"], due_at=r["due_at"],
        qdrant_point_id=r["qdrant_point_id"], meta=meta or {},
        created_at=r["created_at"], updated_at=r["updated_at"],
    )


def _snapshot(item: KnowledgeItem) -> dict[str, Any]:
    return {
        "kind": item.kind, "title": item.title, "content": item.content,
        "status": item.status, "importance": item.importance,
        "confidence": item.confidence, "project_id": item.project_id,
        "provider": item.provider, "chat_id": item.chat_id,
        "assignee_name": item.assignee_name,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
        "valid_to": item.valid_to.isoformat() if item.valid_to else None,
        "meta": item.meta,
    }


class KnowledgeRepo(BossScopedRepo):
    # ---- read ----------------------------------------------------------
    async def get(self, item_id: int) -> KnowledgeItem | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM knowledge_items WHERE id=$1 AND boss_id=$2",
                item_id, self.ctx.boss_id,
            )
        return _row_to_item(row) if row else None

    async def list_all(
        self, *, provider: str | None = None, chat_id: str | None = None,
        kind: str | None = None, status: str | None = KnowledgeStatus.ACTIVE.value,
        project_id: int | None = None, limit: int = 50,
    ) -> list[KnowledgeItem]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM knowledge_items
                WHERE boss_id=$1
                  AND ($2::text   IS NULL OR status=$2)
                  AND ($3::text   IS NULL OR provider=$3)
                  AND ($4::text   IS NULL OR chat_id=$4)
                  AND ($5::text   IS NULL OR kind=$5)
                  AND ($6::bigint IS NULL OR project_id=$6)
                ORDER BY COALESCE(importance, 0) DESC, updated_at DESC
                LIMIT $7
                """,
                self.ctx.boss_id, _v(status), provider, chat_id, _v(kind),
                project_id, limit,
            )
        return [_row_to_item(r) for r in rows]

    async def provenance(self, item_id: int) -> list[int]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """SELECT p.message_id FROM knowledge_provenance p
                   JOIN knowledge_items k ON k.id = p.knowledge_item_id
                   WHERE p.knowledge_item_id=$1 AND k.boss_id=$2
                   ORDER BY p.message_id""",
                item_id, self.ctx.boss_id,
            )
        return [r["message_id"] for r in rows]

    async def search_fts(
        self, query: str, *, provider: str | None = None, chat_id: str | None = None,
        after=None, before=None, limit: int = 20,
    ) -> list[KnowledgeItem]:
        """Lexical leg: FTS tiếng Việt + scope + time + status — TẤT CẢ trong WHERE
        (không lọc hậu kỳ; đối nghịch weak-spot của dense.py messages)."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT *, ts_rank(fts, plainto_tsquery('simple', unaccent($2))) AS rank
                FROM knowledge_items
                WHERE boss_id=$1
                  AND status IN ('active','resolved')
                  AND fts @@ plainto_tsquery('simple', unaccent($2))
                  AND ($3::text        IS NULL OR provider=$3)
                  AND ($4::text        IS NULL OR chat_id=$4)
                  AND ($5::timestamptz IS NULL OR created_at >= $5)
                  AND ($6::timestamptz IS NULL OR created_at <  $6)
                ORDER BY rank DESC
                LIMIT $7
                """,
                self.ctx.boss_id, query, provider, chat_id, after, before, limit,
            )
        return [_row_to_item(r) for r in rows]

    async def workload_summary(
        self, *, chat_id: str | None = None, now: datetime | None = None,
    ) -> dict:
        """Tổng hợp workload theo người TRÊN SPINE: chỉ item có assignee_name (task có chủ).
        open=status'active', done=status'resolved' (đã xong), overdue=active & due_at<now.
        Trả {scope, totals, by_assignee:[{assignee, open, overdue, done, total,
        completion_rate}]} — xếp người nhiều quá-hạn/đang-mở lên trước."""
        now = now or datetime.now(timezone.utc)
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT title, content, assignee_name, status, due_at FROM knowledge_items
                WHERE boss_id=$1 AND assignee_name IS NOT NULL
                  AND status IN ('active','resolved')
                  AND ($2::text IS NULL OR chat_id=$2)
                """,
                self.ctx.boss_id, chat_id,
            )
        agg: dict[str, dict] = {}
        overdue_items = []
        for r in rows:
            name = (r["assignee_name"] or "").strip()
            if not name:
                continue
            b = agg.setdefault(name, {"open": 0, "overdue": 0, "done": 0})
            if r["status"] == "active":
                b["open"] += 1
                if r["due_at"] and r["due_at"] < now:
                    b["overdue"] += 1
                    overdue_items.append({
                        "assignee": name,
                        "what": r["title"] or (r["content"] or "")[:60],
                        "due": r["due_at"].strftime("%Y-%m-%d"),
                    })
            elif r["status"] == "resolved":
                b["done"] += 1
        overdue_items.sort(key=lambda x: x["due"])
        by = []
        for name, b in agg.items():
            total = b["open"] + b["done"]
            by.append({
                "assignee": name, **b, "total": total,
                "completion_rate": round(b["done"] / total, 2) if total else None,
            })
        by.sort(key=lambda x: (x["overdue"], x["open"]), reverse=True)
        totals = {k: sum(b[k] for b in agg.values()) for k in ("open", "overdue", "done")}
        totals["assignees"] = len(agg)
        return {
            "scope": chat_id or "all_groups", "totals": totals, "by_assignee": by,
            "overdue_items": overdue_items[:15],
        }

    async def get_many(self, ids: list[int]) -> list[KnowledgeItem]:
        if not ids:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM knowledge_items WHERE id = ANY($1::bigint[]) "
                "AND boss_id=$2 AND status IN ('active','resolved')",
                ids, self.ctx.boss_id,
            )
        return [_row_to_item(r) for r in rows]

    # ---- write (mọi mutation log revision; KHÔNG hard-delete) ----------
    async def add(
        self, *, kind: str, content: str, title: str | None = None,
        provider: str | None = None, chat_id: str | None = None,
        project_id: int | None = None, importance: int | None = None,
        confidence: float | None = None, valid_from=None, valid_to=None,
        assignee_name: str | None = None, due_at=None,
        meta: dict | None = None, qdrant_point_id: str | None = None,
        source_message_ids: list[int] | None = None,
        actor: str = RevisionActor.EXTRACTOR, reason: str | None = None,
    ) -> KnowledgeItem:
        async with self.pool.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow(
                    """
                    INSERT INTO knowledge_items
                      (boss_id, provider, chat_id, project_id, kind, title, content,
                       importance, confidence, valid_from, valid_to, assignee_name,
                       due_at, qdrant_point_id, meta_json)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                    RETURNING *
                    """,
                    self.ctx.boss_id, provider, chat_id, project_id, _v(kind), title,
                    content, importance, confidence, valid_from, valid_to,
                    assignee_name, due_at, qdrant_point_id, json.dumps(meta or {}),
                )
                item = _row_to_item(row)
                for mid in (source_message_ids or []):
                    await c.execute(
                        "INSERT INTO knowledge_provenance (knowledge_item_id, message_id) "
                        "VALUES ($1,$2) ON CONFLICT DO NOTHING",
                        item.id, mid,
                    )
                await self._log(
                    c, item.id, RevisionOp.ADD.value, _v(actor),
                    None, _snapshot(item), reason,
                    source_message_id=(source_message_ids or [None])[0],
                )
        return item

    async def update(
        self, item_id: int, *, actor: str = RevisionActor.EXTRACTOR,
        reason: str | None = None, source_message_id: int | None = None,
        meta: dict | None = None, **fields: Any,
    ) -> KnowledgeItem | None:
        allowed = {
            "kind", "title", "content", "status", "importance", "confidence",
            "project_id", "valid_from", "valid_to", "qdrant_point_id",
            "assignee_name", "due_at",
        }
        sets = {k: _v(v) for k, v in fields.items() if k in allowed}
        async with self.pool.acquire() as c:
            async with c.transaction():
                before = await c.fetchrow(
                    "SELECT * FROM knowledge_items WHERE id=$1 AND boss_id=$2 FOR UPDATE",
                    item_id, self.ctx.boss_id,
                )
                if before is None:
                    return None
                before_item = _row_to_item(before)
                cols, vals, i = [], [], 3
                for k, v in sets.items():
                    cols.append(f"{k}=${i}")
                    vals.append(v)
                    i += 1
                if meta is not None:
                    cols.append(f"meta_json=${i}::jsonb")
                    vals.append(json.dumps(meta))
                    i += 1
                cols.append("updated_at=NOW()")
                row = await c.fetchrow(
                    f"UPDATE knowledge_items SET {', '.join(cols)} "
                    "WHERE id=$1 AND boss_id=$2 RETURNING *",
                    item_id, self.ctx.boss_id, *vals,
                )
                item = _row_to_item(row)
                await self._log(
                    c, item_id, RevisionOp.UPDATE.value, _v(actor),
                    _snapshot(before_item), _snapshot(item), reason,
                    source_message_id=source_message_id,
                )
        return item

    async def soft_delete(
        self, item_id: int, *, actor: str = RevisionActor.AGENT,
        reason: str | None = None, source_message_id: int | None = None,
    ) -> bool:
        """Đánh dấu deleted — KHÔNG xoá cứng. Giữ row + lịch sử để khôi phục/audit."""
        async with self.pool.acquire() as c:
            async with c.transaction():
                before = await c.fetchrow(
                    "SELECT * FROM knowledge_items WHERE id=$1 AND boss_id=$2 FOR UPDATE",
                    item_id, self.ctx.boss_id,
                )
                if before is None:
                    return False
                await c.execute(
                    "UPDATE knowledge_items SET status='deleted', updated_at=NOW() "
                    "WHERE id=$1 AND boss_id=$2",
                    item_id, self.ctx.boss_id,
                )
                await self._log(
                    c, item_id, RevisionOp.DELETE.value, _v(actor),
                    _snapshot(_row_to_item(before)), None, reason,
                    source_message_id=source_message_id,
                )
        return True

    async def resolve(
        self, item_id: int, *, actor: str = RevisionActor.EXTRACTOR,
        reason: str | None = None, source_message_id: int | None = None,
        content: str | None = None,
    ) -> KnowledgeItem | None:
        """Đóng item nhưng GIỮ vết: status='resolved' (việc đã xong / rủi ro đã xử lý).
        KHÁC soft_delete: KHÔNG gỡ Qdrant point → vẫn tra được để trả lời 'đã xử lý'.
        `content` tuỳ chọn: ghi đè nội dung cho khớp trạng thái đã xử lý (tránh content
        mô tả vấn đề ở thì hiện tại làm responder trả lời 'vẫn còn')."""
        async with self.pool.acquire() as c:
            async with c.transaction():
                before = await c.fetchrow(
                    "SELECT * FROM knowledge_items WHERE id=$1 AND boss_id=$2 FOR UPDATE",
                    item_id, self.ctx.boss_id,
                )
                if before is None:
                    return None
                before_item = _row_to_item(before)
                if content is not None:
                    await c.execute(
                        "UPDATE knowledge_items SET status='resolved', content=$3, "
                        "updated_at=NOW() WHERE id=$1 AND boss_id=$2",
                        item_id, self.ctx.boss_id, content,
                    )
                else:
                    await c.execute(
                        "UPDATE knowledge_items SET status='resolved', updated_at=NOW() "
                        "WHERE id=$1 AND boss_id=$2",
                        item_id, self.ctx.boss_id,
                    )
                after_item = _row_to_item(before)
                after_item.status = KnowledgeStatus.RESOLVED.value
                if content is not None:
                    after_item.content = content
                await self._log(
                    c, item_id, RevisionOp.RESOLVE.value, _v(actor),
                    _snapshot(before_item), _snapshot(after_item), reason,
                    source_message_id=source_message_id,
                )
        return after_item

    async def add_provenance(self, item_id: int, message_ids: list[int]) -> None:
        async with self.pool.acquire() as c:
            owns = await c.fetchval(
                "SELECT 1 FROM knowledge_items WHERE id=$1 AND boss_id=$2",
                item_id, self.ctx.boss_id,
            )
            if not owns:
                return
            for mid in message_ids:
                await c.execute(
                    "INSERT INTO knowledge_provenance (knowledge_item_id, message_id) "
                    "VALUES ($1,$2) ON CONFLICT DO NOTHING",
                    item_id, mid,
                )

    async def set_qdrant_point(self, item_id: int, point_id: str) -> None:
        """Set link vector — KHÔNG log revision (không phải thay đổi nội dung)."""
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE knowledge_items SET qdrant_point_id=$3 "
                "WHERE id=$1 AND boss_id=$2",
                item_id, self.ctx.boss_id, point_id,
            )

    async def _log(
        self, c, item_id: int, op: str, actor: str,
        before: dict | None, after: dict | None, reason: str | None,
        source_message_id: int | None = None,
    ) -> None:
        await c.execute(
            """INSERT INTO knowledge_revisions
                 (knowledge_item_id, op, actor, before_json, after_json, reason,
                  source_message_id)
               VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6,$7)""",
            item_id, op, actor,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            reason, source_message_id,
        )
