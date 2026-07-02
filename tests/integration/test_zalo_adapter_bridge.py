"""Integration: ZaloAdapter spawn fake_bridge.js THẬT qua node (tầng 2 — spec zalo-automation).

Bổ khuyết cho ``test_zalo_adapter.py`` (fake proc in-process): ở đây đi qua
đường spawn subprocess thật — settings.ZALO_BRIDGE_SCRIPT, env, SESSION_PATH,
reader loop trên pipe thật, lifecycle start/stop. Điều khiển fake bridge qua
control socket (inject event động) + command-log (assert protocol).

Không cần DB / zca-js / acc thật — chỉ cần ``node``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.channels.zalo.adapter import ZaloAdapter
from src.config import settings
from src.events.bus import InMemoryEventBus

REPO = Path(__file__).resolve().parents[2]
FAKE_BRIDGE = REPO / "tests" / "fixtures" / "zalo" / "fake_bridge.js"

GROUP_ID = "19001234567890123456"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


class Ctrl:
    """Client control socket của fake bridge."""

    def __init__(self, path: Path):
        self.path = path
        self._writer = None

    async def connect(self, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                _, self._writer = await asyncio.open_unix_connection(str(self.path))
                return
            except (FileNotFoundError, ConnectionRefusedError):
                if asyncio.get_running_loop().time() > deadline:
                    raise
                await asyncio.sleep(0.05)

    async def _send(self, obj: dict) -> None:
        assert self._writer is not None
        self._writer.write((json.dumps(obj) + "\n").encode())
        await self._writer.drain()

    async def inject(self, obj: dict) -> None:
        await self._send({"inject": obj})

    async def set(self, **kw) -> None:
        await self._send({"set": kw})

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()


def _group_message(text: str, *, mentioned: bool = True, uid: str = "111") -> dict:
    """Event 'message' đúng shape bridge.js thật emit (payload đã normalize)."""
    return {
        "event": "message",
        "own_uid": "999",
        "data": {
            "type": 1,
            "threadId": GROUP_ID,
            "thread_id": GROUP_ID,
            "thread_type": "group",
            "uidFrom": uid,
            "sender_uid": uid,
            "dName": "An Nguyễn",
            "sender_name": "An Nguyễn",
            "msg_id": "m100",
            "msgId": "m100",
            "ts": 1751400000000,
            "ts_ms": 1751400000000,
            "text": text,
            "content": text,
            "content_type": "text",
            "media_url": None,
            "mentions": [{"uid": "999", "pos": 0, "len": 4}] if mentioned else [],
            "is_mentioned": mentioned,
            "is_forwarded": False,
            "reply_to": None,
        },
    }


@pytest.fixture()
async def rig(tmp_path, monkeypatch):
    # AF_UNIX giới hạn ~104 ký tự — tmp_path của pytest nằm dưới repo path dài
    # (tên thư mục tiếng Việt) nên socket phải ra TMPDIR hệ thống (ngắn).
    sock_dir = Path(tempfile.mkdtemp(prefix="zbr"))
    ctrl_path = sock_dir / "c.sock"
    out_path = tmp_path / "cmds.jsonl"
    monkeypatch.setattr(settings, "ZALO_BRIDGE_SCRIPT", str(FAKE_BRIDGE))
    monkeypatch.setenv("FAKE_BRIDGE_CTRL", str(ctrl_path))
    monkeypatch.setenv("FAKE_BRIDGE_OUT", str(out_path))

    bus = InMemoryEventBus()
    inbound: list = []
    statuses: list = []

    async def on_inbound(payload):
        inbound.append(payload["message"])

    async def on_status(payload):
        statuses.append(payload)

    bus.subscribe("inbound.normalized", on_inbound)
    bus.subscribe("bot_account.status_changed", on_status)

    adapter = ZaloAdapter(bus)
    acc = SimpleNamespace(id=7, credentials_blob_enc=None, owner_boss_id=None)
    await adapter.start_inbound(acc)

    ctrl = Ctrl(ctrl_path)
    await ctrl.connect()

    yield SimpleNamespace(
        adapter=adapter, acc=acc, ctrl=ctrl,
        inbound=inbound, statuses=statuses, out_path=out_path,
    )
    ctrl.close()
    await adapter.stop_inbound(acc)
    shutil.rmtree(sock_dir, ignore_errors=True)


async def _wait_until(pred, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not pred():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)


def _bridge_cmds(out_path: Path) -> list[dict]:
    if not out_path.exists():
        return []
    return [json.loads(x) for x in out_path.read_text().splitlines() if x.strip()]


async def test_injected_group_message_reaches_bus_normalized(rig):
    await rig.ctrl.inject(_group_message("@bot ai lo phần backend?"))
    await _wait_until(lambda: len(rig.inbound) == 1)

    msg = rig.inbound[0]
    assert msg.provider == "zalo"
    assert msg.bot_account_id == 7
    assert msg.chat_id == GROUP_ID and msg.chat_type == "group"
    assert msg.text == "@bot ai lo phần backend?"
    assert msg.mentions_bot is True
    assert msg.sender_provider_id == "111"
    assert msg.sender_name == "An Nguyễn"
    assert msg.provider_msg_id == "m100"
    assert msg.ts == datetime.fromtimestamp(1751400000, tz=timezone.utc)


async def test_mentions_bot_false_without_mention(rig):
    await rig.ctrl.inject(_group_message("bàn tiếp vụ deadline nhé", mentioned=False))
    await _wait_until(lambda: len(rig.inbound) == 1)
    assert rig.inbound[0].mentions_bot is False


async def test_send_text_writes_protocol_send_over_real_pipe(rig):
    ret = await rig.adapter.send_text(rig.acc, GROUP_ID, "Dạ, em ghi nhận rồi ạ", "group")
    assert ret == "<async>"
    await _wait_until(
        lambda: any(c.get("method") == "send" for c in _bridge_cmds(rig.out_path))
    )
    cmd = next(c for c in _bridge_cmds(rig.out_path) if c["method"] == "send")
    assert cmd["params"] == {
        "chat_id": GROUP_ID, "thread_id": GROUP_ID,
        "text": "Dạ, em ghi nhận rồi ạ", "thread_kind": "group",
    }


async def test_list_members_roundtrip_and_timeout(rig):
    await rig.ctrl.set(members=["111", "222", "333"])
    ids = await rig.adapter.list_members(rig.acc, GROUP_ID)
    assert ids == ["111", "222", "333"]

    await rig.ctrl.set(mute_replies=True)
    with pytest.raises(asyncio.TimeoutError):
        await rig.adapter.list_members(rig.acc, GROUP_ID, timeout_s=0.3)


async def test_fatal_disconnect_publishes_logged_out(rig):
    await rig.ctrl.inject(
        {"event": "disconnected", "data": {"reason": "session expired", "fatal": True}}
    )
    await _wait_until(lambda: len(rig.statuses) == 1)
    assert rig.statuses[0] == {
        "bot_account_id": 7, "to": "logged_out", "reason": "session expired",
    }


async def test_status_event_passthrough(rig):
    await rig.ctrl.inject(
        {"event": "status", "data": {"status": "rate_limited", "reason": "too fast"}}
    )
    await _wait_until(lambda: len(rig.statuses) == 1)
    assert rig.statuses[0]["to"] == "rate_limited"


async def test_start_idempotent_and_stop_kills_process(rig):
    proc = rig.adapter._procs[rig.acc.id]
    await rig.adapter.start_inbound(rig.acc)  # idempotent — không spawn thêm
    assert rig.adapter._procs[rig.acc.id] is proc

    await rig.adapter.stop_inbound(rig.acc)
    assert rig.acc.id not in rig.adapter._procs
    assert proc.returncode is not None
    assert await rig.adapter.health_check() == {}
