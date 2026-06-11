"""Luồng boss tự kết nối Zalo: quét QR bằng acc phụ từ trang Channels.

Mỗi phiên login spawn ``qr_login.js`` (headless, NDJSON qua stdout). Python
stream QR về frontend qua polling; khi user quét xong:

  1. Mã hóa session (Fernet) → tạo ``bot_accounts`` row ownership=boss_owned.
  2. Gán account cho boss (assign_boss_owned + accept) → adapter start_inbound.

Một boss chỉ có một phiên login sống tại một thời điểm; phiên cũ bị hủy khi
mở phiên mới. Phiên hết hạn theo timeout của script (180s).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.services.bot_account_session import encrypt_credentials

log = logging.getLogger(__name__)

BRIDGE_DIR = Path(__file__).parent.parent / "channels" / "zalo" / "bridge"
QR_LOGIN_SCRIPT = BRIDGE_DIR / "qr_login.js"


@dataclass
class LoginSession:
    login_id: str
    boss_id: int
    status: str = "starting"  # starting|qr|scanned|success|error
    qr_image_b64: str | None = None
    display_name: str | None = None
    error: str | None = None
    bot_account_id: int | None = None
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)


class ZaloQrLoginManager:
    def __init__(self, pool, bus, adapter_map_getter):
        """adapter_map_getter: callable trả về {provider: adapter} tại thời điểm gọi
        (channel registry chỉ sẵn sàng sau lifespan startup)."""
        self.pool = pool
        self.bus = bus
        self._adapter_map_getter = adapter_map_getter
        self._sessions: dict[str, LoginSession] = {}
        self._by_boss: dict[int, str] = {}

    async def start(self, boss_id: int) -> LoginSession:
        # Hủy phiên cũ của boss nếu còn sống
        old_id = self._by_boss.get(boss_id)
        if old_id:
            await self._kill(old_id)

        login_id = uuid.uuid4().hex
        sess = LoginSession(login_id=login_id, boss_id=boss_id)
        self._sessions[login_id] = sess
        self._by_boss[boss_id] = login_id

        proc = await asyncio.create_subprocess_exec(
            "node",
            str(QR_LOGIN_SCRIPT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BRIDGE_DIR),
        )
        sess.proc = proc
        asyncio.create_task(self._read_events(sess, proc))
        asyncio.create_task(self._drain_stderr(proc))
        return sess

    def get(self, boss_id: int, login_id: str) -> LoginSession | None:
        sess = self._sessions.get(login_id)
        if sess is None or sess.boss_id != boss_id:
            return None
        return sess

    async def _kill(self, login_id: str) -> None:
        sess = self._sessions.pop(login_id, None)
        if sess is None:
            return
        self._by_boss.pop(sess.boss_id, None)
        if sess.proc is not None and sess.proc.returncode is None:
            try:
                sess.proc.kill()
                await sess.proc.wait()
            except ProcessLookupError:
                pass

    async def _drain_stderr(self, proc) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            log.info("zalo.qr_login: %s", line.decode(errors="replace").rstrip())

    async def _read_events(self, sess: LoginSession, proc) -> None:
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                ev, data = obj.get("event"), obj.get("data") or {}
                if ev == "qr":
                    sess.status = "qr"
                    sess.qr_image_b64 = data.get("image")
                elif ev == "scanned":
                    sess.status = "scanned"
                    sess.display_name = data.get("display_name")
                elif ev == "error":
                    sess.status = "error"
                    sess.error = data.get("message") or "QR login thất bại"
                elif ev == "success":
                    try:
                        await self._provision(sess, data)
                        sess.status = "success"
                    except Exception as e:
                        log.exception("zalo qr provision failed boss=%s", sess.boss_id)
                        sess.status = "error"
                        sess.error = f"Lưu tài khoản thất bại: {e}"
        finally:
            await proc.wait()
            if sess.status not in ("success", "error"):
                sess.status = "error"
                sess.error = sess.error or "Phiên đăng nhập kết thúc bất thường"

    async def _provision(self, sess: LoginSession, data: dict) -> None:
        from src.services.bot_account_service import BotAccountService

        own_id = data.get("own_id")
        display_name = data.get("display_name") or f"Zalo {own_id}"
        creds = {
            "cookie": data.get("cookie"),
            "imei": data.get("imei"),
            "userAgent": data.get("userAgent"),
        }
        blob = encrypt_credentials(creds)

        async with self.pool.acquire() as c:
            # Acc phụ này đã từng kết nối (re-login) → cập nhật session cũ.
            bot_account_id = await c.fetchval(
                """
                UPDATE bot_accounts
                   SET credentials_blob_enc=$3, status='active',
                       display_name=$4, updated_at=NOW()
                 WHERE provider='zalo' AND ownership='boss_owned'
                   AND owner_boss_id=$1 AND provider_user_id=$2
                RETURNING id
                """,
                sess.boss_id,
                own_id,
                blob,
                display_name,
            )
            if bot_account_id is None:
                bot_account_id = await c.fetchval(
                    """
                    INSERT INTO bot_accounts
                      (provider, provider_user_id, display_name, account_kind,
                       ownership, owner_boss_id, credentials_blob_enc, status,
                       max_assigned_bosses)
                    VALUES ('zalo', $1, $2, 'personal', 'boss_owned', $3, $4,
                            'active', 1)
                    RETURNING id
                    """,
                    own_id,
                    display_name,
                    sess.boss_id,
                    blob,
                )

        svc = BotAccountService(self.pool, self.bus, self._adapter_map_getter())
        await svc.assign_boss_owned(sess.boss_id, "zalo", bot_account_id)
        await svc.accept(sess.boss_id, "zalo")
        sess.bot_account_id = bot_account_id
        sess.display_name = display_name
