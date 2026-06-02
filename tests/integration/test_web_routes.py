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
