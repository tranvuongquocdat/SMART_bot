"""Contract test: bridge.js THẬT chạy trên zca-js GIẢ (tầng 1 — spec zalo-automation).

Spawn ``node --require hijack.js bridge.js`` — hijack redirect require('zca-js')
về stub ``tests/fixtures/zalo/fake_zca``. Assert đúng wire-protocol ở
``src/channels/zalo/bridge_protocol.py``:
  - stdout events: ready / message (normalize) / disconnected
  - stdin commands: send / fetch_members / get_own_id / shutdown → reply theo id
  - stub ghi API-call log ra $FAKE_ZCA_OUT để assert bridge gọi zca-js đúng tham số.

Không cần zca-js thật, không cần DB — chỉ cần ``node``.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE_JS = REPO / "src" / "channels" / "zalo" / "bridge" / "bridge.js"
HIJACK_JS = REPO / "tests" / "fixtures" / "zalo" / "fake_zca" / "hijack.js"
SCENARIO_BASIC = REPO / "tests" / "fixtures" / "zalo" / "scenarios" / "basic.json"

GROUP_ID = "19001234567890123456"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


class BridgeProc:
    """Chạy bridge.js + reader thread; đọc event/reply có timeout."""

    def __init__(self, tmp_path: Path, scenario: Path = SCENARIO_BASIC):
        session = tmp_path / "session.json"
        session.write_text(json.dumps({"cookie": {"k": "v"}, "imei": "imei-1", "userAgent": "ua"}))
        self.api_log_path = tmp_path / "zca_calls.jsonl"
        self.proc = subprocess.Popen(
            ["node", "--require", str(HIJACK_JS), str(BRIDGE_JS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(BRIDGE_JS.parent),
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "SESSION_PATH": str(session),
                "FAKE_ZCA_SCENARIO": str(scenario),
                "FAKE_ZCA_OUT": str(self.api_log_path),
            },
            text=True,
        )
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._stderr: list[str] = []
        threading.Thread(target=self._read, args=(self.proc.stdout,), daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self, stream) -> None:
        for line in stream:
            self._lines.put(line)
        self._lines.put(None)

    def _read_err(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.rstrip())

    def send(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def send_raw(self, raw: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(raw + "\n")
        self.proc.stdin.flush()

    def next_obj(self, timeout: float = 8.0) -> dict:
        line = self._lines.get(timeout=timeout)
        if line is None:
            raise AssertionError("bridge stdout closed; stderr:\n" + "\n".join(self._stderr))
        return json.loads(line)

    def wait_for(self, pred, timeout: float = 8.0) -> dict:
        """Đọc tuần tự tới khi gặp object khớp pred (bỏ qua object khác)."""
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            obj = self.next_obj(timeout=max(0.1, deadline - time.monotonic()))
            if pred(obj):
                return obj
        raise AssertionError("timed out waiting for matching bridge output")

    def api_calls(self) -> list[dict]:
        if not self.api_log_path.exists():
            return []
        return [json.loads(x) for x in self.api_log_path.read_text().splitlines() if x.strip()]

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=5)


@pytest.fixture()
def bridge(tmp_path):
    b = BridgeProc(tmp_path)
    yield b
    b.close()


def test_ready_then_normalized_messages_skip_self(bridge):
    ready = bridge.next_obj()
    assert ready == {"event": "ready", "data": {"own_id": "999"}}

    msgs = [bridge.next_obj() for _ in range(3)]
    assert all(m["event"] == "message" and m["own_uid"] == "999" for m in msgs)
    d1, d2, d3 = (m["data"] for m in msgs)

    # m1: group + mention bot
    assert d1["thread_type"] == "group" and d1["threadId"] == GROUP_ID
    assert d1["is_mentioned"] is True
    assert d1["sender_uid"] == "111" and d1["sender_name"] == "An Nguyễn"
    assert d1["text"] == "@bot nhắc anh Tân họp triển khai chiều thứ 3 nhé"
    assert d1["msg_id"] == "m1" and d1["ts_ms"] == 1751400000000

    # m2: DM (type 0)
    assert d2["type"] == 0 and d2["thread_type"] == "dm"
    assert d2["text"] == "/start abc123"

    # m3: file + quote → content_type/file, media_url, reply_to
    assert d3["content_type"] == "file"
    assert d3["text"] == "bao-cao-q2.pdf"
    assert d3["media_url"] == "https://files.example/bao-cao-q2.pdf"
    assert d3["reply_to"] == {"msg_id": "m1", "sender_uid": "111"}

    # m4 (uidFrom = own id) bị bridge bỏ qua → không còn message nào ngay lập tức;
    # login đã nhận đúng creds từ session file.
    calls = bridge.api_calls()
    login = next(c for c in calls if c["api"] == "login")
    assert login == {"api": "login", "has_cookie": True, "imei": "imei-1"}


def test_send_group_and_dm_use_correct_thread_type(bridge):
    bridge.wait_for(lambda o: o.get("event") == "ready")

    bridge.send({"id": 1, "method": "send",
                 "params": {"thread_id": GROUP_ID, "text": "Dạ em nhắc rồi ạ", "thread_kind": "group"}})
    r1 = bridge.wait_for(lambda o: o.get("id") == 1)
    assert r1["result"]["msg_id"].startswith("sent-")

    bridge.send({"id": 2, "method": "send",
                 "params": {"thread_id": "111", "text": "Chào anh", "thread_kind": "user"}})
    r2 = bridge.wait_for(lambda o: o.get("id") == 2)
    assert "result" in r2

    sends = [c for c in bridge.api_calls() if c["api"] == "sendMessage"]
    assert sends[0] == {"api": "sendMessage", "msg": "Dạ em nhắc rồi ạ",
                        "threadId": GROUP_ID, "thread_type": 1}
    assert sends[1]["thread_type"] == 0 and sends[1]["threadId"] == "111"


def test_fetch_members_parses_mem_ver_list(bridge):
    bridge.wait_for(lambda o: o.get("event") == "ready")
    bridge.send({"id": 3, "method": "fetch_members", "params": {"group_id": GROUP_ID}})
    r = bridge.wait_for(lambda o: o.get("id") == 3)
    assert r["result"] == {"member_ids": ["111", "222", "999"]}

    # nhóm không tồn tại → mảng rỗng, không error
    bridge.send({"id": 4, "method": "fetch_members", "params": {"group_id": "nope"}})
    r = bridge.wait_for(lambda o: o.get("id") == 4)
    assert r["result"] == {"member_ids": []}


def test_get_own_id_unknown_method_and_garbage_stdin(bridge):
    bridge.wait_for(lambda o: o.get("event") == "ready")

    bridge.send_raw("not-json{{{")  # bridge phải sống sót
    bridge.send({"id": 5, "method": "get_own_id", "params": {}})
    r = bridge.wait_for(lambda o: o.get("id") == 5)
    assert r["result"] == {"own_id": "999"}

    bridge.send({"id": 6, "method": "teleport", "params": {}})
    r = bridge.wait_for(lambda o: o.get("id") == 6)
    assert r["error"]["code"] == "unknown_method"


def test_listener_error_emits_nonfatal_disconnected(bridge, tmp_path):
    b = BridgeProc(tmp_path / "err", scenario=_scenario_with_error(tmp_path))
    try:
        ev = b.wait_for(lambda o: o.get("event") == "disconnected")
        assert ev["data"]["fatal"] is False
        assert "socket closed" in ev["data"]["reason"]
    finally:
        b.close()


def test_shutdown_exits_zero(bridge):
    bridge.wait_for(lambda o: o.get("event") == "ready")
    bridge.send({"id": 9, "method": "shutdown", "params": {}})
    bridge.wait_for(lambda o: o.get("id") == 9)
    assert bridge.proc.wait(timeout=5) == 0


def _scenario_with_error(tmp_path: Path) -> Path:
    sc = json.loads(SCENARIO_BASIC.read_text())
    sc["messages"] = []
    sc["listener_error"] = "socket closed"
    p = tmp_path / "err_scenario.json"
    (tmp_path / "err").mkdir(exist_ok=True)
    p.write_text(json.dumps(sc))
    return p
