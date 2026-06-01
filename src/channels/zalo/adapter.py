"""ZaloAdapter — spawns Node bridge subprocess per bot_account.

Lifecycle:
  - ``start_inbound(bot_acc)``  → decrypt credentials, write to ephemeral
                                  session file under ``self._sessions_dir``,
                                  spawn ``node bridge.js``, attach stdout
                                  reader (publishes ``inbound.raw.zalo``
                                  events) + stderr forwarder.
  - ``send_text(...)``           → writes a ``send`` command to the bridge
                                  stdin. Fire-and-forget at MVP — the
                                  bridge replies with ``msg_id`` async; we
                                  only block to ``drain`` the write buffer.
  - ``list_members(...)``        → writes a ``fetch_members`` command and
                                  waits for the matching reply (by request id).
  - ``stop_inbound(bot_acc)``    → SIGTERM the subprocess.

Bridge protocol details live in ``bridge_protocol.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import tempfile
from pathlib import Path
from typing import Any

from src.events.bus import EventBus
from src.services.bot_account_session import decrypt_credentials

log = logging.getLogger(__name__)

BRIDGE_DIR = Path(__file__).parent / "bridge"
BRIDGE_SCRIPT = BRIDGE_DIR / "bridge.js"


class ZaloAdapter:
    provider = "zalo"

    def __init__(self, bus: EventBus, bot_accounts_repo: Any = None):
        self.bus = bus
        self.repo = bot_accounts_repo
        self._procs: dict[int, asyncio.subprocess.Process] = {}
        self._req_seq: dict[int, int] = {}
        self._pending: dict[int, dict[int, asyncio.Future]] = {}
        self._sessions_dir = Path(tempfile.mkdtemp(prefix="zalo_session_"))

    # --- public adapter surface -------------------------------------------------

    async def start_inbound(self, bot_acc) -> None:
        if bot_acc.id in self._procs and self._procs[bot_acc.id].returncode is None:
            return  # idempotent
        session_path = self._sessions_dir / f"{bot_acc.id}.json"
        if getattr(bot_acc, "credentials_blob_enc", None):
            creds = decrypt_credentials(bytes(bot_acc.credentials_blob_enc))
            session_path.write_text(json.dumps(creds))
        env = os.environ.copy()
        env["SESSION_PATH"] = str(session_path)
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BRIDGE_DIR),
            env=env,
        )
        self._procs[bot_acc.id] = proc
        self._pending[bot_acc.id] = {}
        self._req_seq[bot_acc.id] = 0
        asyncio.create_task(self._read_stdout(bot_acc, proc))
        asyncio.create_task(self._read_stderr(bot_acc, proc))

    async def stop_inbound(self, bot_acc) -> None:
        proc = self._procs.pop(bot_acc.id, None)
        self._pending.pop(bot_acc.id, None)
        self._req_seq.pop(bot_acc.id, None)
        if proc is None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    async def send_text(
        self,
        bot_acc,
        chat_id: str,
        text: str,
        thread_kind: str,
    ) -> str:
        proc = self._procs.get(bot_acc.id)
        if proc is None or proc.stdin is None:
            raise RuntimeError(f"bridge not running for bot_account_id={bot_acc.id}")
        req_id = self._next_req_id(bot_acc.id)
        cmd = {
            "id": req_id,
            "method": "send",
            "params": {
                "chat_id": chat_id,
                "thread_id": chat_id,
                "text": text,
                "thread_kind": thread_kind,
            },
        }
        proc.stdin.write((json.dumps(cmd) + "\n").encode())
        await proc.stdin.drain()
        # MVP: fire-and-forget on send. The reply (with msg_id) flows through
        # _read_stdout and is logged; we don't block agent loop on it.
        return "<async>"

    async def list_members(
        self,
        bot_acc,
        group_id: str,
        timeout_s: float = 10.0,
    ) -> list[str]:
        proc = self._procs.get(bot_acc.id)
        if proc is None or proc.stdin is None:
            raise RuntimeError(f"bridge not running for bot_account_id={bot_acc.id}")
        req_id = self._next_req_id(bot_acc.id)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[bot_acc.id][req_id] = fut
        cmd = {
            "id": req_id,
            "method": "fetch_members",
            "params": {"group_id": group_id},
        }
        proc.stdin.write((json.dumps(cmd) + "\n").encode())
        await proc.stdin.drain()
        try:
            result = await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            self._pending[bot_acc.id].pop(req_id, None)
            raise
        return list(result.get("member_ids", []))

    # --- internals --------------------------------------------------------------

    def _next_req_id(self, bot_acc_id: int) -> int:
        n = self._req_seq.get(bot_acc_id, 0) + 1
        self._req_seq[bot_acc_id] = n
        return n

    async def _read_stdout(
        self, bot_acc, proc: asyncio.subprocess.Process
    ) -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                obj = json.loads(line)
            except Exception:
                log.warning("zalo bridge bad json", extra={"line": line[:200]})
                continue

            if "event" in obj:
                await self._handle_event(bot_acc, obj)
            elif "id" in obj:
                self._handle_reply(bot_acc, obj)

    async def _read_stderr(
        self, bot_acc, proc: asyncio.subprocess.Process
    ) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            log.info(
                "zalo.bridge[%s] %s",
                bot_acc.id,
                line.decode(errors="replace").rstrip(),
            )

    async def _handle_event(self, bot_acc, obj: dict) -> None:
        ev = obj.get("event")
        data = obj.get("data") or {}
        if ev == "message":
            await self.bus.publish(
                "inbound.raw.zalo",
                {
                    "bot_account_id": bot_acc.id,
                    "data": data,
                    "own_uid": obj.get("own_uid"),
                },
            )
        elif ev == "ready":
            log.info(
                "zalo bridge ready bot_acc=%s own_id=%s",
                bot_acc.id,
                data.get("own_id"),
            )
        elif ev == "disconnected":
            await self.bus.publish(
                "bot_account.status_changed",
                {
                    "bot_account_id": bot_acc.id,
                    "to": "logged_out" if data.get("fatal") else "rate_limited",
                    "reason": data.get("reason"),
                },
            )
        elif ev == "status":
            await self.bus.publish(
                "bot_account.status_changed",
                {
                    "bot_account_id": bot_acc.id,
                    "to": data.get("status"),
                    "reason": data.get("reason"),
                },
            )

    def _handle_reply(self, bot_acc, obj: dict) -> None:
        req_id = obj.get("id")
        pending = self._pending.get(bot_acc.id, {})
        fut = pending.pop(req_id, None)
        if fut is None or fut.done():
            return
        if "error" in obj:
            fut.set_exception(RuntimeError(obj["error"].get("message", "bridge error")))
        else:
            fut.set_result(obj.get("result") or {})
