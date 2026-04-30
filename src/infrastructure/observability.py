"""Structured logging context + optional OpenTelemetry tracer.

Phase 5c ships the scaffold; admin dashboards / Prometheus exporters are
future work. The shape:

- `request_context(...)` — a `contextvars`-backed manager that injects
  `boss_internal_id` / `internal_chat_id` / `request_id` into every log
  record produced inside the block. The router calls it on every inbound
  message; downstream code logs as usual and tags appear automatically.

- `setup_logging(settings)` — initialises the root logger. If
  `Settings.log_format == 'json'`, emits JSON Lines to stdout (one record
  per line, fields = standard logging attrs + context vars). Otherwise it
  keeps the existing human-readable format.

- `setup_tracer(settings)` — installs an OpenTelemetry tracer if
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set in env; otherwise returns a no-op
  tracer. Spans wrap the router boundary so request rate / latency is
  captured without per-call instrumentation.

For Phase 5c we wire `request_context` into the router. JSON output and
real OTel export can be turned on later by env var without code change.
"""
from __future__ import annotations

import contextvars
import logging
import sys
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from src.config import Settings


# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------

_boss_internal_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "boss_internal_id", default=None,
)
_internal_chat_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "internal_chat_id", default=None,
)
_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None,
)


@contextmanager
def request_context(
    *,
    boss_internal_id: Optional[str] = None,
    internal_chat_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Iterator[None]:
    """Bind context vars for the duration of a request. Auto-generates a
    `request_id` (UUID4) if none is supplied — useful for correlating logs
    across the whole inbound→outbound flow."""
    rid = request_id or str(uuid.uuid4())
    tok_b = _boss_internal_id.set(boss_internal_id)
    tok_c = _internal_chat_id.set(internal_chat_id)
    tok_r = _request_id.set(rid)
    try:
        yield
    finally:
        _boss_internal_id.reset(tok_b)
        _internal_chat_id.reset(tok_c)
        _request_id.reset(tok_r)


def current_context() -> dict[str, Optional[str]]:
    """Snapshot of current context vars (for log filters / span attributes)."""
    return {
        "boss_internal_id": _boss_internal_id.get(),
        "internal_chat_id": _internal_chat_id.get(),
        "request_id": _request_id.get(),
    }


# ---------------------------------------------------------------------------
# Logging filter that injects context vars into every record
# ---------------------------------------------------------------------------

class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = current_context()
        for k, v in ctx.items():
            setattr(record, k, v if v is not None else "-")
        return True


class _JsonFormatter(logging.Formatter):
    """Emit one JSON record per log line. Includes context-var fields the
    `_ContextFilter` injected, plus standard logging attrs. No exception
    formatting — the stdlib default already inlines `exc_info` reasonably."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "boss_internal_id": getattr(record, "boss_internal_id", "-"),
            "internal_chat_id": getattr(record, "internal_chat_id", "-"),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: Settings) -> None:
    """Attach the context filter to the root logger. Idempotent.

    When `settings.log_format == 'json'`, also swap every root handler's
    formatter to `_JsonFormatter` so lines come out as JSON Lines. With any
    other value the existing human-readable format is left alone — the only
    visible change is structured attributes added by the context filter.
    """
    root = logging.getLogger()
    if not any(isinstance(f, _ContextFilter) for f in root.filters):
        root.addFilter(_ContextFilter())

    if (settings.log_format or "").lower() == "json":
        json_fmt = _JsonFormatter()
        for h in root.handlers:
            h.setFormatter(json_fmt)


# ---------------------------------------------------------------------------
# OpenTelemetry tracer (no-op if no exporter env var)
# ---------------------------------------------------------------------------

def setup_tracer(settings: Settings) -> Any:
    """Return a tracer object exposing `start_as_current_span(name)`.

    If `OTEL_EXPORTER_OTLP_ENDPOINT` is set in env AND opentelemetry SDK is
    installed, returns a real tracer. Otherwise returns a `NoOpTracer` whose
    spans are zero-cost. Callers wrap operations:

        tracer = setup_tracer(settings)
        with tracer.start_as_current_span("router.handle"):
            ...
    """
    import os
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return _NoOpTracer()
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        # SDK not installed — fall back to no-op silently. To enable:
        #   uv add opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
        return _NoOpTracer()

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("ceo-secretary")


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield None
