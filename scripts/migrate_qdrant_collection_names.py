"""One-shot migration: rename existing Qdrant collections to include the
embedding_dim suffix.

Idempotent — exits 0 if there are no old-format collections.

    python scripts/migrate_qdrant_collection_names.py [--qdrant-url ...] [--dim 1536]
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance, SparseVectorParams, VectorParams,
)
from qdrant_client.http import models


# Old format: messages_<UUID>  or  tasks_<UUID>
# New format: messages_<UUID>_<dim>  or  tasks_<UUID>_<dim>
_OLD_PATTERN = re.compile(
    r"^(?P<prefix>messages|tasks)_(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)


async def _list_collection_names(client: AsyncQdrantClient) -> list[str]:
    res = await client.get_collections()
    return [c.name for c in res.collections]


async def _copy_collection(
    client: AsyncQdrantClient, old_name: str, new_name: str, dim: int,
) -> int:
    """Create new collection with the same shape, scroll all points to it.
    Returns number of points copied."""
    await client.create_collection(
        collection_name=new_name,
        vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
        sparse_vectors_config={
            "bm25": SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    await client.create_payload_index(
        collection_name=new_name, field_name="chat_id", field_schema="keyword"
    )

    total = 0
    next_offset = None
    while True:
        points, next_offset = await client.scroll(
            collection_name=old_name,
            limit=128,
            with_payload=True,
            with_vectors=True,
            offset=next_offset,
        )
        if not points:
            break
        await client.upsert(collection_name=new_name, points=points)
        total += len(points)
        if next_offset is None:
            break
    return total


async def _migrate(qdrant_url: str, default_dim: int) -> int:
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        names = await _list_collection_names(client)
        old_format = [n for n in names if _OLD_PATTERN.match(n)]
        if not old_format:
            print("No collections in old format. Already migrated.")
            return 0

        print(f"Found {len(old_format)} old-format collections: {old_format}")

        for old in old_format:
            new = f"{old}_{default_dim}"
            if new in names:
                print(f"  {old} → {new} (target exists, skip rename, delete old)")
                await client.delete_collection(collection_name=old)
                continue
            print(f"  copy {old} → {new} ...")
            count = await _copy_collection(client, old, new, default_dim)
            print(f"    {count} points copied")
            await client.delete_collection(collection_name=old)
            print(f"    {old} deleted")

        print("Done.")
        return 0
    finally:
        await client.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--qdrant-url", default="http://localhost:6333")
    p.add_argument("--dim", type=int, default=1536,
                   help="Embedding dim of the existing collections (default 1536)")
    args = p.parse_args()
    return asyncio.run(_migrate(args.qdrant_url, args.dim))


if __name__ == "__main__":
    sys.exit(main())
