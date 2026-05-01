"""Async subprocess client for the Node bridge.js."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

logger = logging.getLogger("channels.zalo.bridge")

EventHandler = Callable[[str, dict], Awaitable[None]]


class ZaloBridgeProcess:
    """Spawns `node bridge.js`, owns stdio, dispatches replies + events.

    Single-shot lifecycle: `start()` once, `call()` many, `close()` once.
    """

    def __init__(
        self,
        node_path: str,
        bridge_js_path: str,
        session_path: str,
        on_event: EventHandler,
    ) -> None:
        self._node_path = node_path
        self._bridge_js = bridge_js_path
        self._session = session_path
        self._on_event = on_event
        self._proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._own_id: str = ""

    @property
    def own_id(self) -> str:
        return self._own_id

    async def start(self, ready_timeout: float = 30.0) -> None:
        cwd = os.path.dirname(os.path.abspath(self._bridge_js))
        argv = [self._node_path, self._bridge_js]
        if self._session:
            argv += ["--session", os.path.abspath(self._session)]
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=ready_timeout)
        except asyncio.TimeoutError as exc:
            await self._terminate()
            raise RuntimeError("zalo bridge: timeout waiting for ready event") from exc

    async def call(
        self, method: str, params: dict | None = None, timeout: float = 30.0,
    ) -> dict:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("zalo bridge not running")
        self._next_id += 1
        cid = self._next_id
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[cid] = fut
        cmd = {"id": cid, "method": method, "params": params or {}}
        line = (json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._proc.stdin.write(line)
            await self._proc.stdin.drain()
        except Exception:
            self._pending.pop(cid, None)
            raise
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(cid, None)

    async def close(self) -> None:
        if not self._proc:
            return
        try:
            await asyncio.wait_for(self.call("shutdown", {}, timeout=3.0), timeout=3.0)
        except Exception:
            pass
        await self._terminate()

    async def _terminate(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.kill()
        for t in (self._stdout_task, self._stderr_task):
            if t and not t.done():
                t.cancel()
        self._proc = None

    async def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except Exception:
                logger.warning("zalo bridge: bad stdout line: %r", line[:200])
                continue
            if "id" in msg:
                fut = self._pending.get(msg["id"])
                if fut and not fut.done():
                    if "error" in msg:
                        err = msg["error"] or {}
                        fut.set_exception(RuntimeError(
                            f"{err.get('code', 'error')}: {err.get('message', '')}"
                        ))
                    else:
                        fut.set_result(msg.get("result", {}))
            elif "event" in msg:
                ev, data = msg["event"], msg.get("data", {})
                if ev == "ready":
                    self._own_id = str(data.get("own_id", ""))
                    self._ready.set()
                else:
                    asyncio.create_task(self._dispatch_event(ev, data))

    async def _dispatch_event(self, event: str, data: dict) -> None:
        try:
            await self._on_event(event, data)
        except Exception:
            logger.exception("zalo bridge: event handler raised (event=%s)", event)

    async def _read_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.info("[bridge.stderr] %s", text)
