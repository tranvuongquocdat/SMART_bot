"""BotAccountStatusSync — persist ``bot_account.status_changed`` vào DB.

Adapter (bridge báo disconnected/status) và health job chỉ PUBLISH event;
không có subscriber thì ``bot_accounts.status`` không đổi → trang Channels
vẫn hiện "active" khi session Zalo đã chết, boss không biết phải quét lại QR.
Đăng ký một lần ở app lifespan (cạnh InboundIngest).
"""

from __future__ import annotations

import logging

from src.domain.bot_account import BotAccountStatus

log = logging.getLogger(__name__)

_VALID = {s.value for s in BotAccountStatus}


class BotAccountStatusSync:
    def __init__(self, pool):
        self.pool = pool

    def register(self, bus) -> None:
        bus.subscribe("bot_account.status_changed", self._handle)

    async def _handle(self, payload: dict) -> None:
        acc_id = payload.get("bot_account_id")
        to = payload.get("to")
        if acc_id is None or to not in _VALID:
            log.warning("status_changed bỏ qua payload lạ: %s", payload)
            return
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE bot_accounts
                   SET status=$2, status_reason=$3, updated_at=NOW()
                 WHERE id=$1
                """,
                acc_id,
                to,
                payload.get("reason"),
            )
