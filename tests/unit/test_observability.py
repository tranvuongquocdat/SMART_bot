"""Tests for observability — context propagation + log injection."""
from __future__ import annotations

import logging

import pytest

from src.config import Settings
from src.infrastructure.observability import (
    current_context,
    request_context,
    setup_logging,
    setup_tracer,
)


def _settings() -> Settings:
    return Settings(
        telegram_bot_token="x", lark_app_id="x", lark_app_secret="x",
        openai_api_key="sk-x", cohere_api_key="x",
    )


def test_outside_block_context_is_none():
    ctx = current_context()
    assert ctx == {
        "boss_internal_id": None,
        "internal_chat_id": None,
        "request_id": None,
    }


def test_block_sets_and_resets_context():
    with request_context(boss_internal_id="b1", internal_chat_id="c1"):
        ctx = current_context()
        assert ctx["boss_internal_id"] == "b1"
        assert ctx["internal_chat_id"] == "c1"
        assert ctx["request_id"]  # auto-generated UUID
    # After exit, vars are reset.
    after = current_context()
    assert after == {
        "boss_internal_id": None,
        "internal_chat_id": None,
        "request_id": None,
    }


def test_explicit_request_id_used():
    with request_context(request_id="my-req-42"):
        assert current_context()["request_id"] == "my-req-42"


def test_setup_logging_attaches_filter_idempotently():
    setup_logging(_settings())
    setup_logging(_settings())  # second call is a no-op
    root = logging.getLogger()
    from src.infrastructure.observability import _ContextFilter
    filters = [f for f in root.filters if isinstance(f, _ContextFilter)]
    assert len(filters) == 1


def test_filter_injects_context_fields_directly():
    """Verify the filter sets context attrs on a LogRecord. (Bypasses caplog
    because pytest's caplog uses a separate propagation handler that doesn't
    walk the root filter chain.)"""
    from src.infrastructure.observability import _ContextFilter
    setup_logging(_settings())
    f = _ContextFilter()
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=0,
        msg="hi", args=(), exc_info=None,
    )
    with request_context(boss_internal_id="b9", internal_chat_id="c9"):
        f.filter(rec)
    assert rec.boss_internal_id == "b9"
    assert rec.internal_chat_id == "c9"
    assert rec.request_id and rec.request_id != "-"


def test_setup_tracer_returns_noop_without_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracer = setup_tracer(_settings())
    # Should be the NoOpTracer; usable as a contextmanager.
    with tracer.start_as_current_span("x"):
        pass
