# Web Test Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai một channel mới `web` dưới `src/channels/web/` cho phép giả lập nhiều user/group trong trình duyệt (`/test`), gửi/nhận message qua SSE, persist DB thật, agent loop + LLM chạy real — để self-test cross-group memory mà không cần Zalo.

**Architecture:** Drop-folder channel implement `ChannelAdapter` protocol, đăng ký qua `ChannelRegistry` đã có. 3 bảng sim mới (`web_users`, `web_groups`, `web_group_members`). FastAPI router `/test/*` (HTML + JSON API + SSE). Outbound đẩy qua in-memory `SSEHub` tới các browser tab đang subscribe. Core (agent loop, OutboundService, repositories) **không đụng**.

**Tech Stack:** FastAPI + Jinja2 (sẵn có), asyncpg, Alembic, Server-Sent Events qua `StreamingResponse` (không thêm dependency), vanilla JS + Tailwind CDN (sẵn có), pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-06-01-web-test-channel-design.md`.

---

## File Structure

**Create:**
- `migrations/versions/0002_web_test_channel.py` — Alembic migration: 3 sim tables + seed web bot_account
- `src/channels/web/__init__.py` — `setup(ctx)` entrypoint, đăng ký adapter + subscribers
- `src/channels/web/state_repo.py` — `WebUsersRepo`, `WebGroupsRepo` CRUD
- `src/channels/web/promotion.py` — `BossPromotionService` (atomic upgrade web_user thành boss)
- `src/channels/web/sse.py` — `SSEHub`, `SSEClient` (in-memory pub-sub)
- `src/channels/web/adapter.py` — `WebAdapter` (implements `ChannelAdapter`)
- `src/channels/web/normalizer.py` — `inbound.raw.web` → `messages` row → `message.captured`
- `src/channels/web/fanout.py` — broadcasts inbound message tới các tab khác qua SSEHub
- `src/channels/web/routes.py` — FastAPI router `/test/*`
- `src/channels/web/templates/index.html` — UI shell
- `src/channels/web/static/test.js` — frontend state + EventSource
- `src/channels/web/static/test.css` — minor overrides
- `tests/integration/test_web_state_repo.py`
- `tests/integration/test_web_promotion.py`
- `tests/integration/test_web_sse.py`
- `tests/integration/test_web_adapter.py`
- `tests/integration/test_web_normalizer.py`
- `tests/integration/test_web_routes.py`
- `tests/e2e/test_web_cross_group_memory.py`

**Modify:**
- `src/config.py` — add `ENABLE_WEB_TEST_CHANNEL: bool = True`
- `src/main.py` — mount router (gated bởi flag)

---

## Conventions

- `web_users.id` format: `u-` + 8 hex chars (e.g. `u-a1b2c3d4`). Tạo bằng `f"u-{uuid.uuid4().hex[:8]}"`.
- `web_groups.id` format: `g-` + 8 hex chars (`g-a1b2c3d4`).
- `chat_id` trong `messages`/`outbound_messages`:
  - DM với bot: `"dm:<web_user_id>"` (vd `"dm:u-a1b2c3d4"`)
  - Group: `"<web_group_id>"` (vd `"g-a1b2c3d4"`)
- Web bot_account: `provider_user_id='web-bot-1'`, `display_name='Web Test Bot'`, `ownership='platform'`, `status='active'`.
- Boss web email pattern: `"<web_user_id>@web.test.local"`.

---

## Task 1: Alembic migration — 3 sim tables + web bot_account seed

**Files:**
- Create: `migrations/versions/0002_web_test_channel.py`

- [ ] **Step 1: Tạo migration file**

```python
"""web test channel sim tables + bot_account seed

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-01
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE web_users (
      id            TEXT PRIMARY KEY,
      name          TEXT NOT NULL,
      is_boss       BOOLEAN NOT NULL DEFAULT FALSE,
      boss_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX idx_web_users_boss ON web_users(boss_user_id)")

    op.execute("""
    CREATE TABLE web_groups (
      id          TEXT PRIMARY KEY,
      name        TEXT NOT NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)

    op.execute("""
    CREATE TABLE web_group_members (
      group_id     TEXT NOT NULL REFERENCES web_groups(id) ON DELETE CASCADE,
      web_user_id  TEXT NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
      PRIMARY KEY (group_id, web_user_id)
    )
    """)
    op.execute("CREATE INDEX idx_web_group_members_user ON web_group_members(web_user_id)")

    op.execute("""
    INSERT INTO bot_accounts (provider, provider_user_id, display_name,
                              account_kind, ownership, status)
    VALUES ('web', 'web-bot-1', 'Web Test Bot', 'personal', 'platform', 'active')
    ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.execute("DELETE FROM bot_accounts WHERE provider='web'")
    op.execute("DROP TABLE IF EXISTS web_group_members")
    op.execute("DROP TABLE IF EXISTS web_groups")
    op.execute("DROP TABLE IF EXISTS web_users")
```

- [ ] **Step 2: Chạy migration**

Run: `uv run alembic upgrade head`
Expected: `Running upgrade 0001 -> 0002, web test channel sim tables + bot_account seed`

- [ ] **Step 3: Verify tables tạo + bot_account seed**

Run:
```bash
psql "$POSTGRES_DSN" -c "\d web_users"
psql "$POSTGRES_DSN" -c "\d web_groups"
psql "$POSTGRES_DSN" -c "\d web_group_members"
psql "$POSTGRES_DSN" -c "SELECT provider, display_name FROM bot_accounts WHERE provider='web'"
```
Expected: 3 bảng có schema đúng + 1 row `('web', 'Web Test Bot')`.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0002_web_test_channel.py
git commit -m "feat(web-channel): alembic migration — sim tables + bot_account seed"
```

---

## Task 2: Config flag

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Thêm flag vào Settings**

Edit `src/config.py`, thêm field sau `LOG_RAW_CONTENT`:
```python
ENABLE_WEB_TEST_CHANNEL: bool = True
```

- [ ] **Step 2: Verify**

Run: `python -c "from src.config import settings; print(settings.ENABLE_WEB_TEST_CHANNEL)"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat(web-channel): add ENABLE_WEB_TEST_CHANNEL flag"
```

---

## Task 3: WebUsersRepo + WebGroupsRepo

**Files:**
- Create: `src/channels/web/state_repo.py`
- Create: `tests/integration/test_web_state_repo.py`

- [ ] **Step 1: Viết test cho WebUsersRepo CRUD**

`tests/integration/test_web_state_repo.py`:
```python
import pytest

from src.channels.web.state_repo import WebUsersRepo, WebGroupsRepo


@pytest.mark.asyncio
async def test_web_users_crud(clean_db):
    repo = WebUsersRepo(clean_db)
    uid = await repo.create(name="User X", is_boss=False)
    assert uid.startswith("u-") and len(uid) == 10

    listed = await repo.list_all()
    assert any(u["id"] == uid and u["name"] == "User X" for u in listed)

    await repo.rename(uid, "User Y")
    one = await repo.get(uid)
    assert one["name"] == "User Y"

    await repo.delete(uid)
    assert await repo.get(uid) is None


@pytest.mark.asyncio
async def test_web_groups_crud_and_membership(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)

    u1 = await users.create(name="A", is_boss=False)
    u2 = await users.create(name="B", is_boss=False)
    gid = await groups.create(name="team", member_ids=[u1])

    members = await groups.list_members(gid)
    assert members == [u1]

    await groups.add_member(gid, u2)
    assert set(await groups.list_members(gid)) == {u1, u2}

    await groups.remove_member(gid, u1)
    assert await groups.list_members(gid) == [u2]

    chats = await groups.list_for_user(u2)
    assert any(g["id"] == gid for g in chats)

    await groups.delete(gid)
    assert await groups.list_for_user(u2) == []
```

- [ ] **Step 2: Run test → fail (chưa có module)**

Run: `uv run pytest tests/integration/test_web_state_repo.py -v`
Expected: `ImportError: cannot import name 'WebUsersRepo'`

- [ ] **Step 3: Implement state_repo**

`src/channels/web/state_repo.py`:
```python
"""WebUsersRepo + WebGroupsRepo — CRUD trên 3 bảng sim của channel web.

Không phải BossScopedRepo — web channel là sim layer dùng cross-boss
trong dev/test, không cần RLS theo boss.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class WebUsersRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(
        self, *, name: str, is_boss: bool, boss_user_id: int | None = None
    ) -> str:
        uid = _gen_id("u")
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO web_users (id, name, is_boss, boss_user_id)
                VALUES ($1, $2, $3, $4)
                """,
                uid, name, is_boss, boss_user_id,
            )
        return uid

    async def get(self, web_user_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM web_users WHERE id=$1", web_user_id
            )
        return dict(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM web_users ORDER BY created_at"
            )
        return [dict(r) for r in rows]

    async def rename(self, web_user_id: str, new_name: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE web_users SET name=$2 WHERE id=$1",
                web_user_id, new_name,
            )

    async def set_boss(
        self, web_user_id: str, is_boss: bool, boss_user_id: int | None
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE web_users SET is_boss=$2, boss_user_id=$3 WHERE id=$1
                """,
                web_user_id, is_boss, boss_user_id,
            )

    async def delete(self, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM web_users WHERE id=$1", web_user_id)


class WebGroupsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(self, *, name: str, member_ids: list[str]) -> str:
        gid = _gen_id("g")
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "INSERT INTO web_groups (id, name) VALUES ($1, $2)",
                    gid, name,
                )
                if member_ids:
                    await c.executemany(
                        "INSERT INTO web_group_members (group_id, web_user_id) VALUES ($1, $2)",
                        [(gid, u) for u in member_ids],
                    )
        return gid

    async def get(self, group_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM web_groups WHERE id=$1", group_id
            )
        return dict(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM web_groups ORDER BY created_at"
            )
        return [dict(r) for r in rows]

    async def list_members(self, group_id: str) -> list[str]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT web_user_id FROM web_group_members
                WHERE group_id=$1 ORDER BY web_user_id
                """,
                group_id,
            )
        return [r["web_user_id"] for r in rows]

    async def list_for_user(self, web_user_id: str) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT g.* FROM web_groups g
                JOIN web_group_members m ON m.group_id = g.id
                WHERE m.web_user_id = $1
                ORDER BY g.created_at
                """,
                web_user_id,
            )
        return [dict(r) for r in rows]

    async def add_member(self, group_id: str, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO web_group_members (group_id, web_user_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """,
                group_id, web_user_id,
            )

    async def remove_member(self, group_id: str, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                DELETE FROM web_group_members
                WHERE group_id=$1 AND web_user_id=$2
                """,
                group_id, web_user_id,
            )

    async def delete(self, group_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM web_groups WHERE id=$1", group_id)
```

- [ ] **Step 4: Run test → pass**

Run: `uv run pytest tests/integration/test_web_state_repo.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/state_repo.py tests/integration/test_web_state_repo.py
git commit -m "feat(web-channel): WebUsersRepo + WebGroupsRepo CRUD"
```

---

## Task 4: BossPromotionService

**Files:**
- Create: `src/channels/web/promotion.py`
- Create: `tests/integration/test_web_promotion.py`

- [ ] **Step 1: Viết test cho promote + demote**

`tests/integration/test_web_promotion.py`:
```python
import pytest

from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebUsersRepo


@pytest.mark.asyncio
async def test_promote_creates_boss_link_and_assignment(clean_db):
    users = WebUsersRepo(clean_db)
    svc = BossPromotionService(clean_db)

    web_uid = await users.create(name="Boss X", is_boss=False)
    boss_id = await svc.promote(web_uid)

    assert isinstance(boss_id, int) and boss_id > 0
    async with clean_db.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='web' AND provider_user_id=$1",
            web_uid,
        )
        asg = await c.fetchrow(
            "SELECT * FROM bot_account_assignments WHERE boss_id=$1 AND provider='web'",
            boss_id,
        )
        wu = await c.fetchrow(
            "SELECT is_boss, boss_user_id FROM web_users WHERE id=$1", web_uid
        )
    assert link is not None and link["boss_id"] == boss_id
    assert asg is not None and asg["status"] == "active"
    assert wu["is_boss"] is True and wu["boss_user_id"] == boss_id


@pytest.mark.asyncio
async def test_demote_clears_link_and_assignment(clean_db):
    users = WebUsersRepo(clean_db)
    svc = BossPromotionService(clean_db)
    web_uid = await users.create(name="Boss Y", is_boss=False)
    await svc.promote(web_uid)

    await svc.demote(web_uid)
    async with clean_db.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='web' AND provider_user_id=$1",
            web_uid,
        )
        wu = await c.fetchrow(
            "SELECT is_boss FROM web_users WHERE id=$1", web_uid
        )
    assert link is None
    assert wu["is_boss"] is False
```

- [ ] **Step 2: Run test → fail**

Run: `uv run pytest tests/integration/test_web_promotion.py -v`
Expected: `ImportError`

- [ ] **Step 3: Implement promotion service**

`src/channels/web/promotion.py`:
```python
"""BossPromotionService — atomic upgrade web_user → real boss.

Promote:
  1. INSERT users (role='boss', email='<web_uid>@web.test.local')
  2. INSERT account_links (provider='web', provider_user_id=<web_uid>)
  3. INSERT bot_account_assignments (boss_id, provider='web', bot_account=<web bot>)
  4. UPDATE web_users SET is_boss=true, boss_user_id=<users.id>

Demote: reverse (delete account_links + assignment, set is_boss=false).
"""

from __future__ import annotations

import asyncpg


class BossPromotionService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def promote(self, web_user_id: str) -> int:
        async with self.pool.acquire() as c:
            async with c.transaction():
                wu = await c.fetchrow(
                    "SELECT name FROM web_users WHERE id=$1", web_user_id
                )
                if wu is None:
                    raise ValueError(f"web_user not found: {web_user_id}")

                boss_id = await c.fetchval(
                    """
                    INSERT INTO users (email, name, role)
                    VALUES ($1, $2, 'boss')
                    ON CONFLICT (email) DO UPDATE SET name=EXCLUDED.name
                    RETURNING id
                    """,
                    f"{web_user_id}@web.test.local",
                    wu["name"],
                )

                await c.execute(
                    """
                    INSERT INTO account_links (boss_id, provider, provider_user_id)
                    VALUES ($1, 'web', $2)
                    ON CONFLICT DO NOTHING
                    """,
                    boss_id, web_user_id,
                )

                bot_acc_id = await c.fetchval(
                    """
                    SELECT id FROM bot_accounts
                    WHERE provider='web' AND status='active' LIMIT 1
                    """
                )
                if bot_acc_id is None:
                    raise RuntimeError("no active web bot_account — migration not run?")

                await c.execute(
                    """
                    INSERT INTO bot_account_assignments
                      (boss_id, provider, bot_account_id, assignment_kind, status)
                    VALUES ($1, 'web', $2, 'platform_assigned', 'active')
                    ON CONFLICT (boss_id, provider) DO UPDATE
                      SET bot_account_id=EXCLUDED.bot_account_id,
                          status='active'
                    """,
                    boss_id, bot_acc_id,
                )

                await c.execute(
                    """
                    UPDATE web_users SET is_boss=TRUE, boss_user_id=$2 WHERE id=$1
                    """,
                    web_user_id, boss_id,
                )
        return boss_id

    async def demote(self, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow(
                    "SELECT boss_user_id FROM web_users WHERE id=$1", web_user_id
                )
                boss_id = row["boss_user_id"] if row else None

                await c.execute(
                    """
                    DELETE FROM account_links
                    WHERE provider='web' AND provider_user_id=$1
                    """,
                    web_user_id,
                )
                if boss_id is not None:
                    await c.execute(
                        """
                        DELETE FROM bot_account_assignments
                        WHERE boss_id=$1 AND provider='web'
                        """,
                        boss_id,
                    )
                await c.execute(
                    "UPDATE web_users SET is_boss=FALSE WHERE id=$1",
                    web_user_id,
                )
```

- [ ] **Step 4: Run test → pass**

Run: `uv run pytest tests/integration/test_web_promotion.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/promotion.py tests/integration/test_web_promotion.py
git commit -m "feat(web-channel): BossPromotionService — atomic promote/demote"
```

---

## Task 5: SSEHub (in-memory pub-sub)

**Files:**
- Create: `src/channels/web/sse.py`
- Create: `tests/integration/test_web_sse.py`

- [ ] **Step 1: Viết test**

`tests/integration/test_web_sse.py`:
```python
import asyncio

import pytest

from src.channels.web.sse import SSEHub


@pytest.mark.asyncio
async def test_publish_to_attached_client_receives_event():
    hub = SSEHub()
    client = hub.attach("u-001")
    await hub.publish("u-001", {"kind": "msg", "text": "hi"})
    ev = await asyncio.wait_for(client.queue.get(), timeout=0.5)
    assert ev["text"] == "hi"


@pytest.mark.asyncio
async def test_publish_to_no_clients_is_noop():
    hub = SSEHub()
    await hub.publish("u-nobody", {"kind": "msg"})  # must not raise


@pytest.mark.asyncio
async def test_broadcast_publishes_to_all_recipients():
    hub = SSEHub()
    c1 = hub.attach("u-1")
    c2 = hub.attach("u-2")
    await hub.broadcast(["u-1", "u-2"], {"kind": "msg", "text": "hi"})
    assert (await asyncio.wait_for(c1.queue.get(), 0.5))["text"] == "hi"
    assert (await asyncio.wait_for(c2.queue.get(), 0.5))["text"] == "hi"


@pytest.mark.asyncio
async def test_detach_stops_delivery():
    hub = SSEHub()
    client = hub.attach("u-1")
    hub.detach(client)
    await hub.publish("u-1", {"kind": "msg"})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.queue.get(), 0.1)
```

- [ ] **Step 2: Run test → fail**

Run: `uv run pytest tests/integration/test_web_sse.py -v`
Expected: `ImportError`

- [ ] **Step 3: Implement SSEHub**

`src/channels/web/sse.py`:
```python
"""SSEHub — in-memory pub-sub cho web channel.

Mỗi browser tab attach() → nhận `SSEClient` có `queue` asyncio. Route
``/test/stream`` consume queue → flush ra `text/event-stream`.
Adapter / fanout subscriber publish() vào để push event đến các tab.

Queue có maxsize=100 — overflow → drop event (tab chậm, không block sender).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

QUEUE_MAX = 100


@dataclass
class SSEClient:
    web_user_id: str
    queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_MAX)
    )


class SSEHub:
    def __init__(self) -> None:
        self._clients: dict[str, list[SSEClient]] = defaultdict(list)

    def attach(self, web_user_id: str) -> SSEClient:
        client = SSEClient(web_user_id=web_user_id)
        self._clients[web_user_id].append(client)
        return client

    def detach(self, client: SSEClient) -> None:
        bucket = self._clients.get(client.web_user_id, [])
        if client in bucket:
            bucket.remove(client)

    async def publish(self, web_user_id: str, event: dict) -> None:
        for client in list(self._clients.get(web_user_id, [])):
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning(
                    "SSE queue full for web_user_id=%s; dropping event",
                    web_user_id,
                )

    async def broadcast(self, web_user_ids: list[str], event: dict) -> None:
        for uid in web_user_ids:
            await self.publish(uid, event)
```

- [ ] **Step 4: Run test → pass**

Run: `uv run pytest tests/integration/test_web_sse.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/sse.py tests/integration/test_web_sse.py
git commit -m "feat(web-channel): SSEHub in-memory pub-sub"
```

---

## Task 6: WebAdapter

**Files:**
- Create: `src/channels/web/adapter.py`
- Create: `tests/integration/test_web_adapter.py`

- [ ] **Step 1: Viết test cho send_text broadcast**

`tests/integration/test_web_adapter.py`:
```python
import asyncio
from types import SimpleNamespace

import pytest

from src.channels.web.adapter import WebAdapter
from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo


@pytest.mark.asyncio
async def test_send_text_dm_broadcasts_to_single_recipient(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    u1 = await users.create(name="Boss A", is_boss=True)

    hub = SSEHub()
    client = hub.attach(u1)
    adapter = WebAdapter(bus=None, sse_hub=hub, groups_repo=groups)

    bot_acc = SimpleNamespace(id=1)
    await adapter.send_text(bot_acc, f"dm:{u1}", "hello", "user")
    ev = await asyncio.wait_for(client.queue.get(), timeout=0.5)
    assert ev["kind"] == "message"
    assert ev["text"] == "hello"
    assert ev["sender_kind"] == "bot"
    assert ev["chat_id"] == f"dm:{u1}"


@pytest.mark.asyncio
async def test_send_text_group_broadcasts_to_all_members(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    u1 = await users.create(name="A", is_boss=True)
    u2 = await users.create(name="B", is_boss=False)
    gid = await groups.create(name="team", member_ids=[u1, u2])

    hub = SSEHub()
    c1 = hub.attach(u1)
    c2 = hub.attach(u2)
    adapter = WebAdapter(bus=None, sse_hub=hub, groups_repo=groups)

    bot_acc = SimpleNamespace(id=1)
    await adapter.send_text(bot_acc, gid, "team msg", "group")
    e1 = await asyncio.wait_for(c1.queue.get(), 0.5)
    e2 = await asyncio.wait_for(c2.queue.get(), 0.5)
    assert e1["text"] == "team msg" and e2["text"] == "team msg"


@pytest.mark.asyncio
async def test_classify_thread_kind_and_normalize_text():
    adapter = WebAdapter(bus=None, sse_hub=SSEHub(), groups_repo=None)
    assert adapter.classify_thread_kind("dm:u-abc") == "user"
    assert adapter.classify_thread_kind("g-abc") == "group"
    # Web renders markdown — keep as-is
    assert adapter.normalize_text("**hi**") == "**hi**"
```

- [ ] **Step 2: Run test → fail**

Run: `uv run pytest tests/integration/test_web_adapter.py -v`
Expected: `ImportError`

- [ ] **Step 3: Implement WebAdapter**

`src/channels/web/adapter.py`:
```python
"""WebAdapter — implements ChannelAdapter cho channel web.

start_inbound / stop_inbound: no-op (web không có long-lived subprocess).
send_text: broadcast tới các SSE client của các thành viên chat đích.
list_members: query WebGroupsRepo cho group chat.
health_check: web bot account luôn alive khi app chạy.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo

log = logging.getLogger(__name__)


class WebAdapter:
    provider = "web"

    def __init__(
        self,
        bus: Any,
        sse_hub: SSEHub,
        groups_repo: WebGroupsRepo | None,
    ) -> None:
        self.bus = bus
        self.sse_hub = sse_hub
        self.groups_repo = groups_repo

    async def start_inbound(self, bot_acc) -> None:
        return  # web inbound đến qua HTTP, không cần long-lived process

    async def stop_inbound(self, bot_acc) -> None:
        return

    async def send_text(
        self, bot_acc, chat_id: str, text: str, thread_kind: str
    ) -> str:
        recipients = await self._recipients_of(chat_id)
        event = {
            "kind": "message",
            "chat_id": chat_id,
            "msg_id": f"o-{uuid.uuid4().hex[:8]}",
            "sender_kind": "bot",
            "sender_id": "web-bot-1",
            "sender_name": "Bot",
            "text": text,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        await self.sse_hub.broadcast(recipients, event)
        return event["msg_id"]

    async def list_members(self, bot_acc, group_id: str) -> list[str]:
        if self.groups_repo is None:
            return []
        return await self.groups_repo.list_members(group_id)

    def classify_thread_kind(self, chat_id: str) -> str:
        if chat_id.startswith("dm:"):
            return "user"
        return "group"

    def normalize_text(self, text: str) -> str:
        # Web UI renders markdown — không cần strip.
        return text

    async def health_check(self) -> dict[int, bool]:
        # Web không có subprocess — bot_account luôn "alive" while app up.
        return {}

    async def _recipients_of(self, chat_id: str) -> list[str]:
        if chat_id.startswith("dm:"):
            return [chat_id[3:]]
        if self.groups_repo is None:
            return []
        return await self.groups_repo.list_members(chat_id)
```

- [ ] **Step 4: Run test → pass**

Run: `uv run pytest tests/integration/test_web_adapter.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/adapter.py tests/integration/test_web_adapter.py
git commit -m "feat(web-channel): WebAdapter implements ChannelAdapter"
```

---

## Task 7: Web normalizer

**Files:**
- Create: `src/channels/web/normalizer.py`
- Create: `tests/integration/test_web_normalizer.py`

- [ ] **Step 1: Viết test**

`tests/integration/test_web_normalizer.py`:
```python
import asyncio

import pytest

from src.channels.web import normalizer as web_normalizer
from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo
from src.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_normalizer_dm_inserts_message_and_publishes_captured(clean_db):
    users = WebUsersRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)

    bus = InMemoryEventBus()
    web_normalizer.register(bus, clean_db)

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": boss_uid,
            "chat_id": f"dm:{boss_uid}",
            "chat_type": "dm",
            "text": "hi bot",
            "mention_bot": False,
            "provider_msg_id": "msg-1",
            "sender_name": "Boss",
        },
    )
    await asyncio.sleep(0)

    assert len(captured) == 1
    ev = captured[0]
    assert ev["provider"] == "web"
    assert ev["boss_id"] == boss_id
    assert ev["chat_type"] == "dm"
    assert ev["sender_is_boss"] is True
    assert ev["text"] == "hi bot"


@pytest.mark.asyncio
async def test_normalizer_group_resolves_boss_via_member(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)
    u2 = await users.create(name="UserX", is_boss=False)
    gid = await groups.create(name="team", member_ids=[boss_uid, u2])

    bus = InMemoryEventBus()
    web_normalizer.register(bus, clean_db)

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": u2,
            "chat_id": gid,
            "chat_type": "group",
            "text": "fyi",
            "mention_bot": True,
            "provider_msg_id": "g-msg-1",
            "sender_name": "UserX",
        },
    )
    await asyncio.sleep(0)

    assert len(captured) == 1
    assert captured[0]["chat_type"] == "group"
    assert captured[0]["boss_id"] == boss_id
    assert captured[0]["mentions_bot"] is True
    assert captured[0]["sender_is_boss"] is False
```

- [ ] **Step 2: Run test → fail**

Run: `uv run pytest tests/integration/test_web_normalizer.py -v`
Expected: ImportError or assertion fail

- [ ] **Step 3: Implement normalizer**

`src/channels/web/normalizer.py`:
```python
"""inbound.raw.web → MessagesRepo.insert → publish message.captured.

Schema payload (do routes.py publish):
  {
    web_user_id: str,        # sender
    chat_id: str,            # "dm:<uid>" or "<group_id>"
    chat_type: 'dm'|'group',
    text: str,
    mention_bot: bool,
    provider_msg_id: str,
    sender_name: str,
  }

Boss resolution:
  - DM: account_links lookup theo provider='web', provider_user_id=sender
  - Group: any boss đang là member của group (via web_users.is_boss=true
    JOIN web_group_members). MVP: lấy boss đầu tiên gặp.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.domain.message import NewMessage
from src.events.bus import EventBus
from src.repositories.base import BossContext
from src.repositories.messages import MessagesRepo

log = logging.getLogger(__name__)


def register(bus: EventBus, pool) -> None:
    async def handle(payload: dict) -> None:
        sender_uid = payload["web_user_id"]
        chat_id = payload["chat_id"]
        chat_type = payload["chat_type"]
        text = payload.get("text") or ""
        provider_msg_id = payload.get("provider_msg_id")
        sender_name = payload.get("sender_name")
        mention_bot = bool(payload.get("mention_bot"))

        boss_id: int | None = None
        sender_is_boss = False
        async with pool.acquire() as c:
            if chat_type == "dm":
                row = await c.fetchrow(
                    """
                    SELECT boss_id FROM account_links
                    WHERE provider='web' AND provider_user_id=$1
                    """,
                    sender_uid,
                )
                if row:
                    boss_id = row["boss_id"]
                    sender_is_boss = True
            else:
                row = await c.fetchrow(
                    """
                    SELECT wu.boss_user_id
                    FROM web_group_members m
                    JOIN web_users wu ON wu.id = m.web_user_id
                    WHERE m.group_id=$1
                      AND wu.is_boss=TRUE
                      AND wu.boss_user_id IS NOT NULL
                    LIMIT 1
                    """,
                    chat_id,
                )
                if row:
                    boss_id = row["boss_user_id"]
                # Check if sender themselves is the resolved boss
                if boss_id is not None:
                    own = await c.fetchrow(
                        """
                        SELECT boss_user_id FROM web_users
                        WHERE id=$1 AND is_boss=TRUE
                        """,
                        sender_uid,
                    )
                    if own and own["boss_user_id"] == boss_id:
                        sender_is_boss = True

        if boss_id is None:
            log.info(
                "web inbound dropped — no boss resolved (chat_id=%s sender=%s)",
                chat_id, sender_uid,
            )
            return

        repo = MessagesRepo(pool, BossContext(boss_id=boss_id, user_role="boss"))
        msg = NewMessage(
            provider="web",
            chat_id=chat_id,
            chat_type=chat_type,
            provider_msg_id=provider_msg_id,
            sender_provider_id=sender_uid,
            sender_name=sender_name,
            text=text or None,
            media_kind="text",
            media_url=None,
            media_text=None,
            ts=datetime.now(tz=timezone.utc),
        )
        msg_id = await repo.insert(msg)
        if msg_id is None:
            return  # dedup

        await bus.publish(
            "message.captured",
            {
                "message_id": msg_id,
                "boss_id": boss_id,
                "provider": "web",
                "chat_id": chat_id,
                "chat_type": chat_type,
                "mentions_bot": mention_bot,
                "sender_is_boss": sender_is_boss,
                "text": text,
                "bot_account_id": None,
            },
        )

    bus.subscribe("inbound.raw.web", handle)
```

- [ ] **Step 4: Run test → pass**

Run: `uv run pytest tests/integration/test_web_normalizer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/normalizer.py tests/integration/test_web_normalizer.py
git commit -m "feat(web-channel): inbound normalizer — DB insert + message.captured"
```

---

## Task 8: Inbound fanout (broadcast user messages tới tab khác)

**Files:**
- Create: `src/channels/web/fanout.py`

- [ ] **Step 1: Implement fanout subscriber**

`src/channels/web/fanout.py`:
```python
"""Inbound fanout — khi user X gửi message trong group g-001, các tab
khác (user Y, Z) phải thấy realtime. Subscribe vào ``message.captured``
provider='web' và broadcast event "message" qua SSEHub tới các member.

Sender's own tab cũng nhận event (đơn giản hơn dedup); frontend hiển
thị uniform — không có "optimistic update" mismatch.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo
from src.events.bus import EventBus


def register(
    bus: EventBus, sse_hub: SSEHub, groups_repo: WebGroupsRepo, pool
) -> None:
    async def handle(payload: dict) -> None:
        if payload.get("provider") != "web":
            return
        chat_id = payload["chat_id"]
        if chat_id.startswith("dm:"):
            recipients = [chat_id[3:]]
        else:
            recipients = await groups_repo.list_members(chat_id)

        # Pull sender info từ DB (normalizer đã insert)
        async with pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT m.sender_provider_id, m.sender_name, m.text, m.ts
                FROM messages m WHERE m.id=$1
                """,
                payload["message_id"],
            )
        if row is None:
            return

        event = {
            "kind": "message",
            "chat_id": chat_id,
            "msg_id": str(payload["message_id"]),
            "sender_kind": "user",
            "sender_id": row["sender_provider_id"],
            "sender_name": row["sender_name"],
            "text": row["text"] or "",
            "ts": (row["ts"] or datetime.now(tz=timezone.utc)).isoformat(),
        }
        await sse_hub.broadcast(recipients, event)

    bus.subscribe("message.captured", handle)
```

- [ ] **Step 2: Commit (test included trong Task 11 e2e)**

```bash
git add src/channels/web/fanout.py
git commit -m "feat(web-channel): SSE fanout — broadcast inbound to peers"
```

---

## Task 9: __init__.py setup() entrypoint

**Files:**
- Create: `src/channels/web/__init__.py`

- [ ] **Step 1: Implement setup()**

`src/channels/web/__init__.py`:
```python
"""Web test channel — drop-folder entrypoint.

setup(ctx) được gọi bởi ChannelRegistry.discover_and_load. Trả về
adapter để registry lưu; route mount tách riêng ở main.py (cần access
sse_hub + repos qua app.state).
"""

from __future__ import annotations

from src.channels.registry import ChannelSetupContext
from src.channels.web import fanout, normalizer
from src.channels.web.adapter import WebAdapter
from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo


def setup(ctx: ChannelSetupContext) -> WebAdapter:
    sse_hub = SSEHub()
    groups_repo = WebGroupsRepo(ctx.pool)
    users_repo = WebUsersRepo(ctx.pool)

    adapter = WebAdapter(bus=ctx.bus, sse_hub=sse_hub, groups_repo=groups_repo)

    normalizer.register(ctx.bus, ctx.pool)
    fanout.register(ctx.bus, sse_hub, groups_repo, ctx.pool)

    # Expose handles cho routes.py (mounted ở main.py) qua attributes
    # trên adapter — registry chỉ giữ adapter instance.
    adapter.sse_hub = sse_hub
    adapter.users_repo = users_repo
    adapter.groups_repo = groups_repo
    adapter.outbound_service = ctx.outbound_service
    adapter.pool = ctx.pool
    return adapter
```

- [ ] **Step 2: Smoke test — discover_and_load picks up web**

Run:
```python
uv run python -c "
import asyncio
from src.channels.registry import ChannelRegistry, ChannelSetupContext, discover_and_load
from src.events.bus import InMemoryEventBus
from src.infra.db import create_pool
from src.repositories.bot_accounts import BotAccountsRepo
from src.repositories.base import BossContext

async def main():
    pool = await create_pool()
    bus = InMemoryEventBus()
    admin_repo = BotAccountsRepo(pool, BossContext(0, 'superadmin'))
    reg = ChannelRegistry()
    ctx = ChannelSetupContext(bus=bus, pool=pool, admin_repo=admin_repo)
    loaded = await discover_and_load(reg, ctx)
    print('loaded:', loaded)
    print('web adapter:', reg.get('web'))
    await pool.close()

asyncio.run(main())
"
```
Expected: `loaded: ['web', 'zalo']` (or similar order), `web adapter: <WebAdapter...>`

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/__init__.py
git commit -m "feat(web-channel): setup() entrypoint for ChannelRegistry"
```

---

## Task 10: FastAPI routes — user/group CRUD

**Files:**
- Create: `src/channels/web/routes.py`
- Create: `tests/integration/test_web_routes.py`

- [ ] **Step 1: Viết test cho user/group endpoints**

`tests/integration/test_web_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(clean_db):
    return TestClient(app)


def test_create_and_list_users(client, clean_db):
    r = client.post(
        "/test/api/users",
        json={"name": "Boss A", "is_boss": True},
    )
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert uid.startswith("u-")

    r2 = client.get("/test/api/users")
    assert any(u["id"] == uid for u in r2.json())


def test_create_group_with_members(client, clean_db):
    u1 = client.post("/test/api/users", json={"name": "A", "is_boss": True}).json()["id"]
    u2 = client.post("/test/api/users", json={"name": "B", "is_boss": False}).json()["id"]
    r = client.post(
        "/test/api/groups",
        json={"name": "team", "member_ids": [u1, u2]},
    )
    assert r.status_code == 200
    gid = r.json()["id"]
    members = client.get(f"/test/api/groups").json()
    assert any(g["id"] == gid for g in members)


def test_delete_user_cascade(client, clean_db):
    u1 = client.post("/test/api/users", json={"name": "A", "is_boss": False}).json()["id"]
    gid = client.post(
        "/test/api/groups", json={"name": "g", "member_ids": [u1]}
    ).json()["id"]
    r = client.delete(f"/test/api/users/{u1}")
    assert r.status_code == 204
    # Group still exists but membership cleared
    members = client.get(f"/test/api/chats?as={u1}").json()
    assert members == []
```

- [ ] **Step 2: Run test → fail (route chưa mount)**

Run: `uv run pytest tests/integration/test_web_routes.py -v -k "users or group"`
Expected: 404 Not Found

- [ ] **Step 3: Implement routes (user + group CRUD only ở task này)**

`src/channels/web/routes.py`:
```python
"""FastAPI router cho /test/* — UI + JSON API + SSE.

Mount ở main.py qua include_router. Lookup adapter/repos qua
``request.app.state.channel_registry.get('web')`` để tránh circular dep.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.channels.web.promotion import BossPromotionService

router = APIRouter(prefix="/test")
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _adapter(request: Request):
    reg = getattr(request.app.state, "channel_registry", None)
    if reg is None:
        raise HTTPException(503, "channel registry not ready")
    adapter = reg.get("web")
    if adapter is None:
        raise HTTPException(404, "web channel not enabled")
    return adapter


class CreateUserBody(BaseModel):
    name: str
    is_boss: bool = False


class CreateGroupBody(BaseModel):
    name: str
    member_ids: list[str] = []


class MembershipBody(BaseModel):
    add: list[str] = []
    remove: list[str] = []


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _templates.TemplateResponse(
        "index.html", {"request": request}
    )


@router.get("/api/users")
async def list_users(request: Request):
    a = _adapter(request)
    return await a.users_repo.list_all()


@router.post("/api/users")
async def create_user(request: Request, body: CreateUserBody):
    a = _adapter(request)
    uid = await a.users_repo.create(name=body.name, is_boss=False)
    if body.is_boss:
        await BossPromotionService(a.pool).promote(uid)
    return {"id": uid}


@router.patch("/api/users/{uid}")
async def update_user(request: Request, uid: str, body: CreateUserBody):
    a = _adapter(request)
    await a.users_repo.rename(uid, body.name)
    existing = await a.users_repo.get(uid)
    if existing is None:
        raise HTTPException(404, "user not found")
    if body.is_boss and not existing["is_boss"]:
        await BossPromotionService(a.pool).promote(uid)
    elif not body.is_boss and existing["is_boss"]:
        await BossPromotionService(a.pool).demote(uid)
    return {"ok": True}


@router.delete("/api/users/{uid}", status_code=204)
async def delete_user(request: Request, uid: str):
    a = _adapter(request)
    existing = await a.users_repo.get(uid)
    if existing and existing["is_boss"]:
        await BossPromotionService(a.pool).demote(uid)
    await a.users_repo.delete(uid)


@router.get("/api/groups")
async def list_groups(request: Request):
    a = _adapter(request)
    return await a.groups_repo.list_all()


@router.post("/api/groups")
async def create_group(request: Request, body: CreateGroupBody):
    a = _adapter(request)
    gid = await a.groups_repo.create(name=body.name, member_ids=body.member_ids)
    return {"id": gid}


@router.delete("/api/groups/{gid}", status_code=204)
async def delete_group(request: Request, gid: str):
    a = _adapter(request)
    await a.groups_repo.delete(gid)


@router.post("/api/groups/{gid}/members")
async def edit_members(request: Request, gid: str, body: MembershipBody):
    a = _adapter(request)
    for uid in body.add:
        await a.groups_repo.add_member(gid, uid)
    for uid in body.remove:
        await a.groups_repo.remove_member(gid, uid)
    return {"members": await a.groups_repo.list_members(gid)}


@router.get("/api/chats")
async def list_chats(request: Request, as_: str = "", as_alt: str = ""):
    """Liệt kê chats identity 'as' tham gia: 1 DM với bot + tất cả groups.

    Query param: ?as=<web_user_id>
    """
    a = _adapter(request)
    uid = request.query_params.get("as")
    if not uid:
        return []
    user = await a.users_repo.get(uid)
    if user is None:
        return []
    groups = await a.groups_repo.list_for_user(uid)
    chats = [
        {"chat_id": f"dm:{uid}", "name": f"DM with Bot", "kind": "dm"},
    ]
    chats.extend(
        {"chat_id": g["id"], "name": g["name"], "kind": "group"}
        for g in groups
    )
    return chats
```

- [ ] **Step 4: Mount router tạm thời trong main.py để test**

Edit `src/main.py`, sau `app.include_router(web_admin.router)`, thêm:
```python
from src.channels.web.routes import router as web_test_router
app.include_router(web_test_router)
```

(Sẽ refactor sang flag-gated ở Task 13.)

- [ ] **Step 5: Run test → pass**

Run: `uv run pytest tests/integration/test_web_routes.py -v -k "users or group"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/channels/web/routes.py tests/integration/test_web_routes.py src/main.py
git commit -m "feat(web-channel): routes — user/group CRUD"
```

---

## Task 11: Routes — chat list, messages replay, send

**Files:**
- Modify: `src/channels/web/routes.py`
- Modify: `tests/integration/test_web_routes.py`

- [ ] **Step 1: Test cho send + replay**

Thêm vào `tests/integration/test_web_routes.py`:
```python
def test_send_publishes_inbound_event_and_replay_returns_messages(
    client, clean_db
):
    # Setup: boss + DM
    uid = client.post(
        "/test/api/users", json={"name": "Boss", "is_boss": True}
    ).json()["id"]

    # Send a message as the boss in their DM
    r = client.post(
        "/test/api/send",
        json={
            "as": uid,
            "chat_id": f"dm:{uid}",
            "text": "hello bot",
            "mention_bot": False,
        },
    )
    assert r.status_code == 200

    # Wait a tick for normalizer
    import time
    time.sleep(0.3)

    # Replay
    msgs = client.get(
        f"/test/api/chats/dm:{uid}/messages?limit=50"
    ).json()
    assert any(m["text"] == "hello bot" for m in msgs)
```

- [ ] **Step 2: Run → fail**

Run: `uv run pytest tests/integration/test_web_routes.py::test_send_publishes_inbound_event_and_replay_returns_messages -v`
Expected: 404 (route chưa có)

- [ ] **Step 3: Thêm routes**

Thêm vào cuối `src/channels/web/routes.py`:
```python
class SendBody(BaseModel):
    as_: str = ""
    chat_id: str
    text: str
    mention_bot: bool = False

    class Config:
        fields = {"as_": "as"}  # ignored: pydantic v2 — handle manually
```

Thực tế dùng dict body để hỗ trợ key `"as"` (reserved trong Python):
```python
@router.post("/api/send")
async def send_inbound(request: Request):
    a = _adapter(request)
    body = await request.json()
    as_uid = body.get("as")
    chat_id = body.get("chat_id")
    text = body.get("text") or ""
    mention_bot = bool(body.get("mention_bot"))
    if not as_uid or not chat_id:
        raise HTTPException(400, "as and chat_id required")

    sender = await a.users_repo.get(as_uid)
    if sender is None:
        raise HTTPException(404, "sender not found")

    import uuid as _uuid
    await a.bus.publish(
        "inbound.raw.web",
        {
            "web_user_id": as_uid,
            "chat_id": chat_id,
            "chat_type": "dm" if chat_id.startswith("dm:") else "group",
            "text": text,
            "mention_bot": mention_bot,
            "provider_msg_id": f"w-{_uuid.uuid4().hex[:10]}",
            "sender_name": sender["name"],
        },
    )
    return {"ok": True}


@router.get("/api/chats/{chat_id:path}/messages")
async def replay_messages(request: Request, chat_id: str, limit: int = 50):
    a = _adapter(request)
    async with a.pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT * FROM (
              SELECT
                'in'::text  AS kind,
                m.id        AS id,
                m.chat_id   AS chat_id,
                m.sender_provider_id AS sender_id,
                m.sender_name        AS sender_name,
                m.text      AS text,
                m.ts        AS ts
              FROM messages m
              WHERE m.provider='web' AND m.chat_id=$1
              UNION ALL
              SELECT
                'out'::text AS kind,
                o.id        AS id,
                o.chat_id   AS chat_id,
                NULL        AS sender_id,
                'Bot'       AS sender_name,
                o.content   AS text,
                o.sent_at   AS ts
              FROM outbound_messages o
              WHERE o.provider='web' AND o.chat_id=$1
            ) merged
            ORDER BY ts DESC
            LIMIT $2
            """,
            chat_id, limit,
        )
    rows = list(reversed(rows))  # chronological
    return [
        {
            "kind": r["kind"],
            "id": r["id"],
            "chat_id": r["chat_id"],
            "sender_id": r["sender_id"],
            "sender_name": r["sender_name"],
            "text": r["text"],
            "ts": r["ts"].isoformat(),
        }
        for r in rows
    ]
```

`adapter.bus` cần thêm — set trong setup(): `adapter.bus = ctx.bus` (đã có ở constructor).

- [ ] **Step 4: Run → pass**

Run: `uv run pytest tests/integration/test_web_routes.py -v`
Expected: PASS

Note: nếu test send fail vì agent loop chạy → mention_bot=false thì agent skip; ok.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/routes.py tests/integration/test_web_routes.py
git commit -m "feat(web-channel): routes — send + messages replay"
```

---

## Task 12: SSE stream endpoint

**Files:**
- Modify: `src/channels/web/routes.py`

- [ ] **Step 1: Thêm SSE endpoint**

Thêm vào `routes.py`:
```python
@router.get("/stream")
async def sse_stream(request: Request):
    a = _adapter(request)
    uid = request.query_params.get("as")
    if not uid:
        raise HTTPException(400, "as= required")
    user = await a.users_repo.get(uid)
    if user is None:
        raise HTTPException(404, "user not found")

    client = a.sse_hub.attach(uid)

    async def gen():
        try:
            # Initial comment to flush headers
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        client.queue.get(), timeout=15.0
                    )
                    payload = json.dumps(event)
                    yield f"data: {payload}\n\n".encode()
                except asyncio.TimeoutError:
                    yield b": heartbeat\n\n"
        finally:
            a.sse_hub.detach(client)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 2: Manual smoke test với curl**

Run trong 1 terminal:
```bash
# Terminal A
curl -N http://localhost:8000/test/stream?as=u-<existing-id>
```

Run trong 1 terminal khác:
```bash
# Terminal B — publish a manual event via adapter (using python -c)
uv run python -c "
import asyncio
from src.main import app

async def main():
    # Boot app lifespan to populate channel_registry
    async with app.router.lifespan_context(app):
        adapter = app.state.channel_registry.get('web')
        await adapter.sse_hub.publish('u-<existing-id>', {'kind':'test','text':'hello'})

asyncio.run(main())
"
```

Expected terminal A nhận: `data: {"kind":"test","text":"hello"}`

(Có thể skip manual test này nếu sẽ verify qua frontend ở Task 16.)

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/routes.py
git commit -m "feat(web-channel): SSE /test/stream endpoint with heartbeat"
```

---

## Task 13: Gate router mount với flag + cleanup

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Wrap include_router với flag**

Edit `src/main.py`: 
Tìm dòng đã thêm tạm ở Task 10:
```python
from src.channels.web.routes import router as web_test_router
app.include_router(web_test_router)
```

Thay bằng:
```python
if settings.ENABLE_WEB_TEST_CHANNEL:
    from src.channels.web.routes import router as web_test_router
    app.include_router(web_test_router)
```

- [ ] **Step 2: Verify both states**

Test ON:
```bash
ENABLE_WEB_TEST_CHANNEL=true uv run python -c "
from src.main import app
print('routes:', [r.path for r in app.routes if '/test' in r.path])
"
```
Expected: list chứa `/test/`, `/test/api/users`, `/test/stream`, ...

Test OFF:
```bash
ENABLE_WEB_TEST_CHANNEL=false uv run python -c "
from src.main import app
print('routes:', [r.path for r in app.routes if '/test' in r.path])
"
```
Expected: `routes: []`

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat(web-channel): gate /test mount via ENABLE_WEB_TEST_CHANNEL"
```

---

## Task 14: Frontend HTML shell

**Files:**
- Create: `src/channels/web/templates/index.html`
- Create: `src/channels/web/static/test.css`

- [ ] **Step 1: HTML template**

`src/channels/web/templates/index.html`:
```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SMART_bot — Web Test Channel</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="/test/static/test.css" />
</head>
<body class="bg-gray-50 text-gray-900 antialiased">
  <div id="app" class="flex h-screen">
    <!-- Sidebar -->
    <aside class="w-72 bg-white border-r flex flex-col">
      <div class="p-3 border-b">
        <label class="text-xs uppercase text-gray-500">Sending as</label>
        <select id="as-select" class="w-full mt-1 px-2 py-1 border rounded">
          <option value="">-- chọn user --</option>
        </select>
        <button id="btn-add-user" class="mt-2 w-full text-sm bg-blue-50 text-blue-700 py-1 rounded hover:bg-blue-100">+ Thêm user</button>
      </div>
      <div class="p-3 border-b text-xs uppercase text-gray-500">DMs / Groups</div>
      <ul id="chat-list" class="flex-1 overflow-y-auto"></ul>
      <div class="p-3 border-t">
        <button id="btn-add-group" class="w-full text-sm bg-green-50 text-green-700 py-1 rounded hover:bg-green-100">+ Tạo group</button>
        <button id="btn-admin" class="mt-2 w-full text-sm bg-gray-100 text-gray-700 py-1 rounded">⚙ Admin</button>
      </div>
    </aside>

    <!-- Chat panel -->
    <main class="flex-1 flex flex-col">
      <header id="chat-header" class="px-4 py-3 border-b bg-white">
        <h2 class="font-semibold text-gray-700">— chọn chat —</h2>
      </header>
      <ol id="messages" class="flex-1 overflow-y-auto px-4 py-3 space-y-2"></ol>
      <footer class="p-3 border-t bg-white">
        <div class="flex gap-2 items-center">
          <input id="msg-input" type="text" placeholder="Nhập tin nhắn..."
                 class="flex-1 px-3 py-2 border rounded focus:outline-blue-500" />
          <label class="text-sm text-gray-600">
            <input id="mention-bot" type="checkbox" class="mr-1" />@bot
          </label>
          <button id="btn-send" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">Send</button>
        </div>
      </footer>
    </main>

    <!-- Admin pane (collapsed) -->
    <aside id="admin-pane" class="w-80 bg-white border-l p-3 hidden overflow-y-auto">
      <h3 class="font-semibold">Users</h3>
      <ul id="admin-users" class="text-sm mt-2"></ul>
      <h3 class="font-semibold mt-4">Groups</h3>
      <ul id="admin-groups" class="text-sm mt-2"></ul>
    </aside>
  </div>

  <script src="/test/static/test.js" type="module"></script>
</body>
</html>
```

- [ ] **Step 2: CSS overrides**

`src/channels/web/static/test.css`:
```css
.bubble-self { background: #dbeafe; align-self: flex-end; }
.bubble-other { background: #f1f5f9; }
.bubble-bot { background: #fef3c7; }
.chat-item.active { background: #eff6ff; font-weight: 600; }
```

- [ ] **Step 3: Mount static files**

Cần serve `src/channels/web/static/*` ở path `/test/static/*`. Thêm vào `src/channels/web/routes.py`:
```python
from fastapi.staticfiles import StaticFiles
# ... after router init
_STATIC_DIR = Path(__file__).parent / "static"
```

Mount trong main.py sau include_router:
```python
if settings.ENABLE_WEB_TEST_CHANNEL:
    from src.channels.web.routes import router as web_test_router, _STATIC_DIR as _web_static
    app.include_router(web_test_router)
    app.mount("/test/static", StaticFiles(directory=str(_web_static)), name="web_test_static")
```

- [ ] **Step 4: Smoke test**

Run: `./scripts/restart.sh` (per memory: hybrid runtime)
Mở `http://localhost:8000/test/` — verify HTML render đúng layout (3 cột).

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/templates/ src/channels/web/static/ src/channels/web/routes.py src/main.py
git commit -m "feat(web-channel): HTML shell + Tailwind layout"
```

---

## Task 15: Frontend JS — state, EventSource, send/render

**Files:**
- Create: `src/channels/web/static/test.js`

- [ ] **Step 1: Implement frontend logic**

`src/channels/web/static/test.js`:
```javascript
// State
let state = {
  asUid: "",
  activeChatId: "",
  users: [],
  chats: [],
  messagesByChat: {},  // chatId -> [{kind, sender_id, sender_name, text, ts}]
  eventSource: null,
};

// --- DOM refs ---
const $ = (id) => document.getElementById(id);
const asSelect = $("as-select");
const chatList = $("chat-list");
const messages = $("messages");
const msgInput = $("msg-input");
const mentionBot = $("mention-bot");
const btnSend = $("btn-send");
const btnAddUser = $("btn-add-user");
const btnAddGroup = $("btn-add-group");
const btnAdmin = $("btn-admin");
const adminPane = $("admin-pane");
const chatHeader = $("chat-header").querySelector("h2");

// --- HTTP helpers ---
async function api(path, opts = {}) {
  const r = await fetch(`/test${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.status === 204 ? null : r.json();
}

// --- Render ---
function renderUsers() {
  asSelect.innerHTML = '<option value="">-- chọn user --</option>' +
    state.users.map(u => `<option value="${u.id}" ${u.id === state.asUid ? "selected" : ""}>${u.name}${u.is_boss ? " ★" : ""}</option>`).join("");
}

function renderChats() {
  chatList.innerHTML = state.chats.map(c => `
    <li class="chat-item px-3 py-2 cursor-pointer hover:bg-gray-50 ${c.chat_id === state.activeChatId ? "active" : ""}"
        data-id="${c.chat_id}">
      ${c.kind === "dm" ? "☆" : "#"} ${c.name}
    </li>
  `).join("");
  chatList.querySelectorAll(".chat-item").forEach(li => {
    li.onclick = () => selectChat(li.dataset.id);
  });
}

function renderMessages() {
  const msgs = state.messagesByChat[state.activeChatId] || [];
  messages.innerHTML = msgs.map(m => {
    const klass = m.sender_kind === "bot" ? "bubble-bot"
      : m.sender_id === state.asUid ? "bubble-self" : "bubble-other";
    return `
      <li class="flex flex-col">
        <div class="${klass} max-w-[70%] px-3 py-2 rounded inline-block">
          <div class="text-xs text-gray-500">${m.sender_name || "?"}</div>
          <div>${escapeHtml(m.text || "")}</div>
        </div>
      </li>
    `;
  }).join("");
  messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// --- Actions ---
async function loadUsers() {
  state.users = await api("/api/users");
  renderUsers();
}

async function loadChats() {
  if (!state.asUid) { state.chats = []; renderChats(); return; }
  state.chats = await api(`/api/chats?as=${state.asUid}`);
  renderChats();
}

async function selectChat(chatId) {
  state.activeChatId = chatId;
  const chat = state.chats.find(c => c.chat_id === chatId);
  chatHeader.textContent = chat ? `${chat.kind === "dm" ? "☆" : "#"} ${chat.name}` : "—";
  // Replay
  const msgs = await api(`/api/chats/${encodeURIComponent(chatId)}/messages?limit=50`);
  state.messagesByChat[chatId] = msgs.map(m => ({
    sender_kind: m.kind === "out" ? "bot" : "user",
    sender_id: m.sender_id,
    sender_name: m.sender_name,
    text: m.text,
    ts: m.ts,
  }));
  renderChats();
  renderMessages();
}

async function send() {
  const text = msgInput.value.trim();
  if (!text || !state.asUid || !state.activeChatId) return;
  msgInput.value = "";
  await api("/api/send", {
    method: "POST",
    body: JSON.stringify({
      as: state.asUid,
      chat_id: state.activeChatId,
      text,
      mention_bot: mentionBot.checked,
    }),
  });
  // Don't optimistic-append — wait for SSE echo via fanout/adapter
}

function connectSSE() {
  if (state.eventSource) { state.eventSource.close(); }
  if (!state.asUid) return;
  state.eventSource = new EventSource(`/test/stream?as=${state.asUid}`);
  state.eventSource.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.kind !== "message") return;
    const list = state.messagesByChat[data.chat_id] || (state.messagesByChat[data.chat_id] = []);
    list.push(data);
    if (data.chat_id === state.activeChatId) renderMessages();
  };
}

// --- Setup ---
asSelect.onchange = async () => {
  state.asUid = asSelect.value;
  history.replaceState(null, "", state.asUid ? `?as=${state.asUid}` : "/test/");
  state.activeChatId = "";
  await loadChats();
  connectSSE();
};

btnSend.onclick = send;
msgInput.onkeydown = (e) => { if (e.key === "Enter") send(); };

btnAddUser.onclick = async () => {
  const name = prompt("Tên user:");
  if (!name) return;
  const isBoss = confirm("Là boss?");
  await api("/api/users", { method: "POST", body: JSON.stringify({ name, is_boss: isBoss }) });
  await loadUsers();
};

btnAddGroup.onclick = async () => {
  const name = prompt("Tên group:");
  if (!name) return;
  const memberCsv = prompt("CSV web_user_id thành viên (vd: u-aaa,u-bbb):") || "";
  const member_ids = memberCsv.split(",").map(s => s.trim()).filter(Boolean);
  await api("/api/groups", { method: "POST", body: JSON.stringify({ name, member_ids }) });
  await loadChats();
};

btnAdmin.onclick = () => { adminPane.classList.toggle("hidden"); };

// Init
const params = new URLSearchParams(location.search);
state.asUid = params.get("as") || "";
loadUsers().then(loadChats).then(connectSSE);
```

- [ ] **Step 2: Smoke test**

Run: `./scripts/restart.sh`
Mở 2 tab `http://localhost:8000/test/`:
- Tab 1: tạo Boss A (boss) + User X (non-boss)
- Tab 1: switch dropdown sang Boss A → URL update `?as=u-...`
- Tab 1: tạo group "team-1" gồm Boss A + User X
- Tab 2: switch sang User X
- Tab 1 chọn group "team-1", gửi "hello"
- Tab 2 phải thấy "hello" hiện realtime trong group "team-1"
- Tab 1: trong DM với bot, gửi "@bot tóm tắt nhóm team-1" với checkbox @bot

(Bot reply phụ thuộc LLM thật — verify reply hiển thị ở tab boss.)

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/static/test.js
git commit -m "feat(web-channel): frontend JS — state, EventSource, send/render"
```

---

## Task 16: E2E test — cross-group memory

**Files:**
- Create: `tests/e2e/test_web_cross_group_memory.py`

- [ ] **Step 1: Viết e2e (gated bởi marker slow, dùng real LLM)**

`tests/e2e/test_web_cross_group_memory.py`:
```python
"""E2E test cho web channel: agent nắm context cross-group.

Setup: 2 group, mỗi group có vài message khác chủ đề. Boss DM hỏi
about content; assert response chứa keyword từ group đúng.

Marked slow + requires real LLM keys (set qua env vars).
"""

from __future__ import annotations

import asyncio
import os

import pytest

from fastapi.testclient import TestClient


pytestmark = pytest.mark.skipif(
    not os.getenv("PLATFORM_GROQ_API_KEY") and not os.getenv("PLATFORM_OPENAI_API_KEY"),
    reason="needs real LLM keys",
)


def _send(client, *, as_uid, chat_id, text, mention=False):
    r = client.post(
        "/test/api/send",
        json={"as": as_uid, "chat_id": chat_id, "text": text, "mention_bot": mention},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_boss_dm_recalls_content_from_two_groups(clean_db):
    from src.main import app

    with TestClient(app) as client:
        # 1. Create boss + 2 non-bosses
        boss_uid = client.post(
            "/test/api/users", json={"name": "Boss", "is_boss": True}
        ).json()["id"]
        u_alice = client.post(
            "/test/api/users", json={"name": "Alice", "is_boss": False}
        ).json()["id"]
        u_bob = client.post(
            "/test/api/users", json={"name": "Bob", "is_boss": False}
        ).json()["id"]

        # 2. Two groups, both include boss
        g1 = client.post(
            "/test/api/groups",
            json={"name": "marketing", "member_ids": [boss_uid, u_alice]},
        ).json()["id"]
        g2 = client.post(
            "/test/api/groups",
            json={"name": "engineering", "member_ids": [boss_uid, u_bob]},
        ).json()["id"]

        # 3. Group messages (different topics)
        _send(client, as_uid=u_alice, chat_id=g1, text="Bài quảng cáo TikTok đã chốt ngân sách 50 triệu")
        _send(client, as_uid=u_bob, chat_id=g2, text="Migration Postgres 14 → 16 lên schedule thứ 6 tuần sau")
        await asyncio.sleep(0.5)  # let normalizer flush

        # 4. Boss DM asks across groups
        _send(client, as_uid=boss_uid, chat_id=f"dm:{boss_uid}", text="Tóm tắt nhóm marketing đang bàn gì?")
        # Wait for LLM reply
        await asyncio.sleep(8.0)

        # 5. Replay DM → should contain bot reply mentioning topic
        msgs = client.get(
            f"/test/api/chats/dm:{boss_uid}/messages?limit=50"
        ).json()
        bot_replies = [m["text"] for m in msgs if m["kind"] == "out"]
        assert any(
            ("TikTok" in r or "quảng cáo" in r or "50 triệu" in r)
            for r in bot_replies
        ), f"bot reply missed group-1 topic: {bot_replies}"
```

- [ ] **Step 2: Run e2e (skip nếu không có LLM keys)**

Run: `uv run pytest tests/e2e/test_web_cross_group_memory.py -v -s`
Expected: PASS hoặc SKIP nếu thiếu keys.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_web_cross_group_memory.py
git commit -m "test(web-channel): e2e cross-group memory recall"
```

---

## Task 17: Run full test suite + final manual smoke

- [ ] **Step 1: Full pytest**

Run: `uv run pytest tests/ -q --tb=short`
Expected: all tests pass (185+ existing + new web tests).

- [ ] **Step 2: Manual smoke checklist**

`./scripts/restart.sh` rồi mở `http://localhost:8000/test/`:
- [ ] Tạo 1 boss + 2 non-boss user qua UI
- [ ] Tạo 1 group có cả 3
- [ ] Mở 3 tab với 3 identity khác nhau, gửi message qua lại trong group
- [ ] Mention @bot trong group → bot reply hiện trong group cho cả 3 tab
- [ ] Boss DM bot, hỏi về nội dung group → bot recall đúng
- [ ] Reload tab → messages history replay đúng
- [ ] Set `ENABLE_WEB_TEST_CHANNEL=false` trong .env → restart → `/test/` trả 404

- [ ] **Step 3: Final commit (nếu có cleanup nhỏ)**

```bash
git add -A
git status  # verify clean
```

---

## Notes for the executor

- Sau mỗi task gặp test FAIL không lường trước: STOP, đọc traceback, không skip.
- Nếu `alembic upgrade head` fail → check Postgres đang chạy (`docker ps`).
- Frontend (Task 14, 15) test bằng manual smoke; nếu CI cần automation về sau, dùng Playwright (defer).
- Memory note: `./scripts/restart.sh` đủ rồi sau khi sửa `src/` — không rebuild docker.
- Bám conventions có sẵn: `BossContext`, `MessagesRepo`, event names như Zalo.
- Nếu phát hiện scope creep (vd "thêm mention parser cho text"), STOP — đó là item khác.
