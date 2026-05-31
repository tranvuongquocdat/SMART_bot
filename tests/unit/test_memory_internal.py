import pytest

from src.domain.memory import MemoryScope


class _FakeRepo:
    def __init__(self, *_a, **_kw):
        self.inserted: list = []
        self.updated: list = []
        self.qdrant_points: dict[int, str] = {}

    async def get(self, scope, key):
        return None

    async def get_by_id(self, mid):
        from src.domain.memory import Memory

        return Memory(
            id=mid,
            boss_id=1,
            scope=MemoryScope.SEMANTIC,
            key="k",
            content="content",
            meta={},
            qdrant_point_id=self.qdrant_points.get(mid),
            source="agent_tool",
        )

    async def upsert(self, scope, key, content, meta, source):
        self.inserted.append(("upsert", scope, key, content))
        return 1

    async def insert(self, scope, content, meta, source):
        self.inserted.append(("insert", scope, content))
        return 2

    async def update_content(self, mid, content):
        self.updated.append((mid, content))

    async def set_qdrant_point(self, mid, qpoint):
        self.qdrant_points[mid] = qpoint

    async def list_by_scope(self, scope, limit):
        return []

    async def list_by_ids(self, ids):
        return []

    async def delete(self, mid):
        pass


class _FakeQdrant:
    def __init__(self):
        self.upserts: list = []
        self.deletes: list = []

    async def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    async def search(self, **_kw):
        return []

    async def delete(self, collection_name, points_selector):
        self.deletes.append((collection_name, points_selector))


class _FakeLLM:
    async def embed(self, texts, model):
        return [[0.1] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_write_short_content_skips_qdrant(monkeypatch):
    from src.memory import internal as mod

    fake_repo = _FakeRepo()
    monkeypatch.setattr(mod, "MemoryEntriesRepo", lambda *_a, **_kw: fake_repo)
    qdrant = _FakeQdrant()
    provider = mod.InternalMemoryProvider(pool=None, qdrant=qdrant, llm_gateway=_FakeLLM())
    await provider.write(MemoryScope.EPISODIC, "short", boss_id=1)
    assert qdrant.upserts == []


@pytest.mark.asyncio
async def test_write_long_content_upserts_qdrant(monkeypatch):
    from src.memory import internal as mod

    fake_repo = _FakeRepo()
    monkeypatch.setattr(mod, "MemoryEntriesRepo", lambda *_a, **_kw: fake_repo)
    qdrant = _FakeQdrant()
    provider = mod.InternalMemoryProvider(pool=None, qdrant=qdrant, llm_gateway=_FakeLLM())
    long_text = "this is a long enough content string for embedding"
    await provider.write(MemoryScope.SEMANTIC, long_text, boss_id=1, key="alias")
    assert len(qdrant.upserts) == 1
    coll, points = qdrant.upserts[0]
    assert coll == "smart_bot"
    assert points[0]["payload"]["kind"] == "memory_semantic"


@pytest.mark.asyncio
async def test_recall_no_query_lists_by_scope(monkeypatch):
    from src.memory import internal as mod

    fake_repo = _FakeRepo()
    monkeypatch.setattr(mod, "MemoryEntriesRepo", lambda *_a, **_kw: fake_repo)
    provider = mod.InternalMemoryProvider(
        pool=None, qdrant=_FakeQdrant(), llm_gateway=_FakeLLM()
    )
    out = await provider.recall(MemoryScope.SEMANTIC, None, boss_id=1, k=3)
    assert out == []
