"""Tests for ZaloBridgeProcess — JSONL framing without spawning Node.

We replace `_proc.stdin/stdout/stderr` with in-memory asyncio streams and
drive `_read_stdout` directly to verify id correlation, ready signalling,
event dispatch, and error replies.
"""
from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from src.channels.zalo_bridge.process import ZaloBridgeProcess


class _FakeWriter:
    """Captures bytes written by `call()`."""

    def __init__(self) -> None:
        self.buffer: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _make_reader(lines: list[bytes]) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()
    return reader


async def _events_collector() -> tuple[list[tuple[str, dict]], Any]:
    seen: list[tuple[str, dict]] = []

    async def on_event(ev: str, data: dict) -> None:
        seen.append((ev, data))

    return seen, on_event


async def test_ready_event_unblocks_start():
    seen, on_event = await _events_collector()
    bridge = ZaloBridgeProcess("node", "/x/bridge.js", "/x/session.json", on_event)

    reader = _make_reader([
        json.dumps({"event": "ready", "data": {"own_id": "12345"}}).encode() + b"\n",
    ])
    writer = _FakeWriter()
    bridge._proc = SimpleNamespace(stdin=writer, stdout=reader, stderr=_make_reader([]))

    bridge._stdout_task = asyncio.create_task(bridge._read_stdout())
    bridge._stderr_task = asyncio.create_task(bridge._read_stderr())

    await asyncio.wait_for(bridge._ready.wait(), timeout=1.0)
    assert bridge.own_id == "12345"

    bridge._stdout_task.cancel()
    bridge._stderr_task.cancel()


async def test_call_correlates_id_and_returns_result():
    seen, on_event = await _events_collector()
    bridge = ZaloBridgeProcess("node", "/x/bridge.js", "/x/session.json", on_event)

    # Reader stays open; we feed the reply *after* call() registers the future.
    reader = asyncio.StreamReader()
    writer = _FakeWriter()
    bridge._proc = SimpleNamespace(stdin=writer, stdout=reader, stderr=_make_reader([]))
    bridge._stdout_task = asyncio.create_task(bridge._read_stdout())

    async def feed_reply():
        # Wait until call() has written the request, then feed the reply.
        for _ in range(100):
            if writer.buffer:
                break
            await asyncio.sleep(0.005)
        reader.feed_data(
            json.dumps({"id": 1, "result": {"msg_id": "abc"}}).encode() + b"\n"
        )

    feeder = asyncio.create_task(feed_reply())
    result = await asyncio.wait_for(
        bridge.call("send", {"thread_id": "t", "thread_type": "dm", "text": "hi"}),
        timeout=1.0,
    )
    await feeder
    assert result == {"msg_id": "abc"}

    sent = b"".join(writer.buffer).decode()
    payload = json.loads(sent.strip())
    assert payload["id"] == 1
    assert payload["method"] == "send"
    assert payload["params"]["text"] == "hi"

    reader.feed_eof()
    bridge._stdout_task.cancel()


async def test_call_propagates_error_payload():
    seen, on_event = await _events_collector()
    bridge = ZaloBridgeProcess("node", "/x/bridge.js", "/x/session.json", on_event)

    reader = asyncio.StreamReader()
    writer = _FakeWriter()
    bridge._proc = SimpleNamespace(stdin=writer, stdout=reader, stderr=_make_reader([]))
    bridge._stdout_task = asyncio.create_task(bridge._read_stdout())

    async def feed_err():
        for _ in range(100):
            if writer.buffer:
                break
            await asyncio.sleep(0.005)
        reader.feed_data(
            json.dumps({"id": 1, "error": {"code": "send_failed", "message": "nope"}}).encode() + b"\n"
        )

    feeder = asyncio.create_task(feed_err())
    with pytest.raises(RuntimeError, match="send_failed"):
        await asyncio.wait_for(
            bridge.call("send", {"thread_id": "t", "thread_type": "dm", "text": "hi"}),
            timeout=1.0,
        )
    await feeder

    reader.feed_eof()
    bridge._stdout_task.cancel()


async def test_events_dispatched_to_handler():
    seen, on_event = await _events_collector()
    bridge = ZaloBridgeProcess("node", "/x/bridge.js", "/x/session.json", on_event)

    reader = _make_reader([
        json.dumps({"event": "ready", "data": {"own_id": "1"}}).encode() + b"\n",
        json.dumps({"event": "message", "data": {"thread_id": "T", "text": "hello"}}).encode() + b"\n",
        json.dumps({"event": "disconnected", "data": {"fatal": False}}).encode() + b"\n",
    ])
    writer = _FakeWriter()
    bridge._proc = SimpleNamespace(stdin=writer, stdout=reader, stderr=_make_reader([]))
    bridge._stdout_task = asyncio.create_task(bridge._read_stdout())

    # `ready` is consumed internally; the others go to on_event via tasks.
    await asyncio.wait_for(bridge._ready.wait(), timeout=1.0)
    # Wait for stdout task to drain queued events.
    for _ in range(50):
        if len(seen) >= 2:
            break
        await asyncio.sleep(0.01)

    kinds = [ev for ev, _ in seen]
    assert "message" in kinds
    assert "disconnected" in kinds

    bridge._stdout_task.cancel()


async def test_malformed_line_is_logged_and_skipped():
    seen, on_event = await _events_collector()
    bridge = ZaloBridgeProcess("node", "/x/bridge.js", "/x/session.json", on_event)

    reader = _make_reader([
        b"not-json\n",
        json.dumps({"event": "ready", "data": {"own_id": "1"}}).encode() + b"\n",
    ])
    writer = _FakeWriter()
    bridge._proc = SimpleNamespace(stdin=writer, stdout=reader, stderr=_make_reader([]))
    bridge._stdout_task = asyncio.create_task(bridge._read_stdout())

    # Bad line does not raise; ready still fires after.
    await asyncio.wait_for(bridge._ready.wait(), timeout=1.0)

    bridge._stdout_task.cancel()
