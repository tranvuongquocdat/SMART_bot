from qdrant_client import AsyncQdrantClient

from src.config import settings


def create_qdrant() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.QDRANT_URL)
