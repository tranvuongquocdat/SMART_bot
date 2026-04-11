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
_collection: str = ""


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


async def init_qdrant(qdrant_url: str, collection: str):
    global _qdrant, _collection
    _collection = collection
    _qdrant = AsyncQdrantClient(url=qdrant_url)

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


async def upsert(msg_id: int, chat_id: int, role: str, text: str, vector: list[float]):
    sparse = _tokenize_bm25(text)
    point = PointStruct(
        id=msg_id,
        vector={"dense": vector, "bm25": sparse},
        payload={"chat_id": chat_id, "role": role, "text": text},
    )
    await _qdrant.upsert(collection_name=_collection, points=[point])


async def search(query: str, chat_id: int, top_n: int = 5) -> list[dict]:
    query_vector = await openai_client.embed(query)
    query_sparse = _tokenize_bm25(query)

    chat_filter = Filter(
        must=[FieldCondition(key="chat_id", match=MatchValue(value=chat_id))]
    )

    results = await _qdrant.query_points(
        collection_name=_collection,
        prefetch=[
            Prefetch(query=query_vector, using="dense", limit=20, filter=chat_filter),
            Prefetch(query=query_sparse, using="bm25", limit=20, filter=chat_filter),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_n,
    )

    return [
        {"role": p.payload["role"], "content": p.payload["text"]}
        for p in results.points
    ]


async def close_qdrant():
    if _qdrant:
        await _qdrant.close()
