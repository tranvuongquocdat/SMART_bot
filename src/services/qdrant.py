import hashlib
import re
from collections import Counter

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
    models,
)

from src.services import openai_client

_qdrant: AsyncQdrantClient | None = None


def _word_hash(word: str) -> int:
    return int(hashlib.md5(word.encode()).hexdigest()[:8], 16)


def _tokenize_bm25(text: str) -> SparseVector:
    words = re.findall(r"\w+", text.lower())
    if not words:
        return SparseVector(indices=[0], values=[0.0])
    counts = Counter(words)
    total = len(words)
    indices = [_word_hash(w) for w in counts]
    values = [c / total for c in counts.values()]
    return SparseVector(indices=indices, values=values)


async def init_qdrant(qdrant_url: str):
    """Init client only."""
    global _qdrant
    _qdrant = AsyncQdrantClient(url=qdrant_url)


async def ensure_collection(collection: str):
    """Create collection if not exists. Dense (1536, cosine) + sparse (BM25 IDF)."""
    existing = [c.name for c in (await _qdrant.get_collections()).collections]
    if collection not in existing:
        await _qdrant.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=1536, distance=Distance.COSINE)},
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        await _qdrant.create_payload_index(
            collection_name=collection, field_name="chat_id", field_schema="integer"
        )


async def provision_collections(boss_chat_id: int):
    """Create messages_{id} and tasks_{id} collections for new boss."""
    await ensure_collection(f"messages_{boss_chat_id}")
    await ensure_collection(f"tasks_{boss_chat_id}")


async def upsert(collection: str, point_id: int, chat_id: int, role: str, text: str, vector: list[float]):
    """Upsert message point with dense + BM25 sparse vectors."""
    sparse = _tokenize_bm25(text)
    point = PointStruct(
        id=point_id,
        vector={"dense": vector, "bm25": sparse},
        payload={"chat_id": chat_id, "role": role, "text": text},
    )
    await _qdrant.upsert(collection_name=collection, points=[point])


async def upsert_task(collection: str, record_id: str, text: str, vector: list[float]):
    """Upsert task point. Use hash of record_id as point id."""
    point_id = int(hashlib.md5(record_id.encode()).hexdigest()[:15], 16)
    sparse = _tokenize_bm25(text)
    point = PointStruct(
        id=point_id,
        vector={"dense": vector, "bm25": sparse},
        payload={"record_id": record_id, "text": text},
    )
    await _qdrant.upsert(collection_name=collection, points=[point])


async def delete_task(collection: str, record_id: str):
    """Delete task point by record_id hash."""
    point_id = int(hashlib.md5(record_id.encode()).hexdigest()[:15], 16)
    await _qdrant.delete(collection_name=collection, points_selector=[point_id])


async def search(collection: str, query: str, chat_id: int | None = None, top_n: int = 5) -> list[dict]:
    """Hybrid search (dense + BM25 RRF fusion). Optional chat_id filter. Returns list of dicts with role, content, record_id keys."""
    query_vector = await openai_client.embed(query)
    query_sparse = _tokenize_bm25(query)

    if chat_id is not None:
        chat_filter = Filter(
            must=[FieldCondition(key="chat_id", match=MatchValue(value=chat_id))]
        )
        prefetch = [
            Prefetch(query=query_vector, using="dense", limit=20, filter=chat_filter),
            Prefetch(query=query_sparse, using="bm25", limit=20, filter=chat_filter),
        ]
    else:
        prefetch = [
            Prefetch(query=query_vector, using="dense", limit=20),
            Prefetch(query=query_sparse, using="bm25", limit=20),
        ]

    results = await _qdrant.query_points(
        collection_name=collection,
        prefetch=prefetch,
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_n,
    )

    return [
        {
            "role": p.payload.get("role", ""),
            "content": p.payload.get("text", ""),
            "record_id": p.payload.get("record_id", ""),
        }
        for p in results.points
    ]


async def close_qdrant():
    if _qdrant:
        await _qdrant.close()
