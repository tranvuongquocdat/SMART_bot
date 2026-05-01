# Phase 4a — LLM Abstraction + Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the forward-compat foundation Phase 4b will lean on: `LLMClient` Protocol + factory (per-boss credential resolution), `AuditService` skeleton, Qdrant collection naming with embedding-dim suffix. No service layer yet (Phase 4b); existing tool / agent code keeps using the legacy `infrastructure/openai_client.py` module-level functions until services migrate.

**Architecture:** New `infrastructure/llm/` package owns provider abstraction. `OpenAILLMClient` is the single concrete impl, configurable per-instance. `LLMClientFactory` reads `boss.llm_*` columns (Phase 3 forward-compat); falls back to `Settings.openai_*` when NULL. Qdrant collection names get a `_{embed_dim}` suffix so future embedding-model swaps don't collide. A small migration script renames existing Qdrant collections in place. Existing callers of the legacy openai client are **not** touched — Phase 4b services migrate them.

**Tech Stack:** Python 3.11+, openai SDK (existing), qdrant-client (existing), pytest with `asyncio_mode = auto`.

**Spec reference:** [docs/superpowers/specs/2026-04-28-platform-channel-and-layered-architecture-design.md](../specs/2026-04-28-platform-channel-and-layered-architecture-design.md), Phase 4 — the **forward-compat sub-set** of Phase 4 (`infrastructure/llm/`, `AuditService` interface, Qdrant naming).

---

## Scope Notes

**In scope:**

- `infrastructure/llm/` package: `base.py` Protocol, `openai.py` concrete impl, `factory.py` `get_llm_client(boss, settings)`.
- `services/` package skeleton + `services/audit_service.py` (one method, no callers yet — Phase 4b wires).
- `Settings.openai_embedding_dim: int = 1536` (matches `text-embedding-3-small`).
- Qdrant collection naming: `messages_{boss_uuid}_{embed_dim}` and `tasks_{boss_uuid}_{embed_dim}`. Update `provision_collections`, `ensure_collection`, and the call site in `src/context.py` that builds `ChatContext.messages_collection` / `tasks_collection`.
- Migration script `scripts/migrate_qdrant_collection_names.py`: renames existing `messages_{uuid}` collections to `messages_{uuid}_{dim}` (Qdrant has no rename API → copy-and-delete pattern with explicit dim).
- Manual smoke test: boot bot, DM "hello", confirm Qdrant write/query goes to `messages_{uuid}_1536` collection (200 OK), reply succeeds.

**Out of scope (Phase 4b):**

- Service layer: every service (`task_service`, `person_service`, `reminder_service`, …) — Phase 4b.
- Handler classes + `tool_dispatcher.py` + `tool_definitions.py` — Phase 4b.
- Agent classes (`secretary_agent.py`, `reminder_agent.py`, `advisor_agent.py`, `onboarding_agent.py`) — Phase 4b.
- Refactoring existing `infrastructure/openai_client.py` callers (advisor.py, agent.py, scheduler.py, onboarding.py, tools/*.py, qdrant_client.py) — Phase 4b switches them to inject `LLMClient`.
- Wiring `AuditService.log()` into actions — Phase 4b.
- Encryption-key rotation tooling — out of all phases.

---

## File Structure After This Phase

```
src/
├── infrastructure/
│   ├── llm/                       # NEW package
│   │   ├── __init__.py
│   │   ├── base.py                # LLMClient Protocol
│   │   ├── openai.py              # OpenAILLMClient (only impl this phase)
│   │   └── factory.py             # get_llm_client(boss, settings)
│   ├── openai_client.py           # UNCHANGED — Phase 4b will phase out
│   ├── qdrant_client.py           # MODIFIED — collection name takes dim
│   └── crypto.py                  # UNCHANGED (used by factory)
│
├── services/                      # NEW package
│   ├── __init__.py
│   └── audit_service.py           # AuditService — single log() method
│
├── context.py                     # MODIFIED — collection names include _{dim}
└── config.py                      # MODIFIED — add openai_embedding_dim

scripts/
└── migrate_qdrant_collection_names.py   # NEW — rename existing collections

tests/unit/
├── test_llm_factory.py            # NEW
└── test_audit_service.py          # NEW
```

---

## Task 1 — Add `Settings.openai_embedding_dim`

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Add the field**

Open `src/config.py`. Add `openai_embedding_dim` next to the embedding model:

```python
    openai_api_key: str
    openai_chat_model: str = "gpt-5.4"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dim: int = 1536      # text-embedding-3-small = 1536
```

- [ ] **Step 2: Boot-check**

```bash
uv run python -c "from src.config import Settings; print(Settings().openai_embedding_dim)"
```

Expected: `1536`.

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat(config): add openai_embedding_dim setting (default 1536)"
```

---

## Task 2 — `infrastructure/llm/base.py` — `LLMClient` Protocol

**Files:**
- Create: `src/infrastructure/llm/__init__.py`
- Create: `src/infrastructure/llm/base.py`

- [ ] **Step 1: Create the package init**

Create `src/infrastructure/llm/__init__.py` (empty):

```python
```

- [ ] **Step 2: Define the Protocol**

Create `src/infrastructure/llm/base.py`:

```python
"""Provider-agnostic LLM client Protocol.

Implementations live in this package (`openai.py`, future `groq.py`,
`gemini.py`, `anthropic.py`). Services depend on this Protocol — never on
a concrete provider — so swapping providers per boss is a constructor
choice, not a refactor.

Shape rationale:
- `chat_with_tools` returns the same shape today's `infrastructure.openai_client`
  returns (a (response, usage_dict) tuple). Phase 4b wraps tool-call routing
  on top so the surface to services is uniform across providers later.
- `embed` returns (vector, dim) so callers (Qdrant naming, capacity checks)
  see the dim in-band rather than reading it from a global setting.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """A configured LLM provider client. Holds credentials + model choices."""

    @property
    def chat_model(self) -> str: ...

    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_dim(self) -> int: ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        """Run a chat completion with tools. Returns (response, usage)."""
        ...

    async def embed(self, text: str) -> tuple[list[float], int]:
        """Return (embedding_vector, dim)."""
        ...
```

- [ ] **Step 3: Boot-check**

```bash
uv run python -c "from src.infrastructure.llm.base import LLMClient; print(LLMClient)"
```

Expected: `<class 'src.infrastructure.llm.base.LLMClient'>`.

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/llm/__init__.py src/infrastructure/llm/base.py
git commit -m "feat(infrastructure/llm): add LLMClient Protocol"
```

---

## Task 3 — `infrastructure/llm/openai.py` — concrete impl

**Files:**
- Create: `src/infrastructure/llm/openai.py`

- [ ] **Step 1: Implement `OpenAILLMClient`**

The class is a thin object wrapper over the existing `infrastructure/openai_client.py` module-level functions. Why not call `openai.AsyncOpenAI` directly? Because the legacy module already handles retries + token-usage logging hooks; reproducing that here would duplicate code. Phase 4b can collapse the legacy module into this impl once all callers move over.

Create `src/infrastructure/llm/openai.py`:

```python
"""OpenAI implementation of LLMClient.

Composes the existing module-level `infrastructure.openai_client` for the
actual HTTP/SDK calls but presents a per-instance configured object so
factory + per-boss credentials work cleanly.
"""
from __future__ import annotations

from typing import Any

from src.infrastructure import openai_client as _legacy
from src.infrastructure.llm.base import LLMClient


class OpenAILLMClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        embedding_dim: int,
    ) -> None:
        self._api_key = api_key
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict]:
        # Legacy module reads its own globals (api_key + model) for now.
        # When Phase 4b migrates services off the legacy module, we'll inline
        # the SDK call here using self._api_key + self._chat_model.
        return await _legacy.chat_with_tools(
            messages, tools=tools, model=model or self._chat_model, **kwargs,
        )

    async def embed(self, text: str) -> tuple[list[float], int]:
        vec = await _legacy.embed(text)
        return vec, self._embedding_dim
```

- [ ] **Step 2: Boot-check**

```bash
uv run python -c "from src.infrastructure.llm.openai import OpenAILLMClient; c = OpenAILLMClient('sk-x', 'gpt-x', 'emb-x', 1536); print(c.embedding_dim)"
```

Expected: `1536`.

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/llm/openai.py
git commit -m "feat(infrastructure/llm): add OpenAILLMClient concrete impl"
```

---

## Task 4 — `infrastructure/llm/factory.py` — per-boss client builder

**Files:**
- Create: `src/infrastructure/llm/factory.py`
- Create: `tests/unit/test_llm_factory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_llm_factory.py`:

```python
"""Tests for LLMClient factory — boss override vs Settings fallback."""
from __future__ import annotations

import pytest

from src.config import Settings
from src.infrastructure import crypto
from src.infrastructure.llm.factory import get_llm_client
from src.infrastructure.llm.openai import OpenAILLMClient


def _settings(**overrides) -> Settings:
    base = {
        "telegram_bot_token": "x",
        "lark_app_id": "x",
        "lark_app_secret": "x",
        "openai_api_key": "sk-default",
        "cohere_api_key": "x",
    }
    base.update(overrides)
    return Settings(**base)


def test_no_boss_config_falls_back_to_settings():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": None, "llm_model": None, "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    assert isinstance(client, OpenAILLMClient)
    assert client.chat_model == s.openai_chat_model
    assert client.embedding_model == s.openai_embedding_model
    assert client.embedding_dim == s.openai_embedding_dim


def test_boss_overrides_chat_model():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "openai", "llm_model": "gpt-5-pro",
        "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    assert client.chat_model == "gpt-5-pro"


def test_boss_encrypted_key_is_decrypted():
    key = crypto.generate_key()
    s = _settings(boss_credential_encryption_key=key)
    encrypted = crypto.encrypt("sk-boss-secret", key=key)
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "openai", "llm_model": None,
        "llm_api_key_encrypted": encrypted,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    client = get_llm_client(boss, s)
    # access the private attr to verify decryption
    assert client._api_key == "sk-boss-secret"


def test_boss_embedding_dim_overrides():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": None, "llm_model": None, "llm_api_key_encrypted": None,
        "embedding_provider": "openai", "embedding_model": "text-embedding-3-large",
        "embedding_dim": 3072,
    }
    client = get_llm_client(boss, s)
    assert client.embedding_dim == 3072
    assert client.embedding_model == "text-embedding-3-large"


def test_unknown_provider_raises():
    s = _settings()
    boss = {
        "chat_id": "uuid-1", "name": "Boss",
        "llm_provider": "groq", "llm_model": "llama-3.1",
        "llm_api_key_encrypted": None,
        "embedding_provider": None, "embedding_model": None, "embedding_dim": None,
    }
    with pytest.raises(ValueError, match="provider 'groq' not supported"):
        get_llm_client(boss, s)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_llm_factory.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.infrastructure.llm.factory'`.

- [ ] **Step 3: Implement the factory**

Create `src/infrastructure/llm/factory.py`:

```python
"""LLMClient factory — resolves per-boss credentials with Settings fallback.

Today: only `openai` provider. Future Groq/Gemini/Anthropic = add a branch
in `_build_client`. Boss columns are forward-compat (Phase 3); NULL means
fall back to Settings.
"""
from __future__ import annotations

from src.config import Settings
from src.infrastructure import crypto
from src.infrastructure.llm.base import LLMClient
from src.infrastructure.llm.openai import OpenAILLMClient


_SUPPORTED_PROVIDERS = {"openai"}


def _resolve(boss_field, settings_field):
    """boss column wins if non-empty, else Settings."""
    if boss_field:
        return boss_field
    return settings_field


def _decrypt_boss_key(boss: dict, settings: Settings) -> str:
    encrypted = boss.get("llm_api_key_encrypted")
    if not encrypted:
        return settings.openai_api_key
    return crypto.decrypt(encrypted, key=settings.boss_credential_encryption_key)


def get_llm_client(boss: dict, settings: Settings) -> LLMClient:
    """Build an LLMClient configured for `boss`. Falls back to Settings for
    any column the boss row doesn't set."""
    provider = _resolve(boss.get("llm_provider"), "openai")
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"provider {provider!r} not supported; supported: {sorted(_SUPPORTED_PROVIDERS)}"
        )

    if provider == "openai":
        return OpenAILLMClient(
            api_key=_decrypt_boss_key(boss, settings),
            chat_model=_resolve(boss.get("llm_model"), settings.openai_chat_model),
            embedding_model=_resolve(
                boss.get("embedding_model"), settings.openai_embedding_model
            ),
            embedding_dim=_resolve(
                boss.get("embedding_dim"), settings.openai_embedding_dim
            ),
        )
    raise AssertionError("unreachable")  # _SUPPORTED_PROVIDERS gate
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_llm_factory.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/infrastructure/llm/factory.py tests/unit/test_llm_factory.py
git commit -m "feat(infrastructure/llm): add factory with per-boss credential resolution"
```

---

## Task 5 — `services/audit_service.py`

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/audit_service.py`
- Create: `tests/unit/test_audit_service.py`

> Why ship `AuditService` in 4a not 4b? Because Phase 4b has 15 services to write; introducing the `services/` folder + the simplest impl now lets Phase 4b focus on porting tools, not on layout decisions. Plus this validates the constructor-injection pattern (`__init__(repo)`) that all future services follow.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_audit_service.py`:

```python
"""Tests for AuditService — round-trip log + list."""
from __future__ import annotations

import aiosqlite
import pytest

from src.db import _init_schema
from src.repositories.audit_repo import AuditRepo
from src.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_log_and_list_round_trip(tmp_path):
    path = tmp_path / "t.db"
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await _init_schema(conn)

    repo = AuditRepo(conn)
    svc = AuditService(repo)

    await svc.log(
        actor_internal_id="uuid-actor",
        action="task.create",
        target_table="tasks",
        target_id="rec_xxx",
        payload={"name": "demo task"},
    )

    rows = await svc.list_for_actor("uuid-actor")
    assert len(rows) == 1
    assert rows[0]["action"] == "task.create"
    assert rows[0]["target_id"] == "rec_xxx"

    await conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_audit_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.audit_service'`.

- [ ] **Step 3: Implement**

Create `src/services/__init__.py` (empty):

```python
```

Create `src/services/audit_service.py`:

```python
"""AuditService — append-only audit-trail facade.

Wired but not actively called this phase (Phase 4b services / Phase 7
admin layer light up the call sites). The shape is fixed now so future
callers don't refactor.
"""
from __future__ import annotations

from typing import Any, Optional

from src.repositories.audit_repo import AuditRepo


class AuditService:
    def __init__(self, audit_repo: AuditRepo) -> None:
        self._repo = audit_repo

    async def log(
        self,
        actor_internal_id: Optional[str],
        action: str,
        target_table: Optional[str] = None,
        target_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        """Append an audit-log row. Returns the new row id."""
        return await self._repo.log(
            actor_internal_id=actor_internal_id,
            action=action,
            target_table=target_table,
            target_id=target_id,
            payload=payload,
        )

    async def list_for_actor(
        self, actor_internal_id: str, limit: int = 50,
    ) -> list[dict]:
        return await self._repo.list_for_actor(actor_internal_id, limit)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_audit_service.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/__init__.py src/services/audit_service.py tests/unit/test_audit_service.py
git commit -m "feat(services): add AuditService skeleton (no callers yet)"
```

---

## Task 6 — Qdrant collection naming with embedding-dim suffix

**Files:**
- Modify: `src/infrastructure/qdrant_client.py`
- Modify: `src/context.py`

> The collision risk: when a boss switches embedding model later (e.g. text-embedding-3-small (1536) → text-embedding-3-large (3072)), pushing 3072-dim vectors into a collection configured for 1536 fails. By including `_{dim}` in the collection name, the new model gets a fresh collection; old vectors stay searchable in the old collection until an explicit rebuild action.

- [ ] **Step 1: Update `provision_collections` to take dim**

Open `src/infrastructure/qdrant_client.py`. Find `provision_collections` (around line 63). Replace:

```python
async def provision_collections(boss_chat_id: str):
    """Create messages_{id} and tasks_{id} collections for new boss."""
    await ensure_collection(f"messages_{boss_chat_id}")
    await ensure_collection(f"tasks_{boss_chat_id}")
```

with:

```python
async def provision_collections(boss_chat_id: str, embedding_dim: int = 1536):
    """Create messages_{id}_{dim} and tasks_{id}_{dim} for new boss.

    `embedding_dim` defaults to 1536 (text-embedding-3-small) for legacy
    callers; Phase 4b services pass the boss's actual configured dim.
    """
    await ensure_collection(f"messages_{boss_chat_id}_{embedding_dim}", dim=embedding_dim)
    await ensure_collection(f"tasks_{boss_chat_id}_{embedding_dim}",    dim=embedding_dim)
```

- [ ] **Step 2: Update `ensure_collection` to accept dim**

In the same file, find `ensure_collection` (around line 47). Replace:

```python
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
            collection_name=collection, field_name="chat_id", field_schema="keyword"
        )
```

with:

```python
async def ensure_collection(collection: str, *, dim: int = 1536):
    """Create collection if not exists. Dense (`dim`, cosine) + sparse (BM25 IDF)."""
    existing = [c.name for c in (await _qdrant.get_collections()).collections]
    if collection not in existing:
        await _qdrant.create_collection(
            collection_name=collection,
            vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
            sparse_vectors_config={
                "bm25": SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        await _qdrant.create_payload_index(
            collection_name=collection, field_name="chat_id", field_schema="keyword"
        )
```

- [ ] **Step 3: Update `ChatContext` collection names in `src/context.py`**

Open `src/context.py`. Find `_build_ctx` (around line 111). Replace the `messages_collection` / `tasks_collection` lines:

```python
        messages_collection=f"messages_{bid}",
        tasks_collection=f"tasks_{bid}",
```

with:

```python
        messages_collection=f"messages_{bid}_{boss.get('embedding_dim') or 1536}",
        tasks_collection=f"tasks_{bid}_{boss.get('embedding_dim') or 1536}",
```

(Inline `or 1536` matches the default in `provision_collections`. Phase 4b will replace this with `LLMClient.embedding_dim` from the container.)

- [ ] **Step 4: Boot-check + smoke probe**

```bash
uv run python -c "import src.main; print('OK')"
```

Expected: `OK`.

```bash
uv run python <<'PY'
import asyncio
from src import db
async def main():
    await db.get_db()
    bosses = await db.get_all_bosses()
    if bosses:
        # Default embedding_dim is NULL → falls back to 1536
        b = bosses[0]
        print(f"embedding_dim from row: {b.get('embedding_dim')}  →  collection: messages_{b['chat_id']}_{b.get('embedding_dim') or 1536}")
asyncio.run(main())
PY
```

Expected: prints `embedding_dim from row: None  →  collection: messages_<UUID>_1536`.

- [ ] **Step 5: Commit**

```bash
git add src/infrastructure/qdrant_client.py src/context.py
git commit -m "feat(qdrant): collection name includes embedding_dim suffix"
```

---

## Task 7 — Migration script to rename existing Qdrant collections

**Files:**
- Create: `scripts/migrate_qdrant_collection_names.py`

- [ ] **Step 1: Write the script**

Qdrant has no rename API. The pattern: detect old `messages_{uuid}` (no dim suffix), create new `messages_{uuid}_{dim}` with the same vector config, scroll all points across, delete the old collection.

For self-hosted single-tenant case: the existing collection is fresh (Phase 2 re-provisioned, only a few points). Copy is fast.

Create `scripts/migrate_qdrant_collection_names.py`:

```python
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
```

- [ ] **Step 2: Compile-check**

```bash
uv run python -m py_compile scripts/migrate_qdrant_collection_names.py && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_qdrant_collection_names.py
git commit -m "feat(scripts): add Qdrant collection rename migration"
```

---

## Task 8 — Run Qdrant migration on prod + smoke test

**Files:** None.

- [ ] **Step 1: List current Qdrant collections**

```bash
curl -s http://localhost:6333/collections | python3 -m json.tool
```

Expected: a list including `messages_<UUID>` and `tasks_<UUID>` (old format from Phase 2 work), plus `error_library`.

- [ ] **Step 2: Run the migration**

```bash
uv run python scripts/migrate_qdrant_collection_names.py --dim 1536
```

Expected output:

```
Found 2 old-format collections: ['messages_<UUID>', 'tasks_<UUID>']
  copy messages_<UUID> → messages_<UUID>_1536 ...
    N points copied
    messages_<UUID> deleted
  copy tasks_<UUID> → tasks_<UUID>_1536 ...
    M points copied
    tasks_<UUID> deleted
Done.
```

- [ ] **Step 3: Verify new names**

```bash
curl -s http://localhost:6333/collections | python3 -m json.tool
```

Expected: `messages_<UUID>_1536` and `tasks_<UUID>_1536` exist; the old non-suffixed names are gone.

- [ ] **Step 4: Re-run idempotency**

```bash
uv run python scripts/migrate_qdrant_collection_names.py --dim 1536
```

Expected: `No collections in old format. Already migrated.`

- [ ] **Step 5: Boot bot and DM "hello"**

```bash
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Expected logs: `Application startup complete`, `Polling started`. Then DM the bot `hello`. Expected:
- Server log shows `Received: hello`.
- Qdrant `PUT /collections/messages_<UUID>_1536/points` returns 200.
- Qdrant `POST /collections/messages_<UUID>_1536/points/query` returns 200.
- Bot replies via `editMessageText`.
- No `404 Not Found` from Qdrant.

- [ ] **Step 6: Stop the bot**

`Ctrl-C`.

- [ ] **Step 7: Final state check**

```bash
git log --oneline | head -10
git status
```

Expected: ~7 commits; clean tree.

---

## Done Criteria

- [ ] `src/infrastructure/llm/` exists with `base.py` (Protocol), `openai.py` (impl), `factory.py`.
- [ ] `src/services/` exists with `audit_service.py`.
- [ ] `Settings.openai_embedding_dim` is set; `bosses.embedding_dim` flows into Qdrant collection naming via `ChatContext`.
- [ ] Qdrant collections renamed to `*_{dim}` format; old format removed.
- [ ] `pytest tests/unit/test_llm_factory.py tests/unit/test_audit_service.py -v` is fully green.
- [ ] `python -c "import src.main"` succeeds.
- [ ] Manual smoke (Task 8 step 5): DM "hello" → 200 OK on Qdrant `_1536` collection → bot replies.
- [ ] Existing callers of `infrastructure.openai_client` are unchanged. Phase 4b will migrate them through `LLMClient`.

When all checked, Phase 4a is done. Next: come back to writing-plans skill to draft Phase 4b (services migration + handler classes + dispatcher + agent classes).
