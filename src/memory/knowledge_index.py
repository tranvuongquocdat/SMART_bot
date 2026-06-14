"""KnowledgeIndex — Qdrant index + hybrid retrieval cho knowledge_items.

Build path "đúng từ gốc" để KHÔNG lặp weak-spot của dense.py (messages):
- ts (epoch) + scope vào payload → lọc thời gian + nhóm NGAY trong Qdrant (pre-filter),
  không lọc hậu kỳ SQL.
- Hybrid = dense (Qdrant) + lexical (KnowledgeRepo.search_fts) fuse bằng RRF.
- Cùng collection `smart_bot`; discriminator payload `kind="knowledge"` (tách khỏi message/memory).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.domain.knowledge import KnowledgeItem
from src.repositories.knowledge import KnowledgeRepo

COLLECTION = "smart_bot"
EMBED_MODEL = "text-embedding-3-small"  # khớp collection hiện tại; swap gemini = đổi config sau
RRF_K0 = 60


def _epoch(dt: datetime | None) -> int:
    return int((dt or datetime.now(timezone.utc)).timestamp())


class KnowledgeIndex:
    def __init__(self, pool, qdrant, llm, embed_model: str = EMBED_MODEL):
        self.pool = pool
        self.qdrant = qdrant
        self.llm = llm
        self.embed_model = embed_model

    async def index(self, item: KnowledgeItem) -> str:
        """Embed content + upsert Qdrant. Trả point_id (caller lưu qua set_qdrant_point)."""
        [vec] = await self.llm.embed([item.content], model=self.embed_model)
        pid = item.qdrant_point_id or str(uuid.uuid4())
        await self.qdrant.upsert(
            collection_name=COLLECTION,
            points=[{
                "id": pid,
                "vector": vec,
                "payload": {
                    "boss_id": item.boss_id,
                    "kind": "knowledge",
                    "item_id": item.id,
                    "provider": item.provider,
                    "chat_id": item.chat_id,
                    "item_kind": item.kind,
                    "ts": _epoch(item.created_at),
                },
            }],
        )
        return pid

    async def remove(self, point_id: str) -> None:
        await self.qdrant.delete(collection_name=COLLECTION, points_selector=[point_id])

    async def search_dense(
        self, query: str, boss_id: int, *, chat_id: str | None = None,
        after: datetime | None = None, before: datetime | None = None, k: int = 30,
    ) -> list[tuple[int, float]]:
        [vec] = await self.llm.embed([query], model=self.embed_model)
        must = [
            {"key": "boss_id", "match": {"value": boss_id}},
            {"key": "kind", "match": {"value": "knowledge"}},
        ]
        if chat_id:
            must.append({"key": "chat_id", "match": {"value": chat_id}})
        rng: dict = {}
        if after is not None:
            rng["gte"] = _epoch(after)
        if before is not None:
            rng["lt"] = _epoch(before)
        if rng:
            must.append({"key": "ts", "range": rng})  # time-filter IN Qdrant, không hậu kỳ
        resp = await self.qdrant.query_points(
            collection_name=COLLECTION, query=vec,
            query_filter={"must": must}, limit=k,
        )
        return [(int(p.payload["item_id"]), float(p.score)) for p in resp.points]

    async def search(
        self, repo: KnowledgeRepo, query: str, *, boss_id: int,
        provider: str | None = None, chat_id: str | None = None,
        after: datetime | None = None, before: datetime | None = None, k: int = 20,
    ) -> list[KnowledgeItem]:
        """Hybrid dense+lexical, fuse RRF. Scope boss bắt buộc; chat/time đẩy xuống filter."""
        wide = max(k, 30)
        dense = await self.search_dense(
            query, boss_id, chat_id=chat_id, after=after, before=before, k=wide)
        fts = await repo.search_fts(
            query, provider=provider, chat_id=chat_id,
            after=after, before=before, limit=wide)

        scores: dict[int, float] = {}
        for rank, (iid, _s) in enumerate(dense):
            scores[iid] = scores.get(iid, 0.0) + 1.0 / (RRF_K0 + rank)
        for rank, item in enumerate(fts):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (RRF_K0 + rank)

        order = sorted(scores, key=lambda i: scores[i], reverse=True)[:k]
        have = {it.id: it for it in fts}
        missing = [i for i in order if i not in have]
        for it in await repo.get_many(missing):
            have[it.id] = it
        return [have[i] for i in order if i in have]
