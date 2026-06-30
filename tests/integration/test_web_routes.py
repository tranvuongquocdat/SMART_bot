import pytest
from fastapi.testclient import TestClient

from src import main as main_mod


@pytest.fixture
def client(clean_db):
    with TestClient(main_mod.app) as c:
        yield c


def test_create_and_list_users(client, clean_db):
    r = client.post(
        "/test/api/users",
        json={"name": "Boss A", "role": "boss"},
    )
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert uid.startswith("u-")

    r2 = client.get("/test/api/users")
    assert any(u["id"] == uid for u in r2.json())


def test_create_group_with_members(client, clean_db):
    u1 = client.post("/test/api/users", json={"name": "A", "role": "boss"}).json()["id"]
    u2 = client.post("/test/api/users", json={"name": "B", "role": "employee"}).json()["id"]
    r = client.post(
        "/test/api/groups",
        json={"name": "team", "member_ids": [u1, u2]},
    )
    assert r.status_code == 200
    gid = r.json()["id"]
    members = client.get("/test/api/groups").json()
    assert any(g["id"] == gid for g in members)


def test_delete_user_cascade(client, clean_db):
    u1 = client.post("/test/api/users", json={"name": "A", "role": "employee"}).json()["id"]
    client.post(
        "/test/api/groups", json={"name": "g", "member_ids": [u1]}
    )
    r = client.delete(f"/test/api/users/{u1}")
    assert r.status_code == 204
    # Group still exists but membership cleared
    members = client.get(f"/test/api/chats?as={u1}").json()
    assert members == []


def test_send_publishes_inbound_event_and_replay_returns_messages(
    client, clean_db
):
    # Setup: boss + DM
    uid = client.post(
        "/test/api/users", json={"name": "Boss", "role": "boss"}
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
