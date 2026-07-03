"""Legal docs (ToS/Privacy version+acceptance) + PDPL opt-out cá nhân +
boss consent gate (spec 2026-07-02-legal-consent-design).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.channels.base import InboundMessage
from src.channels.ingest import InboundIngest
from src.events.bus import InMemoryEventBus
from src.web.security import CSRF_COOKIE

CSRF = "csrf-legal"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def _seed_doc(clean_db, kind="terms", version=1):
    async def _():
        async with clean_db.acquire() as c:
            await c.execute(
                "UPDATE legal_documents SET is_active=FALSE WHERE kind=$1", kind)
            await c.execute(
                "INSERT INTO legal_documents (kind, version, content_md) VALUES ($1,$2,$3) "
                "ON CONFLICT (kind, version) DO UPDATE SET is_active=TRUE",
                kind, version, f"# {kind} v{version}")
    asyncio.get_event_loop().run_until_complete(_())


# ---- public đọc + acceptance flow ------------------------------------------


def test_public_legal_document(client, clean_db):
    _seed_doc(clean_db, "privacy", 1)
    r = client.get("/api/v1/legal/privacy")
    assert r.status_code == 200
    assert r.json()["content_md"] == "# privacy v1"
    assert client.get("/api/v1/legal/nope").status_code == 404


def test_acceptance_flow_and_republish(client, logged_in_boss, clean_db):
    _seed_doc(clean_db, "terms", 1)
    r = client.get("/api/v1/legal/acceptance-status")
    assert r.json()["needs_acceptance"] is True

    r = client.post("/api/v1/legal/accept", json={}, headers=_csrf(client))
    assert "terms" in r.json()["accepted"]
    assert client.get("/api/v1/legal/acceptance-status").json()["needs_acceptance"] is False

    # publish bản mới → phải chấp nhận lại
    _seed_doc(clean_db, "terms", 2)
    assert client.get("/api/v1/legal/acceptance-status").json()["needs_acceptance"] is True


def test_superadmin_publish_new_version(client, logged_in_superadmin, clean_db):
    r = client.post(
        "/api/v1/superadmin/legal/terms",
        json={"content_md": "# terms mới"},
        headers=_csrf(client),
    )
    assert r.status_code == 200
    v1 = r.json()["version"]
    r2 = client.post(
        "/api/v1/superadmin/legal/terms",
        json={"content_md": "# terms mới hơn"},
        headers=_csrf(client),
    )
    assert r2.json()["version"] == v1 + 1
    docs = client.get("/api/v1/superadmin/legal").json()
    active = [d for d in docs if d["kind"] == "terms" and d["is_active"]]
    assert len(active) == 1 and active[0]["version"] == v1 + 1


# ---- opt-out cá nhân --------------------------------------------------------


def _msg(**kw):
    base = dict(
        bot_account_id=0, provider="zalo", chat_id="g-opt", chat_type="group",
        provider_msg_id="m1", sender_provider_id="U_BOSS", sender_name="Boss",
        text="chào team", mentions_bot=False, reply_to_provider_msg_id=None,
        media_kind="text", media_url=None, ts=datetime.now(tz=timezone.utc),
    )
    base.update(kw)
    return InboundMessage(**base)


async def _zalo_rig(pool):
    async with pool.acquire() as c:
        acc = await c.fetchval(
            "INSERT INTO bot_accounts (provider, provider_user_id, account_kind, ownership) "
            "VALUES ('zalo', 'opt-bot', 'personal', 'platform') RETURNING id")
        boss = await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ('opt@x.test','Sếp','boss') RETURNING id")
        await c.execute(
            "INSERT INTO account_links (boss_id, provider, provider_user_id) VALUES ($1,'zalo','U_BOSS')",
            boss)
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id, "
            "assignment_kind, status) VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
    return acc, boss


@pytest.mark.asyncio
async def test_opt_out_tool_then_ingest_skips_sender(clean_db):
    acc, boss = await _zalo_rig(clean_db)
    bus = InMemoryEventBus()
    InboundIngest(clean_db, bus).register()
    captured: list = []

    async def on_cap(p):
        captured.append(p)

    bus.subscribe("message.captured", on_cap)

    # boss nói → track; An nói → captured bình thường (kèm sender trong payload)
    await bus.publish("inbound.normalized", {"message": _msg(bot_account_id=acc)})
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m2", sender_provider_id="U_AN",
        sender_name="An", text="em nhận backend")})
    assert len(captured) == 2
    assert captured[1]["sender_provider_id"] == "U_AN"

    # An opt-out qua tool (như responder sẽ gọi)
    from src.tools.core.privacy import opt_out_capture

    ctx = SimpleNamespace(pool=clean_db, provider="zalo",
                          sender_provider_id="U_AN", sender_name="An")
    out = await opt_out_capture(ctx)
    assert out.content["opted_out"] is True

    # tin sau của An bị bỏ qua; người khác vẫn captured
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m3", sender_provider_id="U_AN",
        sender_name="An", text="tin này không được ghi")})
    await bus.publish("inbound.normalized", {"message": _msg(
        bot_account_id=acc, provider_msg_id="m4", sender_provider_id="U_BINH",
        sender_name="Bình", text="tin của Bình vẫn ghi")})
    texts = [p["text"] for p in captured]
    assert "tin này không được ghi" not in texts
    assert "tin của Bình vẫn ghi" in texts

    # idempotent
    out2 = await opt_out_capture(ctx)
    assert out2.content["opted_out"] is True


# ---- boss consent gate (qr-login lần đầu) -----------------------------------


def test_qr_login_requires_consent_first_time(client, logged_in_boss, clean_db):
    r = client.post("/api/v1/admin/channels/zalo/qr-login", json={}, headers=_csrf(client))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "consent_required"

    r = client.post(
        "/api/v1/admin/channels/zalo/qr-login",
        json={"consent_confirmed": True},
        headers=_csrf(client),
    )
    assert r.status_code == 200  # gate qua (session error vì thiếu node deps là chuyện khác)

    # lần sau không cần gửi lại cờ
    r = client.post("/api/v1/admin/channels/zalo/qr-login", json={}, headers=_csrf(client))
    assert r.status_code == 200
