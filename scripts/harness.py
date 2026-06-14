#!/usr/bin/env python3
"""Knowledge spine live harness. Drives /test/api/* + inspects DB.

Commands:
  setup            create boss+employees+group, upgrade boss (pro plan + all tools),
                   send the scripted work conversation. Saves ids to STATE.
  convo            (re)send the scripted conversation into the existing group.
  extract          fire knowledge_extract NOW (reset cursor) then dump knowledge.
  wipe-knowledge   hard-delete knowledge rows for the boss (clean extraction test).
  dump             print knowledge_items for the boss.
  ask "<q>"        boss asks (mention_bot) in group; prints bot reply.
  teardown         delete the test group + its messages/knowledge.
"""
import asyncio
import json
import sys
import urllib.request

import asyncpg

BASE = "http://localhost:8000/test"
DSN = "postgresql://smart:smart@localhost:5433/smart_bot"
STATE = "/tmp/harness_state.json"

TOOLS = [
    "cancel_reminder", "count_messages", "current_time", "edit_group_note",
    "fetch_url", "find_exact_quote", "forget", "list_action_items", "list_groups",
    "list_reminders", "mark_action_item", "pin_message", "read_group_note",
    "refresh_group_note", "remember", "search_history", "search_knowledge",
    "set_reminder", "unpin_message",
]

# Realistic VN work conversation for "Dự án Apollo" (app đặt lịch phòng khám).
# boss speaks FIRST (establishes group tracking), then the team.
CONVO = [
    ("boss", "Chào team, mình khởi động dự án Apollo nhé — app đặt lịch khám cho phòng khám. Mọi người nhận phần việc đi."),
    ("an",   "Em An nhận phần backend, dùng FastAPI. Em estimate xong khung API trong 2 tuần."),
    ("binh", "Em Bình làm UI/UX. Wireframe em xong trước thứ 6 tuần này, đẩy lên Figma."),
    ("chau", "Em Châu lo testing kiêm PM, theo dõi tiến độ. Em set up bảng Jira cho cả team."),
    ("boss", "Ok rõ ràng. Deadline tổng cho bản demo là 30/6 nhé, không lùi."),
    ("an",   "Database mình chốt dùng PostgreSQL cho chắc nha mọi người."),
    ("binh", "Màu chủ đạo em đề xuất xanh dương, tông y tế cho dễ tin tưởng."),
    ("chau", "Trưa nay ăn gì mọi người ơi, đói quá 😄"),
    ("an",   "Mọi người nhớ review giúp em mấy cái PR nha."),
    ("boss", "À khoan, database đổi sang Supabase cho nhanh, khỏi tự host Postgres. Chốt Supabase."),
    ("chau", "Lưu ý rủi ro: cổng thanh toán VNPay chưa có sandbox cho mình test, có thể trễ phần thanh toán."),
    ("binh", "Wireframe em làm xong rồi nhé, đã đẩy hết lên Figma."),
    ("an",   "Deadline backend em xin dời thành 10/7 vì phải thêm phần tích hợp thanh toán."),
]


def _post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode() or "{}")


def _get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode() or "[]")


def _load():
    with open(STATE) as f:
        return json.load(f)


def _save(s):
    with open(STATE, "w") as f:
        json.dump(s, f, indent=2)


async def _boss_id(conn, boss_web_uid):
    return await conn.fetchval(
        "SELECT boss_user_id FROM web_users WHERE id=$1", boss_web_uid)


async def setup():
    boss = _post("/api/users", {"name": "Sếp Minh", "role": "boss"})["id"]
    emps = {n: _post("/api/users", {"name": nm, "role": "employee"})["id"]
            for n, nm in [("an", "An"), ("binh", "Bình"), ("chau", "Châu")]}
    members = [boss] + list(emps.values())
    gid = _post("/api/groups", {"name": "Dự án Apollo", "member_ids": members})["id"]
    state = {"boss": boss, "emps": emps, "gid": gid}
    _save(state)

    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, boss)
    await conn.execute(
        "UPDATE users SET plan_id=(SELECT id FROM plans WHERE name='pro') WHERE id=$1", bid)
    await conn.executemany(
        "INSERT INTO boss_active_tools(boss_id, tool_name) VALUES($1,$2) ON CONFLICT DO NOTHING",
        [(bid, t) for t in TOOLS])
    await conn.close()
    print(f"boss web_uid={boss} boss_id={bid} gid={gid} emps={emps}")
    await convo()


async def convo():
    s = _load()
    who = {"boss": s["boss"], **s["emps"]}
    for role, text in CONVO:
        _post("/api/send", {"as": who[role], "chat_id": s["gid"], "text": text})
    print(f"sent {len(CONVO)} messages into gid={s['gid']}")


async def wipe_knowledge():
    s = _load()
    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, s["boss"])
    n = await conn.fetchval("SELECT count(*) FROM knowledge_items WHERE boss_id=$1", bid)
    await conn.execute(
        "DELETE FROM knowledge_provenance WHERE knowledge_item_id IN "
        "(SELECT id FROM knowledge_items WHERE boss_id=$1)", bid)
    await conn.execute(
        "DELETE FROM knowledge_revisions WHERE knowledge_item_id IN "
        "(SELECT id FROM knowledge_items WHERE boss_id=$1)", bid)
    await conn.execute("DELETE FROM knowledge_items WHERE boss_id=$1", bid)
    await conn.close()
    # Also purge Qdrant points (repo soft_delete does this in prod; hard-wipe must too,
    # else orphan vectors dominate dense top-k and starve live items from hybrid results).
    from qdrant_client import models
    from src.infra.qdrant import create_qdrant
    q = create_qdrant()
    await q.delete(
        collection_name="smart_bot",
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="boss_id", match=models.MatchValue(value=bid)),
            models.FieldCondition(key="kind", match=models.MatchValue(value="knowledge")),
        ])),
    )
    print(f"wiped {n} knowledge_items + qdrant points for boss_id={bid}")


async def dump():
    s = _load()
    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, s["boss"])
    rows = await conn.fetch(
        "SELECT id, kind, title, content, importance, confidence, status "
        "FROM knowledge_items WHERE boss_id=$1 ORDER BY id", bid)
    print(f"\n=== knowledge_items (boss_id={bid}) : {len(rows)} ===")
    for r in rows:
        prov = await conn.fetch(
            "SELECT message_id FROM knowledge_provenance WHERE knowledge_item_id=$1", r["id"])
        pid = [p["message_id"] for p in prov]
        print(f"[{r['id']}] {r['kind']:8} imp={r['importance']} conf={r['confidence']} "
              f"{r['status']:8} src={pid}\n     {r['title']}\n     {r['content']}")
    await conn.close()


async def extract():
    s = _load()
    print(_post("/api/extract", {"chat_id": s["gid"], "reset": True}))
    await dump()


async def ask(q):
    s = _load()
    gid = s["gid"]
    before = _get(f"/api/chats/{gid}/messages?limit=100")
    n_out = sum(1 for m in before if m["kind"] == "out")
    _post("/api/send", {"as": s["boss"], "chat_id": gid, "text": q, "mention_bot": True})
    after = _get(f"/api/chats/{gid}/messages?limit=100")
    new_out = [m for m in after if m["kind"] == "out"][n_out:]
    print(f"\nQ: {q}")
    for m in new_out:
        print(f"BOT: {m['text']}")
    if not new_out:
        print("BOT: (no reply)")


async def teardown():
    s = _load()
    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, s["boss"])
    await conn.execute(
        "DELETE FROM knowledge_provenance WHERE knowledge_item_id IN (SELECT id FROM knowledge_items WHERE boss_id=$1)", bid)
    await conn.execute(
        "DELETE FROM knowledge_revisions WHERE knowledge_item_id IN (SELECT id FROM knowledge_items WHERE boss_id=$1)", bid)
    await conn.execute("DELETE FROM knowledge_items WHERE boss_id=$1", bid)
    await conn.close()
    _post(f"/api/groups/{s['gid']}", {}) if False else None
    print("knowledge wiped; group left intact")


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if cmd == "setup":
        await setup()
    elif cmd == "convo":
        await convo()
    elif cmd == "extract":
        await extract()
    elif cmd == "wipe-knowledge":
        await wipe_knowledge()
    elif cmd == "dump":
        await dump()
    elif cmd == "ask":
        await ask(sys.argv[2])
    elif cmd == "teardown":
        await teardown()
    else:
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
