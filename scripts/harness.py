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
  zalo             e2e kênh Zalo trên fake bridge: tự spawn server (cổng 24815),
                   seed acc+boss, bơm hội thoại, extract, Q&A, reminder người
                   chưa onboard — không cần acc Zalo thật.
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

# Kịch bản hội thoại TỰ ĐỦ + TÁI LẬP (wipe→setup→extract cho ra state đã biết).
# Bao gồm: phân công, đổi quyết định (reconcile UPDATE), risk rồi resolved (DELETE),
# hoàn thành, dời deadline, việc TRỄ HẠN (để test suy luận thời gian), + nhiễu.
# boss nói TRƯỚC (thiết lập group tracking), rồi team.
APOLLO_CONVO = [
    ("boss", "Chào team, mình khởi động dự án Apollo nhé — app đặt lịch khám cho phòng khám. Mọi người nhận phần việc đi."),
    ("an",   "Em An nhận phần backend, dùng FastAPI. Em estimate xong khung API trong 2 tuần."),
    ("binh", "Em Bình làm UI/UX, lo phần wireframe rồi đẩy lên Figma."),
    ("chau", "Em Châu lo testing kiêm PM, theo dõi tiến độ. Em set up bảng Jira cho cả team."),
    ("boss", "Ok rõ ràng. Deadline bản demo là 30/6 nhé."),
    ("an",   "Database mình chốt dùng PostgreSQL cho chắc nha mọi người."),
    ("binh", "Màu chủ đạo em đề xuất xanh dương, tông y tế cho dễ tin tưởng."),
    ("chau", "Trưa nay ăn gì mọi người ơi, đói quá 😄"),
    ("an",   "Mọi người nhớ review giúp em mấy cái PR nha."),
    ("boss", "À khoan, database đổi sang Supabase cho nhanh, khỏi tự host Postgres. Chốt Supabase nhé."),
    ("chau", "Lưu ý rủi ro: cổng thanh toán VNPay chưa có sandbox cho mình test, có thể trễ phần thanh toán."),
    ("binh", "Wireframe em làm xong rồi nhé, đã đẩy hết lên Figma."),
    ("an",   "Deadline backend em xin dời thành 10/7 vì phải thêm phần tích hợp thanh toán."),
    ("boss", "Vì thêm phần thanh toán nên anh dời luôn deadline bản demo từ 30/6 sang 15/7 nhé."),
    ("chau", "Update nhé mọi người: VNPay đã mở sandbox rồi, phần thanh toán hết rủi ro, test được bình thường."),
    ("boss", "À Châu, bản báo cáo tiến độ hạn 10/6 anh vẫn chưa nhận được, em gửi gấp giúp anh nhé."),
]

# Dự án thứ 2 — để test scope đa nhóm + tổng hợp chéo (DM). CÙNG team, khác việc.
BETA_CONVO = [
    ("boss", "Team ơi mở thêm dự án Beta — cổng thanh toán nội bộ cho công ty. Phân việc nhé."),
    ("binh", "Em Bình nhận backend cho Beta, dùng Django."),
    ("chau", "Em Châu làm frontend cho Beta."),
    ("an",   "Em An hỗ trợ phần tích hợp ngân hàng cho Beta."),
    ("boss", "Deadline demo Beta mình chốt 20/8 nhé."),
]

# Kịch bản 2-PASS cho reconcile cross-batch (RESOLVE/UPDATE/DELETE). Pass 1 thiết lập
# trạng thái, Pass 2 (extract incremental) đính chính/giải quyết/đổi quyết định.
MP_P1 = [
    ("boss", "Team mở dự án Orion — hệ thống quản lý kho. Phân việc nhé."),
    ("an",   "Em An nhận backend Orion, dùng FastAPI."),
    ("chau", "Lưu ý rủi ro: license phần mềm quét mã vạch chưa mua, có thể chặn phần nhập kho."),
    ("boss", "Deadline bản demo Orion là 30/6 nhé."),
    ("an",   "Em sẽ làm phần rà soát bảo mật cho hệ thống trước khi demo."),
    ("boss", "Hosting mình chốt dùng AWS nhé."),
]
MP_P2 = [
    ("chau", "Update: đã mua license quét mã vạch rồi, phần nhập kho hết vướng nha."),
    ("boss", "Anh dời deadline demo Orion sang 20/7 nhé, cần thêm thời gian."),
    ("an",   "Em rà soát bảo mật xong rồi nhé sếp, không có lỗ hổng nghiêm trọng."),
    ("boss", "Thôi đổi ý, không dùng AWS nữa, mình chuyển sang Vercel cho gọn."),
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
    beta = _post("/api/groups", {"name": "Dự án Beta", "member_ids": members})["id"]
    state = {"boss": boss, "emps": emps, "gid": gid, "beta": beta}
    _save(state)

    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, boss)
    await conn.execute(
        "UPDATE users SET plan_id=(SELECT id FROM plans WHERE name='pro') WHERE id=$1", bid)
    await conn.executemany(
        "INSERT INTO boss_active_tools(boss_id, tool_name) VALUES($1,$2) ON CONFLICT DO NOTHING",
        [(bid, t) for t in TOOLS])
    await conn.close()
    print(f"boss web_uid={boss} boss_id={bid} apollo={gid} beta={beta} emps={emps}")
    await convo()


def _wait_ingested(gid, n_expected, tries=40):
    """Ingest 'inbound.normalized' chạy bất đồng bộ — poll tới khi đủ tin đã LƯU.
    Không chờ là extract chạy trên window THIẾU (race) → trích sót."""
    import time
    for _ in range(tries):
        msgs = _get(f"/api/chats/{gid}/messages?limit=200")
        if sum(1 for m in msgs if m.get("kind") == "in") >= n_expected:
            return True
        time.sleep(0.25)
    return False


async def convo():
    s = _load()
    who = {"boss": s["boss"], **s["emps"]}
    for role, text in APOLLO_CONVO:
        _post("/api/send", {"as": who[role], "chat_id": s["gid"], "text": text})
    for role, text in BETA_CONVO:
        _post("/api/send", {"as": who[role], "chat_id": s["beta"], "text": text})
    ok_a = _wait_ingested(s["gid"], len(APOLLO_CONVO))
    ok_b = _wait_ingested(s["beta"], len(BETA_CONVO))
    print(f"sent {len(APOLLO_CONVO)} apollo + {len(BETA_CONVO)} beta messages; "
          f"ingested apollo={ok_a} beta={ok_b} (apollo={s['gid']} beta={s['beta']})")


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
    print("apollo:", _post("/api/extract", {"chat_id": s["gid"], "reset": True}))
    if s.get("beta"):
        print("beta:  ", _post("/api/extract", {"chat_id": s["beta"], "reset": True}))
    await dump()


_QUICK_ACK = "Để em xem..."  # filler ack — bỏ qua khi đánh giá nội dung trả lời


def _expand_token(t):
    """Mở rộng token động trong must_include để assert thời gian không bị 'hết hạn'.

    {days_until:YYYY-MM-DD} → số ngày từ HÔM NAY tới ngày đó (vd hôm nay 15/6, ngày
    15/7 → '30'). Nhờ vậy case time-arithmetic luôn đúng dù chạy ngày nào."""
    import datetime as _dt
    import re
    m = re.fullmatch(r"\{days_until:(\d{4})-(\d{2})-(\d{2})\}", t)
    if not m:
        return t
    y, mo, d = (int(x) for x in m.groups())
    delta = (_dt.date(y, mo, d) - _dt.date.today()).days
    return str(delta)


def _norm_dates(text):
    """Chuẩn hoá ngày về 'D/M' (bỏ số 0 đầu + bỏ năm) để assert không phụ thuộc định dạng:
    '20/07/2026', '20/07', '20/7' → '20/7'. Bot có thể trả ngày kiểu nào cũng khớp."""
    import re
    return re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b",
                  lambda m: f"{int(m.group(1))}/{int(m.group(2))}", text)


def _token_missing(t, answer):
    """Token có chữ HOA (tên riêng: An, Bình, Supabase…) → khớp phân biệt hoa/thường để
    tránh false-positive với từ thường (vd 'an' trong 'thanh toán'); còn lại không phân biệt.
    Ngày tháng được chuẩn hoá 2 phía để '20/7' khớp cả '20/07/2026'."""
    t, answer = _norm_dates(t), _norm_dates(answer)
    if any(ch.isupper() for ch in t):
        return t not in answer
    return t.lower() not in answer.lower()


def _gid_for(s, ask_in):
    """ask_in: 'apollo' (mặc định) | 'beta' | 'dm' → chat id tương ứng.

    'dm' = DM sếp↔bot (chat_id 'dm:<boss>') → scope = MỌI nhóm (tổng hợp chéo); đây
    cũng là đường Pha B (sếp hỏi workload ở web admin)."""
    if ask_in in (None, "apollo"):
        return s["gid"]
    if ask_in == "beta":
        return s["beta"]
    if ask_in == "dm":
        return f"dm:{s['boss']}"
    return ask_in  # cho phép truyền thẳng group id


def _ask_capture(s, gid, q):
    """Gửi câu hỏi (mention bot) vào nhóm gid, trả list text MỚI của bot (bỏ quick-ack).

    Diff theo ID tin bot (out) — KHÔNG đếm-rồi-cắt: nhóm tích luỹ >100 tin (chạy gold
    nhiều lần) làm cửa sổ limit lệch → đếm sai → tưởng '(no reply)'. ID đơn điệu nên
    tin mới luôn nằm trong cửa sổ mới nhất và không trùng id cũ."""
    before = _get(f"/api/chats/{gid}/messages?limit=200")
    seen = {m["id"] for m in before if m.get("kind") == "out"}
    _post("/api/send", {"as": s["boss"], "chat_id": gid, "text": q, "mention_bot": True})
    after = _get(f"/api/chats/{gid}/messages?limit=200")
    new_out = [m["text"] for m in after if m.get("kind") == "out" and m["id"] not in seen]
    return [t for t in new_out if t and t.strip() != _QUICK_ACK]


async def ask(q):
    s = _load()
    gid = s["gid"]
    print(f"\nQ: {q}")
    replies = _ask_capture(s, gid, q)
    for t in replies:
        print(f"BOT: {t}")
    if not replies:
        print("BOT: (no reply)")


async def gold(path="scripts/gold_cases.json"):
    """Chạy gold-set: mỗi case post câu hỏi + assert must_include / must_exclude.

    must_include: khớp không phân biệt hoa/thường (mọi token PHẢI có).
    must_exclude: khớp PHÂN BIỆT hoa/thường (không token nào được xuất hiện).
    """
    s = _load()
    with open(path) as f:
        spec = json.load(f)
    cases = spec["cases"]
    passed = failed = 0
    fails = []
    for c in cases:
        gid = _gid_for(s, c.get("ask_in"))
        answer = "\n".join(_ask_capture(s, gid, c["q"]))
        inc = [_expand_token(t) for t in c.get("must_include", [])]
        miss = [t for t in inc if _token_missing(t, answer)]
        leak = [t for t in c.get("must_exclude", []) if t in answer]
        ok = not miss and not leak and bool(answer.strip())
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {c['id']:28} ({c.get('ask_in','apollo')})  {c['q']}")
        if ok:
            passed += 1
        else:
            failed += 1
            detail = []
            if not answer.strip():
                detail.append("EMPTY reply")
            if miss:
                detail.append(f"missing={miss}")
            if leak:
                detail.append(f"leaked={leak}")
            fails.append((c["id"], "; ".join(detail), answer))
    print(f"\n=== gold: {passed} passed, {failed} failed / {len(cases)} ===")
    for cid, detail, answer in fails:
        print(f"\n--- FAIL {cid}: {detail}\n    note: "
              f"{next(c.get('note','') for c in cases if c['id']==cid)}\n    BOT: {answer}")
    sys.exit(1 if failed else 0)


async def multipass():
    """Regression cross-batch reconcile: tạo nhóm Orion mới, gửi Pass1→extract→Pass2→
    extract incremental, rồi assert RESOLVE/UPDATE/DELETE ở DB + câu trả lời."""
    boss = _post("/api/users", {"name": "Sếp Orion", "role": "boss"})["id"]
    emps = {n: _post("/api/users", {"name": nm, "role": "employee"})["id"]
            for n, nm in [("an", "An"), ("chau", "Châu")]}
    gid = _post("/api/groups",
                {"name": "Dự án Orion", "member_ids": [boss] + list(emps.values())})["id"]
    s = {"boss": boss, "emps": emps, "gid": gid}
    who = {"boss": boss, **emps}
    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, boss)
    await conn.close()

    for r, t in MP_P1:
        _post("/api/send", {"as": who[r], "chat_id": gid, "text": t})
    _wait_ingested(gid, len(MP_P1))
    _post("/api/extract", {"chat_id": gid, "reset": True})
    for r, t in MP_P2:
        _post("/api/send", {"as": who[r], "chat_id": gid, "text": t})
    _wait_ingested(gid, len(MP_P1) + len(MP_P2))
    _post("/api/extract", {"chat_id": gid, "reset": False})

    conn = await asyncpg.connect(DSN)
    rows = await conn.fetch(
        "SELECT kind, status, content FROM knowledge_items WHERE boss_id=$1", bid)
    await conn.close()
    checks, fails = [], []

    def chk(name, ok, detail=""):
        checks.append(name)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{'' if ok else '  '+detail}")
        if not ok:
            fails.append(name)

    # Outcome (không ràng buộc cơ chế): license phải được hệ thống coi là ĐÃ ĐÓNG — hoặc risk
    # status='resolved' (cơ chế ưu tiên), hoặc có item ghi nhận đã giải quyết. Cross-batch reconcile
    # non-deterministic giữa RESOLVE vs ADD-fact; câu trả lời (assert Q&A bên dưới) mới là cổng chính.
    lic = [r for r in rows if "license" in (r["content"] or "").lower()]
    closed = any(
        r["status"] == "resolved"
        or any(k in (r["content"] or "").lower()
               for k in ["đã mua", "đã xử lý", "hết vướng", "đã đóng"])
        for r in lic
    )
    chk("DB: license đã đóng (resolved hoặc có ghi nhận giải quyết)",
        bool(lic) and closed, str([(r["kind"], r["status"]) for r in lic]))
    hosting = [r for r in rows if "vercel" in (r["content"] or "").lower()
               and r["status"] in ("active", "resolved")]
    aws_active = [r for r in rows if "aws" in (r["content"] or "").lower()
                  and "vercel" not in (r["content"] or "").lower() and r["status"] == "active"]
    chk("DB: hosting -> Vercel (AWS không còn active)",
        bool(hosting) and not aws_active, f"hosting={bool(hosting)} aws_active={len(aws_active)}")

    qa = [
        ("Còn rủi ro license quét mã vạch không?", ["không"], []),
        ("Deadline demo Orion là ngày nào?", ["20/7"], []),
        ("Phần rà soát bảo mật xong chưa?", ["xong"], []),
        # "không dùng AWS nữa" là câu đúng → KHÔNG exclude AWS; chỉ cần khẳng định Vercel.
        ("Hosting dùng gì?", ["Vercel"], []),
    ]
    for q, inc, exc in qa:
        ans = "\n".join(_ask_capture(s, gid, q))
        miss = [t for t in inc if _token_missing(t, ans)]
        leak = [t for t in exc if t in ans]
        chk(f"Q: {q}", not miss and not leak and bool(ans.strip()),
            f"missing={miss} leaked={leak} :: {ans[:90]}")

    print(f"\n=== multipass: {len(checks)-len(fails)}/{len(checks)} PASS (gid={gid}) ===")
    sys.exit(1 if fails else 0)


async def workload():
    """Regression Pha B: seed knowledge_items có cấu trúc (assignee/due/status) — SPINE là
    nguồn workload — rồi assert workload_summary (DB) + câu trả lời AI ('ai quá tải', 'trễ hạn').
    open=status'active', done=status'resolved', overdue=active & due_at<now. Item không có
    assignee = KHÔNG tính (test bucket bỏ qua)."""
    import datetime as _dt
    boss = _post("/api/users", {"name": "Sếp WL", "role": "boss"})["id"]
    emps = {n: _post("/api/users", {"name": nm, "role": "employee"})["id"]
            for n, nm in [("an", "An"), ("binh", "Bình"), ("chau", "Châu")]}
    gid = _post("/api/groups",
                {"name": "Team Sao Hỏa", "member_ids": [boss] + list(emps.values())})["id"]
    conn = await asyncpg.connect(DSN)
    bid = await _boss_id(conn, boss)
    now = _dt.datetime.now(_dt.timezone.utc)
    past, fut = now - _dt.timedelta(days=3), now + _dt.timedelta(days=5)
    seed = [  # (assignee, due, status) — An:3open/1qh/2done · Bình:1open/3done · Châu:4open/2qh · 1 vô chủ
        ("An", past, "active"), ("An", fut, "active"), ("An", fut, "active"),
        ("An", None, "resolved"), ("An", None, "resolved"),
        ("Bình", fut, "active"), ("Bình", None, "resolved"), ("Bình", None, "resolved"),
        ("Bình", None, "resolved"),
        ("Châu", past, "active"), ("Châu", past, "active"), ("Châu", fut, "active"),
        ("Châu", fut, "active"),
        (None, fut, "active"),  # vô chủ → workload bỏ qua
    ]
    for i, (a, due, st) in enumerate(seed):
        await conn.execute(
            "INSERT INTO knowledge_items(boss_id,provider,chat_id,kind,title,content,"
            "status,assignee_name,due_at) VALUES($1,'web',$2,'decision',$3,$3,$4,$5,$6)",
            bid, gid, f"Việc {i+1}", st, a, due)
    counts = dict(await conn.fetchrow(
        "SELECT count(*) FILTER (WHERE status='active') open, "
        "count(*) FILTER (WHERE status='active' AND due_at<now()) overdue, "
        "count(*) FILTER (WHERE status='resolved') done FROM knowledge_items "
        "WHERE boss_id=$1 AND assignee_name IS NOT NULL", bid))
    await conn.close()

    checks, fails = [], []

    def chk(name, ok, detail=""):
        checks.append(name)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{'' if ok else '  '+detail}")
        if not ok:
            fails.append(name)

    chk("DB counts (có assignee): open=8 overdue=3 done=5",
        counts == {"open": 8, "overdue": 3, "done": 5}, str(counts))
    s = {"boss": boss}
    dm = f"dm:{boss}"
    qa = [
        ("Ai đang quá tải nhất trong team?", ["Châu"], []),
        ("Có bao nhiêu việc đang trễ hạn?", ["3"], []),
        ("Tỷ lệ hoàn thành của Bình là bao nhiêu?", ["75"], []),
    ]
    for q, inc, exc in qa:
        ans = "\n".join(_ask_capture(s, dm, q))
        miss = [t for t in inc if _token_missing(t, ans)]
        leak = [t for t in exc if t in ans]
        chk(f"Q: {q}", not miss and not leak and bool(ans.strip()),
            f"missing={miss} :: {ans[:100]}")

    # --- GỘP THEO ĐẦU VIỆC (P2): EXTRACT thật trên hội thoại có phân-công + deadline +
    # ước lượng của CÙNG một người → phải ra ĐÚNG 1 đầu việc (due gắn vào đó), không tách
    # thành nhiều mục (kẻo workload đếm dư). today inject → suy năm cho '20/7'. ---
    boss2 = _post("/api/users", {"name": "Sếp Zeta", "role": "boss"})["id"]
    an2 = _post("/api/users", {"name": "An", "role": "employee"})["id"]
    gid2 = _post("/api/groups", {"name": "Dự án Zeta", "member_ids": [boss2, an2]})["id"]
    conn = await asyncpg.connect(DSN)
    bid2 = await _boss_id(conn, boss2)
    await conn.close()
    zeta = [
        ("boss", "Team mở dự án Zeta — app nội bộ chấm công. Phân việc nhé."),
        ("an", "Em An nhận phần backend Zeta, dùng FastAPI."),
        ("boss", "Deadline backend của An chốt 20/7 nhé."),
        ("an", "Em ước lượng khoảng 2 tuần là xong khung API."),
    ]
    who2 = {"boss": boss2, "an": an2}
    for r, t in zeta:
        _post("/api/send", {"as": who2[r], "chat_id": gid2, "text": t})
    _wait_ingested(gid2, len(zeta))
    _post("/api/extract", {"chat_id": gid2, "reset": True})
    conn = await asyncpg.connect(DSN)
    an_rows = await conn.fetch(
        "SELECT due_at FROM knowledge_items WHERE boss_id=$1 AND assignee_name='An' "
        "AND status='active'", bid2)
    await conn.close()
    exp = _dt.date(_dt.date.today().year, 7, 20)
    if exp < _dt.date.today():
        exp = _dt.date(exp.year + 1, 7, 20)
    n_an = len(an_rows)
    due_ok = any(r["due_at"] and r["due_at"].date() == exp for r in an_rows)
    # GỘP đầu việc là LLM-dependent (gpt-5.4-mini đôi khi tách deadline-ở-message-riêng
    # hoặc estimate thành item riêng cho cùng người). Theo nguyên tắc "không heuristic"
    # (không dedup bằng code), check theo MỤC TIÊU THỰC TẾ thay vì "đúng 1 item":
    #   (1) deadline TRUY ĐƯỢC và gắn ĐÚNG NGƯỜI (không vô chủ, không phantom) — due_ok
    #       query theo assignee='An' nên nếu deadline bị tách thành item VÔ CHỦ → due_ok=False.
    #   (2) workload KHÔNG đếm dư NHIỀU — cho phép tối đa 1 item phụ (n_an ≤ 2).
    chk("Deadline 20/7 truy được & gắn đúng người An (không vô chủ/phantom)",
        due_ok, f"due_ok={due_ok} (An có {n_an} item)")
    chk("Workload không đếm dư nhiều cho An (≤2 item active)",
        n_an <= 2, f"An có {n_an} item active (cho phép tối đa 2)")

    print(f"\n=== workload: {len(checks)-len(fails)}/{len(checks)} PASS (gid={gid}) ===")
    sys.exit(1 if fails else 0)


# ---------------------------------------------------------------------------
# ZALO E2E (tầng 3 — spec zalo-automation): app THẬT + ZaloAdapter THẬT +
# fake_bridge.js. Tự spawn uvicorn riêng (cổng 24815) với env fake-bridge,
# tự seed boss/bot_account/assignment/account_links, bơm hội thoại qua control
# socket, extract, hỏi bot, assert reply qua command-log của bridge.
# Không cần acc Zalo thật. Chạy lặp lại được (mỗi lần seed boss mới).
# ---------------------------------------------------------------------------

ZALO_PORT = 24815
ZALO_BASE = f"http://localhost:{ZALO_PORT}/test"
ZALO_GID = None  # sinh mỗi lần chạy (id nhóm zalo giả, digits ≥19 ký tự)
ZALO_BOSS_UID = "900"
ZALO_QUICK_ACKS = {_QUICK_ACK, "Em xem rồi trả lời ngay ạ."}

ZALO_CONVO = [
    # boss nói trước → ensure_tracked (giống luồng thật: sếp chào nhóm)
    ("boss", "Chào team, đây là nhóm dự án Zeta. Em bot sẽ hỗ trợ ghi nhận công việc nhé."),
    ("an",   "Em An nhận phần backend Zeta, dùng FastAPI, deadline 20/7 nhé sếp."),
    ("an",   "Phần deploy em sẽ dùng Docker trên VPS công ty."),
    ("boss", "Ok. Tài liệu API nhớ viết song song nhé."),
]


def _zalo_msg(uid, name, text, *, gid, mid, mentioned=False):
    """Event 'message' đúng shape bridge.js thật emit (payload đã normalize)."""
    import time as _t
    ts = int(_t.time() * 1000)
    return {"event": "message", "own_uid": "999", "data": {
        "type": 1, "threadId": gid, "thread_id": gid, "thread_type": "group",
        "uidFrom": uid, "sender_uid": uid, "dName": name, "sender_name": name,
        "msg_id": mid, "msgId": mid, "ts": ts, "ts_ms": ts,
        "text": text, "content": text, "content_type": "text", "media_url": None,
        "mentions": [{"uid": "999", "pos": 0, "len": 4}] if mentioned else [],
        "is_mentioned": mentioned, "is_forwarded": False, "reply_to": None,
    }}


async def _zalo_inject(sock_path, obj):
    r, w = await asyncio.open_unix_connection(sock_path)
    w.write((json.dumps({"inject": obj}) + "\n").encode())
    await w.drain()
    w.close()


def _bridge_sends(out_path, skip=0):
    """Command 'send' bridge đã nhận (bỏ quick-ack), từ dòng thứ `skip`."""
    import os
    if not os.path.exists(out_path):
        return []
    lines = open(out_path).read().splitlines()
    sends = []
    for ln in lines[skip:]:
        try:
            c = json.loads(ln)
        except ValueError:
            continue
        if c.get("method") == "send" and c["params"].get("text") not in ZALO_QUICK_ACKS:
            sends.append(c["params"])
    return sends


def _bridge_lines(out_path):
    import os
    if not os.path.exists(out_path):
        return 0
    return len(open(out_path).read().splitlines())


async def _zalo_wait_sends(out_path, skip, n=1, timeout=120):
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        sends = _bridge_sends(out_path, skip)
        if len(sends) >= n:
            return sends
        await asyncio.sleep(0.5)
    return _bridge_sends(out_path, skip)


async def zalo():
    import os
    import signal as _sig
    import subprocess
    import tempfile
    import time as _t
    import urllib.error
    import urllib.request
    import uuid as _uuid

    gid = "19007770001112223" + str(int(_t.time()))[-3:]
    sock_dir = tempfile.mkdtemp(prefix="zh")
    sock = os.path.join(sock_dir, "c.sock")
    out_path = os.path.join(sock_dir, "cmds.jsonl")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fake_bridge = os.path.join(repo_root, "tests", "fixtures", "zalo", "fake_bridge.js")

    # --- seed: boss + bot_account zalo + assignment + link acc chính của sếp ---
    conn = await asyncpg.connect(DSN)
    bid = await conn.fetchval(
        "INSERT INTO users(email, name, role) VALUES($1, 'Sếp Zalo', 'boss') RETURNING id",
        f"zalo-harness-{_uuid.uuid4().hex[:8]}@local.test")
    acc_id = await conn.fetchval(
        "INSERT INTO bot_accounts(provider, provider_user_id, account_kind, ownership, "
        "owner_boss_id, status) VALUES('zalo', $1, 'personal', 'boss_owned', $2, 'active') "
        "RETURNING id", f"999-{bid}", bid)
    await conn.execute(
        "INSERT INTO bot_account_assignments(boss_id, provider, bot_account_id, "
        "assignment_kind, status) VALUES($1, 'zalo', $2, 'boss_owned', 'active')", bid, acc_id)
    await conn.execute(
        "INSERT INTO account_links(boss_id, provider, provider_user_id) VALUES($1, 'zalo', $2) "
        "ON CONFLICT (provider, provider_user_id) DO UPDATE SET boss_id=EXCLUDED.boss_id",
        bid, ZALO_BOSS_UID)
    await conn.close()

    # --- spawn server riêng với fake bridge ---
    env = dict(os.environ,
               ZALO_BRIDGE_SCRIPT=fake_bridge,
               FAKE_BRIDGE_CTRL=sock, FAKE_BRIDGE_OUT=out_path,
               FAKE_BRIDGE_OWN_ID="999",
               ENABLE_WEB_TEST_CHANNEL="true")
    log_f = open(os.path.join(sock_dir, "server.log"), "w")
    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app",
         "--port", str(ZALO_PORT), "--log-level", "warning"],
        cwd=repo_root, env=env, stdout=log_f, stderr=log_f)
    print(f"server pid={srv.pid} port={ZALO_PORT} boss_id={bid} gid={gid}\n"
          f"bridge log: {out_path}")

    checks, fails = [], []

    def chk(name, ok, detail: object = ""):
        checks.append(name)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{'' if ok else '  ' + str(detail)}")
        if not ok:
            fails.append(name)

    try:
        # đợi server + fake bridge (boot_inbound_for_all spawn bridge cho acc active)
        deadline = _t.time() + 60
        up = False
        while _t.time() < deadline:
            try:
                urllib.request.urlopen(f"{ZALO_BASE}/api/chats/__probe__/messages", timeout=2)
                up = True
                break
            except (urllib.error.URLError, ConnectionError):
                await asyncio.sleep(0.5)
        chk("server lên", up)
        deadline = _t.time() + 30
        while _t.time() < deadline and not os.path.exists(sock):
            await asyncio.sleep(0.3)
        chk("fake bridge lên (inbound tự start cho acc active)", os.path.exists(sock))
        if fails:
            raise RuntimeError("hạ tầng không lên — dừng sớm")

        # --- bơm hội thoại nhóm ---
        who = {"boss": (ZALO_BOSS_UID, "Sếp Minh"), "an": ("111", "An")}
        for i, (role, text) in enumerate(ZALO_CONVO):
            uid, name = who[role]
            await _zalo_inject(sock, _zalo_msg(uid, name, text, gid=gid, mid=f"zm{i}"))
            await asyncio.sleep(0.1)

        conn = await asyncpg.connect(DSN)
        deadline = _t.time() + 20
        n_msgs = 0
        while _t.time() < deadline:
            n_msgs = await conn.fetchval(
                "SELECT count(*) FROM messages WHERE provider='zalo' AND chat_id=$1 "
                "AND boss_id=$2", gid, bid)
            if n_msgs >= len(ZALO_CONVO):
                break
            await asyncio.sleep(0.3)
        await conn.close()
        chk(f"inbound qua adapter thật: {len(ZALO_CONVO)} tin persist",
            n_msgs >= len(ZALO_CONVO), f"got {n_msgs}")

        # --- extract trên provider zalo ---
        body = json.dumps({"chat_id": gid, "reset": True, "provider": "zalo"}).encode()
        req = urllib.request.Request(f"{ZALO_BASE}/api/extract", data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            fired = json.loads(r.read().decode())
        chk("extract fired cho boss zalo", bid in fired.get("fired_for", []), fired)

        conn = await asyncpg.connect(DSN)
        k_rows = await conn.fetch(
            "SELECT content, assignee_name FROM knowledge_items WHERE boss_id=$1", bid)
        await conn.close()
        an_items = [r for r in k_rows if r["assignee_name"] == "An"]
        chk("spine: trích được việc của An từ hội thoại zalo",
            bool(an_items), f"{len(k_rows)} items, assignees="
            f"{[r['assignee_name'] for r in k_rows]}")

        # --- Q&A: sếp mention bot hỏi ---
        skip = _bridge_lines(out_path)
        await _zalo_inject(sock, _zalo_msg(
            ZALO_BOSS_UID, "Sếp Minh", "@bot ai lo phần backend Zeta, deadline khi nào?",
            gid=gid, mid="zq1", mentioned=True))
        sends = await _zalo_wait_sends(out_path, skip)
        ans = "\n".join(s["text"] for s in sends)
        miss = [t for t in ["An", "20/7"] if _token_missing(t, ans)]
        chk("Q&A qua kênh zalo: trả lời có An + 20/7", bool(sends) and not miss,
            f"missing={miss} :: {ans[:120]}")
        chk("reply đi đúng nhóm (thread_kind=group, đúng gid)",
            all(s["thread_kind"] == "group" and s["chat_id"] == gid for s in sends),
            sends and sends[0])

        # --- hành vi: nhắc người CHƯA onboard → ghi nhận + nhắc TẠI NHÓM ---
        skip = _bridge_lines(out_path)
        await _zalo_inject(sock, _zalo_msg(
            ZALO_BOSS_UID, "Sếp Minh",
            "@bot nhắc anh Tân chuẩn bị slide demo vào 15h thứ Ba tuần sau nhé",
            gid=gid, mid="zq2", mentioned=True))
        sends = await _zalo_wait_sends(out_path, skip)
        ans = "\n".join(s["text"] for s in sends)
        conn = await asyncpg.connect(DSN)
        rem = await conn.fetchrow(
            "SELECT scope, chat_id, provider, text FROM scheduled_reminders "
            "WHERE boss_id=$1 ORDER BY id DESC LIMIT 1", bid)
        await conn.close()
        chk("reminder cho người chưa onboard: có row scope=group đúng nhóm",
            rem is not None and rem["scope"] == "group" and rem["chat_id"] == gid,
            dict(rem) if rem else "no reminder row")
        chk("bot xác nhận trong nhóm, nhắc tên Tân, không đòi onboard",
            bool(sends) and not _token_missing("Tân", ans), f":: {ans[:120]}")

        n_ok = len(checks) - len(fails)
        print(f"\n=== zalo: {n_ok}/{len(checks)} PASS (boss_id={bid} gid={gid}) ===")
    finally:
        srv.send_signal(_sig.SIGTERM)
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log_f.close()
    sys.exit(1 if fails else 0)


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
    elif cmd == "gold":
        await gold(sys.argv[2] if len(sys.argv) > 2 else "scripts/gold_cases.json")
    elif cmd == "multipass":
        await multipass()
    elif cmd == "workload":
        await workload()
    elif cmd == "zalo":
        await zalo()
    elif cmd == "teardown":
        await teardown()
    else:
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
