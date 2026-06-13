# Channel Inbound Ingest — Boss-membership gating — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gom toàn bộ logic định danh sếp + lọc nhóm vào một wrapper chung (`InboundIngest`); chỉ nhận tin nhóm có acc chính của sếp (boss-spoke), tự deactivate khi sếp rời nhóm; mọi kênh (Zalo, Web, và sau này) chảy qua cùng cơ chế.

**Architecture:** Mỗi adapter dịch wire-format → `InboundMessage` rồi publish `inbound.normalized`. Một subscriber duy nhất `InboundIngest` xử lý handshake `/start`, resolve boss (DM qua `account_links`, group qua boss-spoke + `group_notes`), dedup, publish `message.captured`. `group_notes` (đã có) làm sổ track nhóm; không thêm bảng. Re-verify rời nhóm qua scheduler job dùng `list_members` (gate bằng `capabilities.member.list_api`).

**Tech Stack:** Python 3.12, asyncpg, FastAPI lifespan, APScheduler, alembic (op.execute raw SQL), pytest-asyncio + `clean_db` fixture (DB `*_test`).

**Spec:** `docs/superpowers/specs/2026-06-13-channel-inbound-ingest-design.md`

**Convention bám theo:**
- Repo kế thừa `BossScopedRepo(pool, ctx)`; lookup cross-boss = method riêng có docstring (như `AccountLinksRepo.lookup`).
- Event bus: `bus.publish(name, dict)`, payload là dict; nhiều subscriber/topic, chạy concurrent.
- Migration: file `migrations/versions/00NN_*.py`, `op.execute(<raw SQL>)`, có `upgrade`/`downgrade`.
- Test integration: `async def test_x(clean_db)`, dựng dữ liệu bằng repo/SQL thật.

---

## Task 1: Migration 0013 — messages unique theo boss + index gate

**Files:**
- Create: `migrations/versions/0013_boss_scoped_message_dedup.py`
- Test: `tests/integration/test_migration_0013.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_migration_0013.py
import pytest


@pytest.mark.asyncio
async def test_messages_unique_includes_boss_id(clean_db):
    async with clean_db.acquire() as c:
        cols = await c.fetch(
            """
            SELECT a.attname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
            JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = k.attnum
            WHERE rel.relname = 'messages' AND con.contype = 'u'
            ORDER BY k.ord
            """
        )
    names = [r["attname"] for r in cols]
    assert names == ["boss_id", "provider", "chat_id", "provider_msg_id"]


@pytest.mark.asyncio
async def test_group_notes_gate_index_exists(clean_db):
    async with clean_db.acquire() as c:
        idx = await c.fetchval(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_group_notes_gate'"
        )
    assert idx == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_migration_0013.py -v`
Expected: FAIL — unique hiện là `(provider, chat_id, provider_msg_id)`; index chưa có.

- [ ] **Step 3: Write the migration**

```python
# migrations/versions/0013_boss_scoped_message_dedup.py
"""messages dedup theo boss + index gate group_notes

- messages: UNIQUE (provider, chat_id, provider_msg_id)
            -> UNIQUE (boss_id, provider, chat_id, provider_msg_id)
  Mô hình tenant vốn mỗi sếp một bản sao; cần cho nhóm nhiều sếp.
- group_notes: index (provider, chat_id) WHERE is_active cho bước gate cross-boss.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-14
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "DROP CONSTRAINT IF EXISTS messages_provider_chat_id_provider_msg_id_key"
    )
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT messages_boss_dedup_key "
        "UNIQUE (boss_id, provider, chat_id, provider_msg_id)"
    )
    op.execute(
        "CREATE INDEX idx_group_notes_gate ON group_notes (provider, chat_id) "
        "WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_group_notes_gate")
    op.execute(
        "ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_boss_dedup_key"
    )
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT messages_provider_chat_id_provider_msg_id_key "
        "UNIQUE (provider, chat_id, provider_msg_id)"
    )
```

- [ ] **Step 4: Apply migration to test DB + run test**

Run: `POSTGRES_DSN="$POSTGRES_DSN" alembic upgrade head && pytest tests/integration/test_migration_0013.py -v`
(Nếu test dùng DB `*_test` tự bootstrap — chạy lại `pytest` là đủ vì conftest tự `alembic upgrade`.)
Expected: PASS cả 2 test.

- [ ] **Step 5: Update `MessagesRepo.insert` ON CONFLICT cho khớp constraint mới**

Modify `src/repositories/messages.py:38` — đổi:
```python
                ON CONFLICT (provider, chat_id, provider_msg_id) DO NOTHING
```
thành:
```python
                ON CONFLICT (boss_id, provider, chat_id, provider_msg_id) DO NOTHING
```

- [ ] **Step 6: Run existing messages tests**

Run: `pytest tests/integration -k "message" -v`
Expected: PASS (không regress).

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/0013_boss_scoped_message_dedup.py tests/integration/test_migration_0013.py src/repositories/messages.py
git commit -m "feat(schema): messages dedup theo boss + index gate group_notes (0013)"
```

---

## Task 2: GroupNotesRepo — gate methods (ensure_tracked / bosses_tracking / mark_left)

**Files:**
- Modify: `src/repositories/group_notes.py`
- Test: `tests/integration/test_group_notes_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_group_notes_gate.py
import pytest

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo


async def _mk_boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1,$2,'boss') RETURNING id",
            email, email,
        )


@pytest.mark.asyncio
async def test_ensure_tracked_creates_then_reactivates_left(clean_db):
    boss = await _mk_boss(clean_db, "b1@x.test")
    repo = GroupNotesRepo(clean_db, BossContext(boss_id=boss, user_role="boss"))

    await repo.ensure_tracked("zalo", "g1", group_name="Team")
    assert await repo.bosses_tracking("zalo", "g1") == [boss]

    # boss rời nhóm -> mark_left -> không còn tracked
    await repo.mark_left(boss, "zalo", "g1")
    assert await repo.bosses_tracking("zalo", "g1") == []

    # boss quay lại nói -> ensure_tracked reactivate (status='left' -> active)
    await repo.ensure_tracked("zalo", "g1", group_name="Team")
    assert await repo.bosses_tracking("zalo", "g1") == [boss]


@pytest.mark.asyncio
async def test_ensure_tracked_keeps_manual_pause(clean_db):
    boss = await _mk_boss(clean_db, "b2@x.test")
    repo = GroupNotesRepo(clean_db, BossContext(boss_id=boss, user_role="boss"))
    await repo.ensure_tracked("zalo", "g2")
    # sếp tự tắt thủ công
    async with clean_db.acquire() as c:
        await c.execute(
            "UPDATE group_notes SET is_active=FALSE, status='paused' "
            "WHERE boss_id=$1 AND provider='zalo' AND chat_id='g2'",
            boss,
        )
    # boss nói lại -> KHÔNG tự reactivate (paused != left)
    await repo.ensure_tracked("zalo", "g2")
    assert await repo.bosses_tracking("zalo", "g2") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_group_notes_gate.py -v`
Expected: FAIL — `ensure_tracked` / `bosses_tracking` / `mark_left` chưa tồn tại.

- [ ] **Step 3: Add methods to `GroupNotesRepo`**

Thêm vào `src/repositories/group_notes.py` (trong class `GroupNotesRepo`):

```python
    async def ensure_tracked(
        self,
        provider: str,
        chat_id: str,
        group_name: str | None = None,
    ) -> None:
        """Đánh dấu nhóm được track cho boss hiện tại (gọi khi sếp nói câu đầu).

        - Chưa có row  -> tạo (is_active=TRUE, status='active').
        - status='left' -> reactivate (sếp quay lại nhóm).
        - status khác (vd 'paused' do tự tắt) -> GIỮ nguyên, không bật lại.
        """
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (boss_id, provider, chat_id) DO UPDATE SET
                  is_active = CASE WHEN group_notes.status='left' THEN TRUE
                                   ELSE group_notes.is_active END,
                  status    = CASE WHEN group_notes.status='left' THEN 'active'
                                   ELSE group_notes.status END,
                  group_name = COALESCE(EXCLUDED.group_name, group_notes.group_name)
                """,
                self.ctx.boss_id, provider, chat_id, group_name,
            )

    async def bosses_tracking(self, provider: str, chat_id: str) -> list[int]:
        """Cross-boss: các boss đang track (is_active) nhóm này. Dùng bởi InboundIngest."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT boss_id FROM group_notes
                WHERE provider=$1 AND chat_id=$2 AND is_active
                ORDER BY boss_id
                """,
                provider, chat_id,
            )
        return [r["boss_id"] for r in rows]

    async def mark_left(self, boss_id: int, provider: str, chat_id: str) -> None:
        """Cross-boss: sếp rời nhóm -> deactivate (status='left'). Dùng bởi re-verify job."""
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE group_notes SET is_active=FALSE, status='left', updated_at=NOW()
                WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
                """,
                boss_id, provider, chat_id,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_group_notes_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/group_notes.py tests/integration/test_group_notes_gate.py
git commit -m "feat(repo): group_notes gate methods — ensure_tracked/bosses_tracking/mark_left"
```

---

## Task 3: InboundIngest — wrapper chung (handshake + DM resolve + group gate + dedup + publish)

**Files:**
- Create: `src/channels/ingest.py`
- Test: `tests/integration/test_inbound_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_inbound_ingest.py
import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.events.bus import InMemoryEventBus


async def _boss_with_link(pool, email, provider, uid, bot_acc_id):
    async with pool.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1,$2,'boss') RETURNING id",
            email, email,
        )
        await c.execute(
            "INSERT INTO account_links (boss_id, provider, provider_user_id) VALUES ($1,$2,$3)",
            boss, provider, uid,
        )
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1,$2,$3,'boss_owned','active')
            """,
            boss, provider, bot_acc_id,
        )
    return boss


async def _bot_acc(pool, owner_boss_id=None):
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts (provider, provider_user_id, account_kind, ownership, owner_boss_id)
            VALUES ('zalo', $1, 'personal', $2, $3) RETURNING id
            """,
            f"botuid-{owner_boss_id}", "boss_owned" if owner_boss_id else "platform", owner_boss_id,
        )


def _msg(**kw):
    base = dict(
        bot_account_id=0, provider="zalo", chat_id="g1", chat_type="group",
        provider_msg_id="m1", sender_provider_id="U_BOSS", sender_name="Boss",
        text="hello", mentions_bot=False, reply_to_provider_msg_id=None,
        media_kind="text", media_url=None, ts=datetime.now(tz=timezone.utc),
    )
    base.update(kw)
    return InboundMessage(**base)


@pytest.mark.asyncio
async def test_group_dropped_until_boss_speaks_then_captures(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    boss = await _boss_with_link(clean_db, "gb@x.test", "zalo", "U_BOSS", acc)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    # 1) Người lạ nói trước khi boss nói -> drop
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_OTHER", provider_msg_id="m0", text="spam?")})
    await asyncio.sleep(0)
    assert captured == []

    # 2) Boss nói -> track + captured (sender_is_boss True)
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_BOSS", provider_msg_id="m1", text="hi team")})
    await asyncio.sleep(0)
    assert len(captured) == 1
    assert captured[0]["boss_id"] == boss
    assert captured[0]["sender_is_boss"] is True

    # 3) Người lạ nói SAU khi đã track -> captured (sender_is_boss False)
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, sender_provider_id="U_OTHER", provider_msg_id="m2", text="fyi")})
    await asyncio.sleep(0)
    assert len(captured) == 2
    assert captured[1]["sender_is_boss"] is False


@pytest.mark.asyncio
async def test_dm_from_boss_captured_stranger_dropped(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    boss = await _boss_with_link(clean_db, "db@x.test", "zalo", "U_BOSS", acc)
    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_BOSS", sender_provider_id="U_BOSS",
        provider_msg_id="d1", text="nhắc tôi 3h")})
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_X", sender_provider_id="U_X",
        provider_msg_id="d2", text="ai đó")})
    await asyncio.sleep(0)
    assert [c["sender_is_boss"] for c in captured] == [True]
    assert captured[0]["boss_id"] == boss


@pytest.mark.asyncio
async def test_start_handshake_links_and_does_not_persist(clean_db):
    acc = await _bot_acc(clean_db, owner_boss_id=None)
    # boss tồn tại + assignment active, NHƯNG chưa có account_links
    async with clean_db.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ('hs@x.test','hs','boss') RETURNING id")
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id, assignment_kind, status)"
            " VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
    from src.services.linking_service import LinkingService
    token = await LinkingService(clean_db).generate(boss, "zalo", acc)

    sent: list[dict] = []

    class _OB:
        async def send(self, **kw):
            sent.append(kw)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus, outbound_service=_OB()).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, chat_type="dm", chat_id="U_NEW", sender_provider_id="U_NEW",
        provider_msg_id="h1", text=f"/start {token}")})
    await asyncio.sleep(0)

    assert captured == []  # handshake không persist
    assert len(sent) == 1  # có ack
    async with clean_db.acquire() as c:
        link = await c.fetchval(
            "SELECT boss_id FROM account_links WHERE provider='zalo' AND provider_user_id='U_NEW'")
    assert link == boss
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_inbound_ingest.py -v`
Expected: FAIL — `src.channels.ingest` chưa tồn tại.

- [ ] **Step 3: Implement `InboundIngest`**

```python
# src/channels/ingest.py
"""InboundIngest — wrapper định danh + lọc nhóm dùng chung cho MỌI kênh.

Mỗi adapter dịch wire-format -> InboundMessage rồi publish ``inbound.normalized``
({"message": InboundMessage}). Đây là subscriber DUY NHẤT cho topic đó. Không
kênh nào tự resolve boss hay tự publish ``message.captured``.

Luồng:
  - DM "/start <token>"  -> LinkingService.consume -> ack, KHÔNG persist.
  - DM thường            -> resolve boss qua account_links (scope theo assignment).
  - Group                -> boss-spoke: sếp nói -> ensure_tracked; chỉ capture nếu
                            nhóm đã track cho ít nhất một boss assign vào bot acc này.
  - Dedup + insert per-boss + publish ``message.captured`` (mỗi boss một event).
"""

from __future__ import annotations

import hashlib
import logging

from src.channels.base import InboundMessage
from src.channels.zalo.inbound_filter import should_drop_normalized
from src.domain.message import NewMessage
from src.events.bus import EventBus
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.repositories.messages import MessagesRepo

log = logging.getLogger(__name__)


class InboundIngest:
    def __init__(self, pool, bus: EventBus, outbound_service=None):
        self.pool = pool
        self.bus = bus
        self.outbound_service = outbound_service

    def register(self) -> None:
        self.bus.subscribe("inbound.normalized", self._handle)

    async def _handle(self, payload: dict) -> None:
        msg: InboundMessage = payload["message"]
        if should_drop_normalized(msg):
            return
        if msg.chat_type == "dm":
            await self._handle_dm(msg)
        else:
            await self._handle_group(msg)

    # ---- candidates / identity helpers -----------------------------------

    async def _candidates(self, bot_account_id) -> list[int]:
        if bot_account_id is None:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT boss_id FROM bot_account_assignments "
                "WHERE bot_account_id=$1 AND status='active'",
                bot_account_id,
            )
        return [r["boss_id"] for r in rows]

    async def _sender_boss(self, provider, sender_uid, candidates) -> int | None:
        if not sender_uid or not candidates:
            return None
        async with self.pool.acquire() as c:
            return await c.fetchval(
                "SELECT boss_id FROM account_links "
                "WHERE provider=$1 AND provider_user_id=$2 AND boss_id = ANY($3::int[])",
                provider, sender_uid, candidates,
            )

    # ---- DM ---------------------------------------------------------------

    async def _handle_dm(self, msg: InboundMessage) -> None:
        text = msg.text or ""
        if text.startswith("/start "):
            await self._handshake(msg, text.split(" ", 1)[1].strip())
            return
        candidates = await self._candidates(msg.bot_account_id)
        boss_id = await self._sender_boss(msg.provider, msg.sender_provider_id, candidates)
        if boss_id is None:
            return
        await self._persist_and_publish(msg, boss_id, sender_is_boss=True)

    async def _handshake(self, msg: InboundMessage, token: str) -> None:
        from src.services.linking_service import LinkingService

        boss_id = await LinkingService(self.pool).consume(
            token=token,
            sender_provider_uid=msg.sender_provider_id,
            bot_account_id=msg.bot_account_id,
        )
        if boss_id is not None and self.outbound_service is not None:
            await self.outbound_service.send(
                boss_id=boss_id, provider=msg.provider, chat_id=msg.chat_id,
                content="Đã kết nối. Em là bot của anh ở đây.", trigger="system",
            )
        else:
            log.info("handshake rejected provider=%s bot_acc=%s sender=%s",
                     msg.provider, msg.bot_account_id, msg.sender_provider_id)

    # ---- Group ------------------------------------------------------------

    async def _handle_group(self, msg: InboundMessage) -> None:
        candidates = await self._candidates(msg.bot_account_id)
        if not candidates:
            return
        sender_boss = await self._sender_boss(
            msg.provider, msg.sender_provider_id, candidates)
        if sender_boss is not None:
            await GroupNotesRepo(
                self.pool, BossContext(boss_id=sender_boss, user_role="boss")
            ).ensure_tracked(msg.provider, msg.chat_id, group_name=None)

        tracked = await GroupNotesRepo(
            self.pool, BossContext(boss_id=0, user_role="superadmin")
        ).bosses_tracking(msg.provider, msg.chat_id)
        tracked = [b for b in tracked if b in candidates]
        if not tracked:
            return
        for boss_id in tracked:
            await self._persist_and_publish(
                msg, boss_id, sender_is_boss=(boss_id == sender_boss))

    # ---- persist ----------------------------------------------------------

    def _dedup_id(self, msg: InboundMessage) -> str:
        if msg.provider_msg_id:
            return msg.provider_msg_id
        ts = int(msg.ts.timestamp()) if msg.ts else 0
        h = hashlib.sha1((msg.text or "").encode()).hexdigest()[:10]
        return f"syn:{msg.sender_provider_id or ''}:{ts}:{h}"

    async def _persist_and_publish(self, msg, boss_id: int, sender_is_boss: bool) -> None:
        repo = MessagesRepo(self.pool, BossContext(boss_id=boss_id, user_role="boss"))
        msg_id = await repo.insert(NewMessage(
            provider=msg.provider, chat_id=msg.chat_id, chat_type=msg.chat_type,
            provider_msg_id=self._dedup_id(msg),
            sender_provider_id=msg.sender_provider_id or None,
            sender_name=msg.sender_name, text=msg.text or None,
            media_kind=msg.media_kind or "text", media_url=msg.media_url,
            media_text=None, ts=msg.ts,
        ))
        if msg_id is None:
            return  # dedup
        await self.bus.publish("message.captured", {
            "message_id": msg_id, "boss_id": boss_id, "provider": msg.provider,
            "chat_id": msg.chat_id, "chat_type": msg.chat_type,
            "mentions_bot": bool(msg.mentions_bot), "sender_is_boss": sender_is_boss,
            "text": msg.text, "bot_account_id": msg.bot_account_id,
        })
```

- [ ] **Step 4: Add `should_drop_normalized` to inbound_filter (works on `InboundMessage`)**

Thêm vào `src/channels/zalo/inbound_filter.py`:

```python
def should_drop_normalized(msg) -> bool:
    """Như should_drop nhưng cho InboundMessage đã chuẩn hoá (dùng bởi InboundIngest)."""
    text = (msg.text or "").strip()
    if not text and not msg.media_url:
        return True
    return False
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/integration/test_inbound_ingest.py -v`
Expected: PASS cả 3 test.

- [ ] **Step 6: Commit**

```bash
git add src/channels/ingest.py src/channels/zalo/inbound_filter.py tests/integration/test_inbound_ingest.py
git commit -m "feat(channels): InboundIngest wrapper — handshake + DM/group gate boss-spoke + dedup"
```

---

## Task 4: BaseChannelAdapter — `_emit_inbound` mixin

**Files:**
- Modify: `src/channels/base.py`
- Test: `tests/integration/test_base_adapter_emit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_base_adapter_emit.py
import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import BaseChannelAdapter, InboundMessage
from src.events.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_emit_inbound_publishes_normalized():
    bus = InMemoryEventBus()

    class A(BaseChannelAdapter):
        provider = "zalo"

    a = A(bus)
    seen: list[dict] = []
    bus.subscribe("inbound.normalized", lambda p: seen.append(p) or asyncio.sleep(0))

    msg = InboundMessage(
        bot_account_id=1, provider="zalo", chat_id="g", chat_type="group",
        provider_msg_id="m", sender_provider_id="u", sender_name="x", text="hi",
        mentions_bot=False, reply_to_provider_msg_id=None, media_kind="text",
        media_url=None, ts=datetime.now(tz=timezone.utc))
    await a._emit_inbound(msg)
    await asyncio.sleep(0)
    assert seen and seen[0]["message"] is msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_base_adapter_emit.py -v`
Expected: FAIL — `BaseChannelAdapter` chưa tồn tại.

- [ ] **Step 3: Add `BaseChannelAdapter` to `src/channels/base.py`**

Thêm vào cuối `src/channels/base.py`:

```python
class BaseChannelAdapter:
    """Base cho adapter: cung cấp đường DUY NHẤT đẩy tin vào hệ thống.

    Adapter chỉ việc dịch wire-format -> InboundMessage rồi gọi _emit_inbound.
    Toàn bộ định danh/lọc/persist do InboundIngest (subscriber inbound.normalized).
    """

    def __init__(self, bus, *args, **kwargs):
        self.bus = bus

    async def _emit_inbound(self, msg: "InboundMessage") -> None:
        await self.bus.publish("inbound.normalized", {"message": msg})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_base_adapter_emit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/channels/base.py tests/integration/test_base_adapter_emit.py
git commit -m "feat(channels): BaseChannelAdapter._emit_inbound — entry chuẩn inbound.normalized"
```

---

## Task 5: Wire InboundIngest trong lifespan (đăng ký một lần)

**Files:**
- Modify: `src/main.py` (vùng lifespan ~ dòng 84-90)

- [ ] **Step 1: Thêm đăng ký InboundIngest TRƯỚC discover_and_load**

Trong `src/main.py`, ngay sau khối `register_artifacts(...)` và trước/sau khi tạo `outbound_service`, thêm (đặt sau khi `outbound_service` đã tạo, trước `discover_and_load`):

```python
    # Wrapper định danh + lọc nhóm dùng chung — subscriber duy nhất cho
    # inbound.normalized. Phải đăng ký TRƯỚC khi channels boot_inbound.
    from src.channels.ingest import InboundIngest
    InboundIngest(
        app.state.db_pool, app.state.bus, app.state.outbound_service
    ).register()
```

> Vị trí chính xác: chèn ngay sau khối tạo `app.state.outbound_service = OutboundService(...)` (kết thúc ở `src/main.py:96`) và trước `_setup_ctx = ChannelSetupContext(...)`.

- [ ] **Step 2: Smoke import**

Run: `python -c "import src.main"`
Expected: không lỗi import.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat(app): đăng ký InboundIngest một lần trong lifespan"
```

---

## Task 6: Zalo adapter → emit InboundMessage; bỏ zalo normalizer

**Files:**
- Modify: `src/channels/zalo/adapter.py` (`_handle_event`, `__init__`, class base)
- Modify: `src/channels/zalo/__init__.py` (bỏ `_normalizer.register`)
- Delete: `src/channels/zalo/normalizer.py`
- Test: `tests/integration/test_zalo_adapter.py` (cập nhật)

- [ ] **Step 1: Cập nhật test adapter sang topic mới**

Trong `tests/integration/test_zalo_adapter.py`: đổi mọi `bus.subscribe("inbound.raw.zalo", ...)` → `bus.subscribe("inbound.normalized", ...)`, và assert payload là `InboundMessage`:
```python
from src.channels.base import InboundMessage
# ...
seen: list[dict] = []
bus.subscribe("inbound.normalized", lambda p: seen.append(p) or _noop())
# ... sau khi adapter nhận 1 message từ bridge giả:
assert isinstance(seen[0]["message"], InboundMessage)
assert seen[0]["message"].bot_account_id == bot_acc.id
assert seen[0]["message"].chat_type == "group"
```
(Các test ở `test_zalo_adapter.py` đang dựa `message.captured` qua normalizer cũ — chuyển sang test parse→`inbound.normalized`. Phần resolve boss đã có test riêng ở `test_inbound_ingest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_zalo_adapter.py -v`
Expected: FAIL — adapter vẫn publish `inbound.raw.zalo`.

- [ ] **Step 3: Sửa adapter — kế thừa base + build InboundMessage**

`src/channels/zalo/adapter.py`:
- Đổi khai báo class: `class ZaloAdapter(BaseChannelAdapter):` và import `from src.channels.base import BaseChannelAdapter, InboundMessage`.
- Trong `__init__`, gọi `super().__init__(bus)` rồi giữ phần còn lại:
```python
    def __init__(self, bus: EventBus, bot_accounts_repo: Any = None):
        super().__init__(bus)
        self.repo = bot_accounts_repo
        self._procs = {}
        self._req_seq = {}
        self._pending = {}
        self._sessions_dir = Path(tempfile.mkdtemp(prefix="zalo_session_"))
```
- Thay `_handle_event` nhánh `ev == "message"`: build `InboundMessage` từ `data` + `own_uid` rồi `await self._emit_inbound(msg)`:
```python
    async def _handle_event(self, bot_acc, obj: dict) -> None:
        ev = obj.get("event")
        data = obj.get("data") or {}
        if ev == "message":
            await self._emit_inbound(self._to_inbound(bot_acc, data, obj.get("own_uid")))
        elif ev == "ready":
            log.info("zalo bridge ready bot_acc=%s own_id=%s", bot_acc.id, data.get("own_id"))
        elif ev == "disconnected":
            await self.bus.publish("bot_account.status_changed", {
                "bot_account_id": bot_acc.id,
                "to": "logged_out" if data.get("fatal") else "rate_limited",
                "reason": data.get("reason")})
        elif ev == "status":
            await self.bus.publish("bot_account.status_changed", {
                "bot_account_id": bot_acc.id, "to": data.get("status"),
                "reason": data.get("reason")})

    def _to_inbound(self, bot_acc, data: dict, own_uid) -> InboundMessage:
        from datetime import datetime, timezone
        text = data.get("text") or data.get("content") or ""
        if not isinstance(text, str):
            text = ""
        mentions = data.get("mentions") or []
        mentions_bot = bool(data.get("is_mentioned")) or any(
            m.get("uid") == own_uid for m in mentions)
        ms = data.get("ts") or data.get("ts_ms") or 0
        try:
            ts = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        except Exception:
            ts = datetime.now(tz=timezone.utc)
        reply = data.get("reply_to") or {}
        return InboundMessage(
            bot_account_id=bot_acc.id, provider="zalo",
            chat_id=str(data.get("threadId") or data.get("thread_id") or ""),
            chat_type="dm" if data.get("type") == 0 else "group",
            provider_msg_id=(str(data.get("msgId") or data.get("msg_id") or "") or None),
            sender_provider_id=str(data.get("uidFrom") or data.get("sender_uid") or ""),
            sender_name=data.get("dName") or data.get("sender_name"),
            text=text, mentions_bot=mentions_bot,
            reply_to_provider_msg_id=(reply.get("msg_id") or None),
            media_kind=data.get("content_type") or "text",
            media_url=data.get("media_url"), ts=ts, raw=data)
```

- [ ] **Step 4: Bỏ normalizer khỏi setup + xoá file**

`src/channels/zalo/__init__.py`:
```python
from src.channels.registry import ChannelSetupContext
from src.channels.zalo.adapter import ZaloAdapter


def setup(ctx: ChannelSetupContext) -> ZaloAdapter:
    return ZaloAdapter(ctx.bus, ctx.admin_repo)
```
Rồi: `git rm src/channels/zalo/normalizer.py`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/integration/test_zalo_adapter.py tests/integration/test_inbound_ingest.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A src/channels/zalo tests/integration/test_zalo_adapter.py
git commit -m "refactor(zalo): adapter emit InboundMessage qua _emit_inbound; bỏ zalo normalizer"
```

---

## Task 7: Web → emit InboundMessage (bot_account_id thật); bỏ web normalizer

**Files:**
- Modify: `src/channels/web/routes.py` (chỗ đang publish `inbound.raw.web`)
- Modify: `src/channels/web/__init__.py` (bỏ `normalizer.register`)
- Delete: `src/channels/web/normalizer.py`
- Test: `tests/integration/test_web_normalizer.py` → đổi tên test cho khớp boss-spoke
- Modify: `src/web/routes/api_admin.py:2178` (admin-inject) → publish `inbound.normalized`

- [ ] **Step 1: Cập nhật test web sang boss-spoke**

Trong `tests/integration/test_web_normalizer.py`:
- `test_normalizer_dm_inserts_message_and_publishes_captured`: đổi `web_normalizer.register(bus, clean_db)` → đăng ký `InboundIngest(clean_db, bus).register()`, và publish `inbound.normalized` với `InboundMessage` (chat_type="dm"). Cần promote boss (đã có account_links provider='web' qua `BossPromotionService`) + assignment 'web' active (promotion đã tạo). DM từ boss → captured.
- `test_normalizer_group_resolves_boss_via_member` → đổi thành `test_group_requires_boss_to_speak`: người lạ nói trước → drop; boss (web_user là boss) nói → track + captured.

```python
import asyncio
from datetime import datetime, timezone

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo
from src.events.bus import InMemoryEventBus


async def _web_bot_acc(pool):
    async with pool.acquire() as c:
        return await c.fetchval(
            "SELECT id FROM bot_accounts WHERE provider='web' AND status='active' LIMIT 1")


def _wmsg(acc, **kw):
    base = dict(
        bot_account_id=acc, provider="web", chat_id="g1", chat_type="group",
        provider_msg_id="m1", sender_provider_id="u", sender_name="x", text="hi",
        mentions_bot=False, reply_to_provider_msg_id=None, media_kind="text",
        media_url=None, ts=datetime.now(tz=timezone.utc))
    base.update(kw)
    return InboundMessage(**base)


@pytest.mark.asyncio
async def test_web_group_requires_boss_to_speak(clean_db):
    users = WebUsersRepo(clean_db)
    boss_uid = await users.create(name="Boss", is_boss=False)
    boss_id = await BossPromotionService(clean_db).promote(boss_uid)
    acc = await _web_bot_acc(clean_db)

    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or asyncio.sleep(0))

    await bus.publish("inbound.normalized", {"message": _wmsg(
        acc, chat_id="gw", sender_provider_id="stranger", provider_msg_id="w0")})
    await asyncio.sleep(0)
    assert captured == []

    await bus.publish("inbound.normalized", {"message": _wmsg(
        acc, chat_id="gw", sender_provider_id=boss_uid, provider_msg_id="w1")})
    await asyncio.sleep(0)
    assert len(captured) == 1 and captured[0]["boss_id"] == boss_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_web_normalizer.py -v`
Expected: FAIL — web vẫn đi qua `inbound.raw.web`.

- [ ] **Step 3: Sửa web routes — publish `inbound.normalized` với bot_account_id thật**

Tại chỗ `routes.py` đang `bus.publish("inbound.raw.web", {...})`: build `InboundMessage` và publish `inbound.normalized`. Resolve `web` bot_account_id một lần (cache trên adapter trong `setup`, hoặc query `SELECT id FROM bot_accounts WHERE provider='web' AND status='active' LIMIT 1`). Ví dụ:
```python
from src.channels.base import InboundMessage
from datetime import datetime, timezone

msg = InboundMessage(
    bot_account_id=web_bot_account_id,   # resolve once tại setup/route state
    provider="web", chat_id=chat_id, chat_type=chat_type,
    provider_msg_id=provider_msg_id, sender_provider_id=web_user_id,
    sender_name=sender_name, text=text or "", mentions_bot=bool(mention_bot),
    reply_to_provider_msg_id=None, media_kind=media_kind or "text",
    media_url=media_url, ts=datetime.now(tz=timezone.utc))
await bus.publish("inbound.normalized", {"message": msg})
```

- [ ] **Step 4: Bỏ web normalizer + sửa admin-inject**

- `src/channels/web/__init__.py`: bỏ dòng `normalizer.register(ctx.bus, ctx.pool)` và import; thêm resolve web bot_account_id để route dùng (gắn `adapter.web_bot_account_id`).
- `git rm src/channels/web/normalizer.py`.
- `src/web/routes/api_admin.py` (~2178): thay khối publish `message.captured` trực tiếp bằng publish `inbound.normalized` với `InboundMessage` (chat_type="dm", sender = boss's web uid). Bỏ phần tự set `sender_is_boss=True` (ingest tự resolve).

- [ ] **Step 5: Run tests**

Run: `pytest tests/integration/test_web_normalizer.py tests/integration/test_api_admin_chat.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A src/channels/web src/web/routes/api_admin.py tests/integration/test_web_normalizer.py
git commit -m "refactor(web): inbound qua InboundIngest (bot_account_id thật); bỏ web normalizer + admin-inject"
```

---

## Task 8: Outbound thread_kind — bỏ heuristic độ dài

**Files:**
- Modify: `src/services/outbound_service.py` (`send`, `_persist_queued`)
- Modify: `src/agents/dm_responder.py`, `src/agents/in_group_responder.py` (truyền `chat_type`)
- Test: `tests/integration/test_outbound_thread_kind.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_outbound_thread_kind.py
import pytest

from src.services.outbound_service import OutboundService


class _Adapter:
    provider = "zalo"
    def normalize_text(self, t): return t
    def classify_thread_kind(self, chat_id): return "group"  # heuristic CŨ (sai cho DM)
    async def send_text(self, bot_acc, chat_id, text, thread_kind):
        self.kind = thread_kind
        return "ok"


class _Reg:
    def __init__(self, a): self.a = a
    def get(self, p): return self.a


class _AdminRepo:
    async def find_active_for_boss(self, boss_id, provider): return object()


@pytest.mark.asyncio
async def test_outbound_uses_explicit_chat_type_for_dm():
    a = _Adapter()
    svc = OutboundService(None, _Bus(), _Reg(a), _AdminRepo())
    await svc.send(boss_id=1, provider="zalo", chat_id="123456789012345678901",
                   content="hi", trigger="dm", chat_type="dm")
    assert a.kind == "user"  # KHÔNG bị heuristic ép thành group


class _Bus:
    async def publish(self, *a, **k): ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_outbound_thread_kind.py -v`
Expected: FAIL — `send()` chưa nhận `chat_type`; vẫn gọi `classify_thread_kind`.

- [ ] **Step 3: Sửa `OutboundService.send`**

Thêm tham số `chat_type: str | None = None`; khi có → `thread_kind = "group" if chat_type == "group" else "user"`; chỉ fallback `adapter.classify_thread_kind(chat_id)` khi `chat_type is None` (giữ tương thích chỗ gọi cũ chưa truyền):
```python
    async def send(self, *, boss_id, provider, chat_id, content, trigger,
                   reply_to_message_id=None, chat_type=None):
        ...
        else:
            text = adapter.normalize_text(content)
            if chat_type is not None:
                thread_kind = "group" if chat_type == "group" else "user"
            else:
                thread_kind = adapter.classify_thread_kind(chat_id)
            ...
```

- [ ] **Step 4: Truyền `chat_type` từ responders**

- `src/agents/dm_responder.py`: `ctx.outbound_service.send(..., trigger="dm", chat_type="dm")`.
- `src/agents/in_group_responder.py`: cả 2 chỗ `send(...)` thêm `chat_type="group"`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/integration/test_outbound_thread_kind.py tests/integration -k outbound -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/outbound_service.py src/agents/dm_responder.py src/agents/in_group_responder.py tests/integration/test_outbound_thread_kind.py
git commit -m "fix(outbound): dùng chat_type tường minh thay heuristic classify_thread_kind"
```

---

## Task 9: Re-verify rời nhóm → auto deactivate (scheduler job)

**Files:**
- Create: `src/scheduler/jobs/group_membership_reverify.py`
- Modify: `src/scheduler/runner.py` (đăng ký job)
- Modify: `src/channels/capabilities.py` (thêm `WEB_CAPS` để Web có `member.list_api`)
- Test: `tests/integration/test_group_reverify.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_group_reverify.py
import pytest

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.scheduler.jobs.group_membership_reverify import reverify_once


class _Adapter:
    provider = "zalo"
    def __init__(self, members): self._m = members
    async def list_members(self, bot_acc, group_id): return self._m


class _Reg:
    def __init__(self, a): self._a = a
    def adapters(self): return [self._a]
    def get(self, p): return self._a


async def _setup(pool, members):
    async with pool.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email,name,role) VALUES ('rv@x.test','rv','boss') RETURNING id")
        acc = await c.fetchval(
            "INSERT INTO bot_accounts (provider,provider_user_id,account_kind,ownership,owner_boss_id)"
            " VALUES ('zalo','b',$1,'boss_owned',$2) RETURNING id", "boss_owned", boss)
        await c.execute(
            "INSERT INTO account_links (boss_id,provider,provider_user_id) VALUES ($1,'zalo','U_BOSS')", boss)
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id,provider,bot_account_id,assignment_kind,status)"
            " VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
    repo = GroupNotesRepo(pool, BossContext(boss_id=boss, user_role="boss"))
    await repo.ensure_tracked("zalo", "gx")
    return boss, acc, repo


@pytest.mark.asyncio
async def test_reverify_deactivates_when_boss_absent(clean_db):
    boss, acc, repo = await _setup(clean_db, members=["U_OTHER"])  # boss KHÔNG còn
    await reverify_once(clean_db, _Reg(_Adapter(["U_OTHER"])))
    assert await repo.bosses_tracking("zalo", "gx") == []


@pytest.mark.asyncio
async def test_reverify_keeps_when_boss_present(clean_db):
    boss, acc, repo = await _setup(clean_db, members=["U_BOSS", "U_OTHER"])
    await reverify_once(clean_db, _Reg(_Adapter(["U_BOSS", "U_OTHER"])))
    assert await repo.bosses_tracking("zalo", "gx") == [boss]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_group_reverify.py -v`
Expected: FAIL — module chưa tồn tại.

- [ ] **Step 3: Implement job**

```python
# src/scheduler/jobs/group_membership_reverify.py
"""Re-verify nhóm đang track: nếu acc chính của sếp không còn trong nhóm -> deactivate.

DUY NHẤT chỗ dùng list_members — để TẮT, không phải để bật (bật vẫn boss-spoke).
Gate theo capabilities.member.list_api: kênh không hỗ trợ -> bỏ qua.
"""

from __future__ import annotations

import logging
from typing import Any

from src.channels.capabilities import caps_for
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo

log = logging.getLogger(__name__)

_SUPER = BossContext(boss_id=0, user_role="superadmin")


async def reverify_once(pool, registry) -> None:
    repo = GroupNotesRepo(pool, _SUPER)
    for adapter in registry.adapters():
        provider = adapter.provider
        if not caps_for(provider).get("member.list_api"):
            continue
        async with pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT gn.boss_id, gn.chat_id, al.provider_user_id AS boss_uid,
                       baa.bot_account_id
                FROM group_notes gn
                JOIN account_links al
                  ON al.boss_id = gn.boss_id AND al.provider = gn.provider
                JOIN bot_account_assignments baa
                  ON baa.boss_id = gn.boss_id AND baa.provider = gn.provider
                     AND baa.status='active'
                WHERE gn.provider=$1 AND gn.is_active
                """,
                provider,
            )
        for r in rows:
            try:
                acc = type("X", (), {"id": r["bot_account_id"], "owner_boss_id": None})()
                members = await adapter.list_members(acc, r["chat_id"])
            except Exception:
                log.exception("reverify list_members failed provider=%s chat=%s",
                              provider, r["chat_id"])
                continue
            if r["boss_uid"] not in set(map(str, members)):
                await repo.mark_left(r["boss_id"], provider, r["chat_id"])


async def job(app_state: Any) -> None:
    registry = getattr(app_state, "channel_registry", None)
    if registry is None:
        return
    await reverify_once(app_state.db_pool, registry)
```

- [ ] **Step 4: Thêm `WEB_CAPS` để Web re-verify được**

`src/channels/capabilities.py`:
```python
WEB_CAPS: dict[str, Any] = {
    "inbound.supports_groups": True,
    "inbound.supports_mentions": True,
    "outbound.send_text": True,
    "member.list_api": "full",
    "auth.kind": "internal",
}

CAPABILITIES = {"zalo": ZALO_CAPS, "web": WEB_CAPS}
```

- [ ] **Step 5: Đăng ký job trong runner**

`src/scheduler/runner.py`: thêm import + wrapper + `add_job`:
```python
    from src.scheduler.jobs.group_membership_reverify import job as reverify_job
    async def _reverify() -> None:
        try:
            await reverify_job(app_state)
        except Exception:
            log.exception("group_membership_reverify job crashed")
    sched.add_job(_reverify, "interval", minutes=60, id="group_membership_reverify")
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/integration/test_group_reverify.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/scheduler/jobs/group_membership_reverify.py src/scheduler/runner.py src/channels/capabilities.py tests/integration/test_group_reverify.py
git commit -m "feat(scheduler): re-verify rời nhóm -> auto deactivate (gate qua capabilities)"
```

---

## Task 10: Nối UI handshake `/start <token>` (định danh acc chính)

**Files:**
- Modify: `src/web/routes/api_admin.py` (thêm endpoint mint token)
- Modify: `frontend/src/modules/admin/features/channels/api.ts` + `zalo-qr-dialog.tsx` (hiện bước handshake sau khi connect)
- Test: `tests/integration/test_api_channels_link_token.py`

- [ ] **Step 1: Write the failing test (backend endpoint)**

```python
# tests/integration/test_api_channels_link_token.py
import pytest


@pytest.mark.asyncio
async def test_link_token_endpoint_returns_token_for_connected_provider(
    clean_db, boss_client  # boss_client: fixture client đã auth (xem conftest/các test api hiện có)
):
    # giả định boss đã có bot_account_assignments active cho 'zalo'
    r = await boss_client.post("/api/v1/admin/channels/zalo/link-token")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["token"], str) and len(body["token"]) > 10
    assert body["bot_phone"]  # số/ë tên acc bot để hiển thị
```

> Nếu chưa có `boss_client` fixture, tái dùng pattern auth trong `tests/integration/test_api_channels_connect.py` (cùng cách tạo client + login boss).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_api_channels_link_token.py -v`
Expected: FAIL — endpoint chưa có.

- [ ] **Step 3: Thêm endpoint mint token**

Trong `src/web/routes/api_admin.py` (cùng router với các route `/admin/channels/...`):
```python
@router.post("/admin/channels/{provider}/link-token")
async def mint_link_token(provider: str, request: Request, ctx=Depends(boss_ctx)):
    pool = request.app.state.db_pool
    async with pool.acquire() as c:
        acc = await c.fetchrow(
            """
            SELECT ba.id, ba.provider_user_id, ba.display_name
            FROM bot_account_assignments baa
            JOIN bot_accounts ba ON ba.id = baa.bot_account_id
            WHERE baa.boss_id=$1 AND baa.provider=$2 AND baa.status='active'
            """,
            ctx.boss_id, provider,
        )
    if acc is None:
        raise HTTPException(status_code=409, detail=tr(ctx, vi="Chưa kết nối kênh này", en="Channel not connected"))
    from src.services.linking_service import LinkingService
    token = await LinkingService(pool).generate(ctx.boss_id, provider, acc["id"])
    return {"token": token, "bot_phone": acc["display_name"] or acc["provider_user_id"]}
```
(Theo đúng pattern `boss_ctx`/`tr(ctx, vi=, en=)`/`HTTPException` đang dùng trong file.)

- [ ] **Step 4: Run backend test**

Run: `pytest tests/integration/test_api_channels_link_token.py -v`
Expected: PASS.

- [ ] **Step 5: Frontend — hiện bước handshake sau khi QR connect xong**

- `frontend/src/modules/admin/features/channels/api.ts`: thêm
```ts
export const mintLinkToken = (provider: string) =>
  api<{ token: string; bot_phone: string }>(
    `/api/v1/admin/channels/${encodeURIComponent(provider)}/link-token`,
    { method: 'POST', body: JSON.stringify({}) },
  );
```
- `zalo-qr-dialog.tsx`: sau khi `status === 'success'`, gọi `mintLinkToken('zalo')` và hiển thị hướng dẫn: *"Mở Zalo bằng **tài khoản chính của anh**, nhắn `/start <token>` cho `<bot_phone>` để bot nhận diện anh."* (dùng `useT()` + class theme PageSection/Badge hiện có, không thêm style mới).

- [ ] **Step 6: Build frontend kiểm tra type**

Run: `cd frontend && npm run build`
Expected: build PASS (không lỗi TS).

- [ ] **Step 7: Commit**

```bash
git add src/web/routes/api_admin.py frontend/src/modules/admin/features/channels/ tests/integration/test_api_channels_link_token.py
git commit -m "feat(channels): handshake /start — endpoint mint token + bước hướng dẫn trên UI"
```

---

## Task 11: Quét regress + dọn tham chiếu cũ

**Files:**
- Modify: `tests/integration/test_linking_flow.py` (đang publish `inbound.raw.zalo`)
- Various: tìm tham chiếu sót `inbound.raw.`

- [ ] **Step 1: Cập nhật `test_linking_flow.py`**

Đổi mọi `bus.publish("inbound.raw.zalo", {...})` → publish `inbound.normalized` với `InboundMessage` (build từ field tương ứng), và đăng ký `InboundIngest(...).register()` thay vì `zalo normalizer`. Giữ assertion: handshake KHÔNG publish `message.captured`, account_links được tạo.

- [ ] **Step 2: Grep tham chiếu sót**

Run:
```bash
grep -rn "inbound.raw" src/ tests/ ; grep -rn "zalo.normalizer\|web.normalizer\|classify_thread_kind" src/ tests/
```
Expected: chỉ còn `classify_thread_kind` trong `ChannelAdapter` protocol + adapter (giữ cho fallback) và web cap; KHÔNG còn publish/subscribe `inbound.raw.*`.

- [ ] **Step 3: Chạy full suite**

Run: `pytest -q`
Expected: PASS toàn bộ (sửa các test còn đỏ theo cùng pattern envelope mới nếu phát sinh).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: migrate test còn lại sang inbound.normalized; xoá tham chiếu inbound.raw"
```

---

## Self-Review (đã chạy)

**Spec coverage:**
- §3.1 wrapper/envelope → Task 3,4,5,6,7. §3.2 group_notes registry → Task 2,3. §3.3 group gate → Task 3.
  §3.4 DM + handshake → Task 3. §3.5 handshake UI → Task 10. §3.6 schema → Task 1. §3.7 wiring → Task 5.
  §3.8 re-verify → Task 9. §4 vá kèm (thread_kind Task 8, dedup Task 3, is_group_active Task 2/3).
  §5 scope (Zalo+Web migrate Task 6,7; test/admin-inject Task 7,11). ✓ không gap.
- **Type consistency:** `InboundMessage` (base.py) dùng nhất quán; `ensure_tracked/bosses_tracking/mark_left`
  ký hiệu khớp giữa Task 2/3/9; `send(..., chat_type=)` khớp Task 8 ↔ responders.
- **Placeholder:** không có TBD/TODO; mọi step có code/command thật.

## Execution Handoff

Chọn cách thực thi ở tin nhắn kế.
