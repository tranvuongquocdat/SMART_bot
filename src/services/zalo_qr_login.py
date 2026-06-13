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
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.services.bot_account_session import encrypt_credentials

log = logging.getLogger(__name__)

BRIDGE_DIR = Path(__file__).parent.parent / "channels" / "zalo" / "bridge"
QR_LOGIN_SCRIPT = BRIDGE_DIR / "qr_login.js"

# Thời gian sống của một phiên QR — nguồn duy nhất, truyền xuống script qua env
# và trả về frontend để hiện đếm ngược.
LOGIN_TTL_SECONDS = 180


@dataclass
class LoginSession:
    login_id: str
    owner_key: str  # "boss:<id>" (boss tự kết nối) | "acc:<id>" (superadmin login hộ acc)
    boss_id: int | None = None  # mode boss_connect
    target_account_id: int | None = None  # mode account_login
    actor_user_id: int | None = None  # superadmin thao tác (audit)
    status: str = "starting"  # starting|qr|scanned|success|error
    qr_image_b64: str | None = None
    display_name: str | None = None
    error: str | None = None
    bot_account_id: int | None = None
    deadline_monotonic: float = 0.0
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)
    stderr_tail: list[str] = field(default_factory=list, repr=False)

    @property
    def expires_in_s(self) -> int:
        if self.status in ("success", "error"):
            return 0
        return max(0, int(self.deadline_monotonic - time.monotonic()))


class ZaloQrLoginManager:
    def __init__(self, pool, bus, adapter_map_getter):
        """adapter_map_getter: callable trả về {provider: adapter} tại thời điểm gọi
        (channel registry chỉ sẵn sàng sau lifespan startup)."""
        self.pool = pool
        self.bus = bus
        self._adapter_map_getter = adapter_map_getter
        self._sessions: dict[str, LoginSession] = {}
        self._by_owner: dict[str, str] = {}

    async def start(self, boss_id: int) -> LoginSession:
        """Boss tự kết nối acc phụ (tạo/cập nhật account boss_owned)."""
        return await self._spawn(
            LoginSession(login_id="", owner_key=f"boss:{boss_id}", boss_id=boss_id)
        )

    async def start_for_account(
        self, account_id: int, actor_user_id: int
    ) -> LoginSession:
        """Superadmin đăng nhập QR cho một bot account có sẵn (kể cả re-login)."""
        return await self._spawn(
            LoginSession(
                login_id="",
                owner_key=f"acc:{account_id}",
                target_account_id=account_id,
                actor_user_id=actor_user_id,
            )
        )

    async def _spawn(self, sess: LoginSession) -> LoginSession:
        # Hủy phiên cũ cùng owner nếu còn sống
        old_id = self._by_owner.get(sess.owner_key)
        if old_id:
            await self._kill(old_id)

        sess.login_id = uuid.uuid4().hex
        self._sessions[sess.login_id] = sess
        self._by_owner[sess.owner_key] = sess.login_id

        # Preflight: thiếu node_modules là lỗi hay gặp nhất — báo thẳng thay vì
        # "kết thúc bất thường".
        if not (BRIDGE_DIR / "node_modules" / "zca-js").exists():
            sess.status = "error"
            sess.error = (
                "Zalo bridge dependencies not installed — run `npm install` in "
                "src/channels/zalo/bridge then try again"
            )
            return sess

        try:
            env = os.environ.copy()
            env["LOGIN_TIMEOUT_MS"] = str(LOGIN_TTL_SECONDS * 1000)
            proxy_url = await self._resolve_proxy(sess)
            if proxy_url:
                env["PROXY_URL"] = proxy_url
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(QR_LOGIN_SCRIPT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(BRIDGE_DIR),
                env=env,
            )
        except FileNotFoundError:
            sess.status = "error"
            sess.error = "`node` not found on the server — Node.js must be installed"
            return sess
        sess.deadline_monotonic = time.monotonic() + LOGIN_TTL_SECONDS
        sess.proc = proc
        asyncio.create_task(self._read_events(sess, proc))
        asyncio.create_task(self._drain_stderr(sess, proc))
        return sess

    async def _resolve_proxy(self, sess: LoginSession) -> str | None:
        """Proxy của boss sở hữu acc — boss-connect dùng boss_id trực tiếp,
        account-login truy owner_boss_id của account đích."""
        from src.services.proxy_pool import resolve_for_boss

        try:
            boss_id = sess.boss_id
            if boss_id is None and sess.target_account_id is not None:
                async with self.pool.acquire() as c:
                    boss_id = await c.fetchval(
                        "SELECT owner_boss_id FROM bot_accounts WHERE id=$1",
                        sess.target_account_id,
                    )
            if boss_id is None:
                return None
            return await resolve_for_boss(self.pool, boss_id)
        except Exception:
            log.exception("qr_login: resolve proxy failed")
            return None

    def get(self, boss_id: int, login_id: str) -> LoginSession | None:
        sess = self._sessions.get(login_id)
        if sess is None or sess.boss_id != boss_id:
            return None
        return sess

    def get_by_login_id(self, login_id: str) -> LoginSession | None:
        return self._sessions.get(login_id)

    async def _kill(self, login_id: str) -> None:
        sess = self._sessions.pop(login_id, None)
        if sess is None:
            return
        self._by_owner.pop(sess.owner_key, None)
        if sess.proc is not None and sess.proc.returncode is None:
            try:
                sess.proc.kill()
                await sess.proc.wait()
            except ProcessLookupError:
                pass

    async def _drain_stderr(self, sess: LoginSession, proc) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            log.info("zalo.qr_login: %s", text)
            sess.stderr_tail.append(text)
            del sess.stderr_tail[:-5]  # giữ 5 dòng cuối cho thông báo lỗi

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
                    msg = data.get("message") or "QR login failed"
                    if "timeout" in msg.lower():
                        msg = f"Scan timed out ({LOGIN_TTL_SECONDS}s) — press Try again to get a new code"
                    sess.error = msg
                elif ev == "success":
                    try:
                        await self._provision(sess, data)
                        sess.status = "success"
                    except Exception as e:
                        log.exception("zalo qr provision failed boss=%s", sess.boss_id)
                        sess.status = "error"
                        sess.error = f"Failed to save account: {e}"
        finally:
            await proc.wait()
            if sess.status not in ("success", "error"):
                sess.status = "error"
                detail = sess.stderr_tail[-1] if sess.stderr_tail else None
                sess.error = sess.error or (
                    f"Login session ended unexpectedly: {detail}"
                    if detail
                    else "Login session ended unexpectedly"
                )

    async def _provision(self, sess: LoginSession, data: dict) -> None:
        if sess.target_account_id is not None:
            await self._provision_account_login(sess, data)
        else:
            await self._provision_boss_connect(sess, data)

    async def _provision_account_login(self, sess: LoginSession, data: dict) -> None:
        """Superadmin quét QR cho một bot account có sẵn: cập nhật session/uid,
        kích hoạt lại listener. Không đụng assignment."""
        from src.repositories.admin_audit_log import AdminAuditLogRepo
        from src.repositories.base import BossContext
        from src.repositories.bot_accounts import _row_to_bot_account

        own_id = data.get("own_id")
        creds = {
            "cookie": data.get("cookie"),
            "imei": data.get("imei"),
            "userAgent": data.get("userAgent"),
        }
        blob = encrypt_credentials(creds)

        async with self.pool.acquire() as c:
            # Acc Zalo vừa quét đã gắn vào row khác → chặn (unique provider+uid).
            conflict = await c.fetchval(
                """
                SELECT id FROM bot_accounts
                WHERE provider='zalo' AND provider_user_id=$1 AND id <> $2
                """,
                own_id,
                sess.target_account_id,
            )
            if conflict:
                raise RuntimeError(
                    f"This Zalo account already belongs to bot account #{conflict} — cannot link twice"
                )
            row = await c.fetchrow(
                """
                UPDATE bot_accounts
                   SET provider_user_id=$2, credentials_blob_enc=$3,
                       status='active', status_reason=NULL,
                       display_name=COALESCE(display_name, $4),
                       last_seen_at=NOW(), updated_at=NOW()
                 WHERE id=$1
                RETURNING *
                """,
                sess.target_account_id,
                own_id,
                blob,
                data.get("display_name"),
            )
            if row is None:
                raise RuntimeError("bot account does not exist")

        # Restart listener với session mới (re-login phải thay proc cũ).
        adapter = self._adapter_map_getter().get("zalo")
        if adapter is not None:
            acc = _row_to_bot_account(row)
            try:
                await adapter.stop_inbound(acc)
                await adapter.start_inbound(acc)
            except Exception:
                log.exception("qr account login: restart inbound failed acc=%s", acc.id)

        if sess.actor_user_id:
            await AdminAuditLogRepo(
                self.pool,
                BossContext(boss_id=sess.actor_user_id, user_role="superadmin"),
            ).insert(
                action="bot_account.qr_logged_in",
                target_kind="bot_account",
                target_id=str(sess.target_account_id),
                payload={"provider_user_id": own_id},
            )

        sess.bot_account_id = sess.target_account_id
        sess.display_name = row["display_name"] or data.get("display_name")

    async def _provision_boss_connect(self, sess: LoginSession, data: dict) -> None:
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
            # Mỗi boss chỉ 1 acc Zalo. Acc Zalo này đã thuộc row khác (boss khác
            # / pool) → chặn trùng (unique provider+uid).
            conflict = await c.fetchval(
                """
                SELECT id FROM bot_accounts
                WHERE provider='zalo' AND provider_user_id=$1
                  AND NOT (ownership='boss_owned' AND owner_boss_id=$2)
                """,
                own_id,
                sess.boss_id,
            )
            if conflict:
                raise RuntimeError(
                    f"This Zalo account is already used elsewhere (#{conflict}) — cannot connect twice"
                )

            # Boss đã có acc Zalo khác uid → chặn. Phải gỡ acc cũ trước (1 acc/nền tảng).
            existing = await c.fetchrow(
                """
                SELECT id, provider_user_id FROM bot_accounts
                WHERE provider='zalo' AND ownership='boss_owned' AND owner_boss_id=$1
                """,
                sess.boss_id,
            )
            if existing and existing["provider_user_id"] != own_id:
                raise RuntimeError(
                    "You already connected a different Zalo account. Remove the old one on "
                    "the Channels page before connecting a new account."
                )

            if existing is not None:
                # Re-login cùng acc → cập nhật session.
                bot_account_id = existing["id"]
                await c.execute(
                    """
                    UPDATE bot_accounts
                       SET credentials_blob_enc=$2, status='active',
                           status_reason=NULL, display_name=$3, updated_at=NOW()
                     WHERE id=$1
                    """,
                    bot_account_id,
                    blob,
                    display_name,
                )
            else:
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
