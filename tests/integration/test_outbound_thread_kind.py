import pytest

from src.services.outbound_service import OutboundService


class _Bus:
    async def publish(self, *a, **k):
        return None


class _Adapter:
    provider = "zalo"

    def normalize_text(self, t):
        return t

    def classify_thread_kind(self, chat_id):
        return "group"  # heuristic CŨ — sai cho DM uid dài

    async def send_text(self, bot_acc, chat_id, text, thread_kind):
        self.kind = thread_kind
        return "ok"


class _Reg:
    def __init__(self, a):
        self.a = a

    def get(self, p):
        return self.a


class _AdminRepo:
    async def find_active_for_boss(self, boss_id, provider):
        return object()


@pytest.mark.asyncio
async def test_outbound_uses_explicit_chat_type_for_dm():
    a = _Adapter()
    svc = OutboundService(None, _Bus(), _Reg(a), _AdminRepo())
    await svc.send(
        boss_id=1, provider="zalo", chat_id="123456789012345678901",
        content="hi", trigger="dm", chat_type="dm",
    )
    assert a.kind == "user"  # KHÔNG bị heuristic ép thành group


@pytest.mark.asyncio
async def test_outbound_falls_back_to_heuristic_when_no_chat_type():
    a = _Adapter()
    svc = OutboundService(None, _Bus(), _Reg(a), _AdminRepo())
    await svc.send(
        boss_id=1, provider="zalo", chat_id="grp", content="hi", trigger="x",
    )
    assert a.kind == "group"  # giữ tương thích chỗ gọi cũ
