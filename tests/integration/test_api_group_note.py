"""Tests for group note web API + artifact collector."""
from __future__ import annotations

import asyncio

from src.web.security import CSRF_COOKIE

CSRF = "test-csrf-note"


def _csrf(client):
    client.cookies.set(CSRF_COOKIE, CSRF)
    return {"X-CSRF-Token": CSRF}


def test_get_note(client, logged_in_boss, seed_group_owned_by_boss):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/note")
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert "template_id" in body
    assert isinstance(body["manually_edited_sections"], list)


def test_edit_note_creates_version(client, logged_in_boss, seed_group_owned_by_boss):
    gid = seed_group_owned_by_boss.id
    r = client.patch(
        f"/api/v1/admin/groups/{gid}/note",
        json={"content": "# Note mới\n- mục 1"},
        headers=_csrf(client),
    )
    assert r.status_code == 200

    r2 = client.get(f"/api/v1/admin/groups/{gid}/note")
    assert r2.json()["content"] == "# Note mới\n- mục 1"

    r3 = client.get(f"/api/v1/admin/groups/{gid}/note/versions")
    assert r3.status_code == 200
    versions = r3.json()
    assert len(versions) >= 1
    assert versions[0]["emitted_by"] == "boss_web"


def test_restore_version(client, logged_in_boss, seed_group_owned_by_boss):
    gid = seed_group_owned_by_boss.id
    headers = _csrf(client)
    client.patch(f"/api/v1/admin/groups/{gid}/note", json={"content": "ban dau"}, headers=headers)
    client.patch(f"/api/v1/admin/groups/{gid}/note", json={"content": "da sua"}, headers=headers)

    versions = client.get(f"/api/v1/admin/groups/{gid}/note/versions").json()
    first = versions[-1]  # oldest
    r = client.post(
        f"/api/v1/admin/groups/{gid}/note/versions/{first['id']}/restore",
        headers=headers,
    )
    assert r.status_code == 200
    assert client.get(f"/api/v1/admin/groups/{gid}/note").json()["content"] == "ban dau"


def test_note_other_boss_403(client, logged_in_boss, seed_group_owned_by_other):
    r = client.get(f"/api/v1/admin/groups/{seed_group_owned_by_other.id}/note")
    assert r.status_code in (403, 404)


def test_note_templates_listing(client, logged_in_boss):
    r = client.get("/api/v1/admin/note-templates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_refresh_note_publishes(client, logged_in_boss, seed_group_owned_by_boss):
    r = client.post(
        f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/note/refresh",
        headers=_csrf(client),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_artifact_collector_extracts_links(client, logged_in_boss, seed_group_owned_by_boss, clean_db):
    """message.captured với text chứa URL → group_artifacts có row 'link'."""

    async def _run():
        from src.events.bus import InMemoryEventBus
        from src.services.artifact_collector import register

        bus = InMemoryEventBus()
        register(bus, clean_db)

        async with clean_db.acquire() as c:
            msg_id = await c.fetchval(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type, sender_name, text, ts)
                VALUES ($1, 'zalo', 'zalo-group-test-001', 'group', 'Anh A',
                        'xem tài liệu https://docs.example.com/spec.pdf nhé', NOW())
                RETURNING id
                """,
                logged_in_boss.boss_id,
            )
        await bus.publish(
            "message.captured",
            {
                "message_id": msg_id,
                "boss_id": logged_in_boss.boss_id,
                "provider": "zalo",
                "chat_id": "zalo-group-test-001",
                "chat_type": "group",
                "mentions_bot": False,
                "sender_is_boss": False,
                "text": "xem tài liệu https://docs.example.com/spec.pdf nhé",
                "bot_account_id": None,
            },
        )
        async with clean_db.acquire() as c:
            return await c.fetch(
                "SELECT kind, url FROM group_artifacts WHERE group_id=$1",
                seed_group_owned_by_boss.id,
            )

    rows = asyncio.get_event_loop().run_until_complete(_run())
    assert any(
        r["kind"] == "link" and "docs.example.com" in r["url"] for r in rows
    )
