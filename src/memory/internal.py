import uuid

from src.domain.memory import Memory, MemoryScope
from src.repositories.base import BossContext
from src.repositories.memory_entries import MemoryEntriesRepo

COLLECTION = "smart_bot"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


def _ctx(boss_id: int) -> BossContext:
    return BossContext(boss_id=boss_id, user_role="boss")


class InternalMemoryProvider:
    def __init__(self, pool, qdrant, llm_gateway):
        self.pool = pool
        self.qdrant = qdrant
        self.llm = llm_gateway

    async def write(
        self,
        scope: MemoryScope,
        content: str,
        boss_id: int,
        meta: dict | None = None,
        key: str | None = None,
    ) -> Memory:
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        if scope == MemoryScope.SEMANTIC and key:
            existing = await repo.get(scope, key)
            if existing:
                await repo.update_content(existing.id, content)
                mem_id = existing.id
                qpoint = existing.qdrant_point_id
            else:
                mem_id = await repo.upsert(
                    scope=scope,
                    key=key,
                    content=content,
                    meta=meta or {},
                    source="agent_tool",
                )
                qpoint = None
        else:
            mem_id = await repo.insert(
                scope=scope,
                content=content,
                meta=meta or {},
                source="agent_tool",
            )
            qpoint = None

        if len(content) > 20:
            qpoint = qpoint or str(uuid.uuid4())
            [vec] = await self.llm.embed([content], model=EMBED_MODEL)
            await self.qdrant.upsert(
                collection_name=COLLECTION,
                points=[
                    {
                        "id": qpoint,
                        "vector": vec,
                        "payload": {
                            "boss_id": boss_id,
                            "kind": f"memory_{scope.value}",
                            "memory_id": mem_id,
                            "key": key,
                        },
                    }
                ],
            )
            await repo.set_qdrant_point(mem_id, qpoint)

        out = await repo.get_by_id(mem_id)
        assert out is not None
        return out

    async def recall(
        self,
        scope: MemoryScope,
        query: str | None,
        boss_id: int,
        k: int = 5,
    ) -> list[Memory]:
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        if query is None or len(query) < 3:
            return await repo.list_by_scope(scope, limit=k)
        [vec] = await self.llm.embed([query], model=EMBED_MODEL)
        hits = await self.qdrant.search(
            collection_name=COLLECTION,
            query_vector=vec,
            query_filter={
                "must": [
                    {"key": "boss_id", "match": {"value": boss_id}},
                    {"key": "kind", "match": {"value": f"memory_{scope.value}"}},
                ]
            },
            limit=k,
        )
        mem_ids = [h.payload["memory_id"] for h in hits]
        return await repo.list_by_ids(mem_ids)

    async def forget(self, memory_id: int, boss_id: int) -> None:
        repo = MemoryEntriesRepo(self.pool, _ctx(boss_id))
        m = await repo.get_by_id(memory_id)
        if m and m.qdrant_point_id:
            await self.qdrant.delete(
                collection_name=COLLECTION,
                points_selector=[m.qdrant_point_id],
            )
        await repo.delete(memory_id)


async def ensure_collection(qdrant) -> None:
    from qdrant_client.http.models import Distance, VectorParams

    cols = await qdrant.get_collections()
    if not any(c.name == COLLECTION for c in cols.collections):
        await qdrant.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
