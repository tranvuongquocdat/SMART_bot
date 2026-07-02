"""QR login provisioning: quét xong → bot_account boss_owned + assignment active
+ inbound start ngay (spec zalo-automation §4, invariant then chốt của connect flow).
"""

from __future__ import annotations

import pytest

from src.events.bus import InMemoryEventBus
from src.services.zalo_qr_login import LoginSession, ZaloQrLoginManager


class _FakeAdapter:
    provider = "zalo"

    def __init__(self):
        self.started: list[int] = []
        self.stopped: list[int] = []

    async def start_inbound(self, acc):
        self.started.append(acc.id)

    async def stop_inbound(self, acc):
        self.stopped.append(acc.id)


async def _boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1, 'Sếp QR', 'boss') RETURNING id",
            email,
        )


def _success_payload(own_id="555", name="Acc Phụ"):
    return {
        "own_id": own_id,
        "cookie": {"zpsid": "xyz"},
        "imei": "imei-qr",
        "userAgent": "ua-qr",
        "display_name": name,
    }


@pytest.mark.asyncio
async def test_qr_success_provisions_account_assignment_and_inbound(clean_db):
    boss = await _boss(clean_db, "qr1@x.test")
    adapter = _FakeAdapter()
    mgr = ZaloQrLoginManager(clean_db, InMemoryEventBus(), lambda: {"zalo": adapter})
    sess = LoginSession(login_id="t1", owner_key=f"boss:{boss}", boss_id=boss)

    await mgr._provision(sess, _success_payload())

    async with clean_db.acquire() as c:
        acc = await c.fetchrow(
            "SELECT * FROM bot_accounts WHERE provider='zalo' AND owner_boss_id=$1", boss)
        assign = await c.fetchrow(
            "SELECT * FROM bot_account_assignments WHERE boss_id=$1 AND provider='zalo'", boss)
    assert acc is not None
    assert acc["ownership"] == "boss_owned"
    assert acc["status"] == "active"
    assert acc["provider_user_id"] == "555"
    assert acc["credentials_blob_enc"] is not None  # session Fernet-encrypted
    assert assign["status"] == "active"
    assert assign["bot_account_id"] == acc["id"]
    assert adapter.started == [acc["id"]]  # inbound chạy ngay, không cần restart
    assert sess.bot_account_id == acc["id"]


@pytest.mark.asyncio
async def test_qr_relogin_same_account_updates_session_no_duplicate(clean_db):
    boss = await _boss(clean_db, "qr2@x.test")
    adapter = _FakeAdapter()
    mgr = ZaloQrLoginManager(clean_db, InMemoryEventBus(), lambda: {"zalo": adapter})

    await mgr._provision(
        LoginSession(login_id="a", owner_key=f"boss:{boss}", boss_id=boss),
        _success_payload())
    await mgr._provision(
        LoginSession(login_id="b", owner_key=f"boss:{boss}", boss_id=boss),
        _success_payload(name="Acc Phụ Mới"))

    async with clean_db.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM bot_accounts WHERE provider='zalo' AND owner_boss_id=$1",
            boss)
        status = await c.fetchval(
            "SELECT status FROM bot_accounts WHERE provider='zalo' AND owner_boss_id=$1",
            boss)
    assert n == 1  # re-login không nhân đôi acc
    assert status == "active"
    assert len(adapter.started) == 2  # mỗi lần login đều (re)start inbound


@pytest.mark.asyncio
async def test_qr_different_zalo_account_blocked(clean_db):
    boss = await _boss(clean_db, "qr3@x.test")
    adapter = _FakeAdapter()
    mgr = ZaloQrLoginManager(clean_db, InMemoryEventBus(), lambda: {"zalo": adapter})

    await mgr._provision(
        LoginSession(login_id="a", owner_key=f"boss:{boss}", boss_id=boss),
        _success_payload(own_id="555"))
    with pytest.raises(RuntimeError, match="different Zalo account"):
        await mgr._provision(
            LoginSession(login_id="b", owner_key=f"boss:{boss}", boss_id=boss),
            _success_payload(own_id="777"))


@pytest.mark.asyncio
async def test_qr_account_of_other_boss_blocked(clean_db):
    boss1 = await _boss(clean_db, "qr4a@x.test")
    boss2 = await _boss(clean_db, "qr4b@x.test")
    adapter = _FakeAdapter()
    mgr = ZaloQrLoginManager(clean_db, InMemoryEventBus(), lambda: {"zalo": adapter})

    await mgr._provision(
        LoginSession(login_id="a", owner_key=f"boss:{boss1}", boss_id=boss1),
        _success_payload(own_id="555"))
    with pytest.raises(RuntimeError, match="already used"):
        await mgr._provision(
            LoginSession(login_id="b", owner_key=f"boss:{boss2}", boss_id=boss2),
            _success_payload(own_id="555"))
