"""Verify the agent's system prompt includes Zalo guidance when
ZALO_ENABLED is true — so the bot can explain the onboarding rules
to the sếp when they forget."""
from __future__ import annotations

from types import SimpleNamespace

from src.agent.secretary_agent import _build_zalo_guidance


def test_zalo_guidance_empty_when_disabled():
    s = SimpleNamespace(zalo_enabled=False, zalo_onboard_phrase="khởi tạo trợ lý")
    assert _build_zalo_guidance(s) == ""


def test_zalo_guidance_includes_onboard_phrase_when_enabled():
    s = SimpleNamespace(zalo_enabled=True, zalo_onboard_phrase="khởi tạo trợ lý")
    out = _build_zalo_guidance(s)
    assert "khởi tạo trợ lý" in out
    assert "Zalo channel rules" in out
    assert "đăng ký group này" in out


def test_zalo_guidance_uses_custom_phrase():
    s = SimpleNamespace(zalo_enabled=True, zalo_onboard_phrase="onboard please")
    out = _build_zalo_guidance(s)
    assert "onboard please" in out
    assert "khởi tạo trợ lý" not in out
